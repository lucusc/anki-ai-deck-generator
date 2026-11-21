from dataclasses import dataclass
from datetime import timedelta
import json
import logging
import os
from time import monotonic
from typing import Callable

from azure.core.exceptions import AzureError
from azure.identity import DefaultAzureCredential

from auth import Principal
from .artifacts import Artifacts, DrainPending
from .azure import AzureTable, Table, Write
from .blob import AzureBlobs, Blobs, StoragePolicyError
from .models import user_partition
from .repository import Conflict, Inactive, Repository, _keys


CLEANUP_LEAD = timedelta(hours=1)
MAX_CYCLE = timedelta(minutes=15)


class RetentionUnavailable(Exception):
    """Content-free operational failure; alert and recover the persisted cursor."""


@dataclass(frozen=True)
class Settings:
    table_endpoint: str
    table_name: str
    blob_endpoint: str
    container: str
    subscription_id: str
    resource_group: str
    account_name: str
    users: tuple[Principal, ...]

    @classmethod
    def from_environment(cls) -> "Settings":
        # A deployment-controlled, explicitly bounded inventory, not an account scan.
        try:
            raw = json.loads(os.environ.get("RETENTION_USERS", "[]"))
            if not isinstance(raw, list) or not 1 <= len(raw) <= 5:
                raise ValueError("Explicit inventory of 1-5 users required")
            users = []
            for entry in raw:
                if (
                    not isinstance(entry, dict) or set(entry) != {"issuer", "subject"}
                    or not all(isinstance(value, str) and value.strip() for value in entry.values())
                ):
                    raise ValueError("Exact issuer/subject inventory required")
                users.append(Principal(entry["issuer"], entry["subject"]))
            if len({user_partition(user) for user in users}) != len(users):
                raise ValueError("Duplicate inventory user")
            values = [os.environ[name] for name in (
                "STORAGE_TABLE_ENDPOINT", "STORAGE_TABLE_NAME",
                "STORAGE_BLOB_ENDPOINT", "STORAGE_BLOB_CONTAINER",
                "STORAGE_SUBSCRIPTION_ID", "STORAGE_RESOURCE_GROUP", "STORAGE_ACCOUNT_NAME",
            )]
            if not all(values):
                raise ValueError("Storage configuration required")
        except (KeyError, ValueError, TypeError):
            raise RetentionUnavailable("retention_configuration_invalid") from None
        return cls(*values, tuple(users))


@dataclass(frozen=True)
class Sweep:
    inspected: int
    deleted: int
    complete: bool


def sweep_user(
    repository: Repository, blobs: Blobs, *, limit: int = 10, deadline: float | None = None,
) -> Sweep:
    """One SDK page per user and invocation; failures never advance the saved cursor."""
    progress = repository._optional("r:retention")
    now = repository._now()
    previous = progress.properties if progress else {}
    continuation = json.loads(previous["Cursor"]) if "Cursor" in previous else None
    started = previous.get("CycleStartedAt", now)
    completed = previous.get("LastCompletedAt", now)
    page = repository.table.page(repository.partition, continuation=continuation, limit=limit)
    artifacts = Artifacts(repository, blobs)
    removed = 0
    failures = 0
    for entity in page.rows:
        if deadline is not None and monotonic() >= deadline:
            failures += 1
            break
        try:
            # A preceding deck cleanup may have removed or fenced this page's snapshot.
            entity = repository._optional(entity.properties["RowKey"])
            if entity is None:
                continue
            properties = entity.properties
            if properties.get("Kind") == "BlobArtifacts":
                if (
                    properties["State"] == "deleting" or properties.get("DeleteRequested")
                    or artifacts.effective_expiry(properties) <= now + CLEANUP_LEAD
                ):
                    artifacts._delete_row(entity)
                    removed += 1
            elif properties.get("Kind") == "Decks" and properties["State"] == "deleting":
                if artifacts.delete_deck(properties["DeckId"], limit=limit):
                    removed += 1
            elif repository.purge_entity(entity, cutoff=now + CLEANUP_LEAD):
                removed += 1
        except (AzureError, StoragePolicyError, Conflict, Inactive, DrainPending):
            failures += 1
            logging.error("retention_record_failed")
    complete = page.continuation is None and not failures
    properties = {
        **_keys(repository.partition, "r:retention"), "Kind": "RetentionCursor",
        "CycleStartedAt": now if complete else started,
        "LastCompletedAt": now if complete else completed,
    }
    cursor = continuation if failures else page.continuation
    if cursor is not None:
        properties["Cursor"] = json.dumps(cursor, separators=(",", ":"))
    repository.table.transact([Write(
        "replace" if progress else "create", properties, progress.etag if progress else None,
    )])
    result = Sweep(len(page.rows), removed, complete)
    if failures:
        raise RetentionUnavailable("retention_records_pending")
    # Persist progress before raising, so a backlogged user is not stuck on page one.
    if now - started > MAX_CYCLE or now - completed > MAX_CYCLE:
        raise RetentionUnavailable("retention_cycle_overdue")
    return result


def run_sweep(
    table: Table, blobs: Blobs, users: tuple[Principal, ...], *,
    repository_factory: Callable[[Table, Principal], Repository] = Repository,
) -> None:
    if not 1 <= len(users) <= 5 or len({user_partition(user) for user in users}) != len(users):
        raise RetentionUnavailable("retention_inventory_invalid")
    failures = 0
    deadline = monotonic() + 180
    for user in users:
        try:
            if monotonic() >= deadline:
                raise RetentionUnavailable("retention_execution_budget_exhausted")
            result = sweep_user(repository_factory(table, user), blobs, deadline=deadline)
            logging.info(
                "retention_page inspected=%d deleted=%d complete=%s",
                result.inspected, result.deleted, result.complete,
            )
        except (AzureError, StoragePolicyError, Conflict, Inactive, DrainPending, RetentionUnavailable):
            failures += 1
            logging.error("retention_user_failed")
    if failures:
        raise RetentionUnavailable("retention_sweep_failed") from None


def run_configured_sweep() -> None:
    """No provisioning or host startup networking; actual SDK operations at timer invocation."""
    settings = Settings.from_environment()
    credential = DefaultAzureCredential()
    table = blobs = None
    try:
        table = AzureTable.connect(settings.table_endpoint, settings.table_name, credential)
        blobs = AzureBlobs.connect(
            settings.blob_endpoint, settings.container, credential,
            subscription_id=settings.subscription_id, resource_group=settings.resource_group,
            account_name=settings.account_name,
        )
        blobs.check_policy()
        run_sweep(table, blobs, settings.users)
    except (AzureError, ValueError, StoragePolicyError):
        raise RetentionUnavailable("retention_storage_unavailable") from None
    finally:
        if blobs is not None:
            blobs.close()
        if table is not None:
            table.close()
        credential.close()
