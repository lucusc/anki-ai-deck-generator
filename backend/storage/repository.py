from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import uuid4

from azure.core.exceptions import ResourceNotFoundError

from auth import Principal
from .azure import Snapshot, Table, Write
from .models import (
    ArtifactReference, Provenance, State, TRANSITIONS, Usage,
    digest, identifier, user_partition, utc,
)


class Inactive(Exception):
    """Missing, deleted or expired ownership boundary."""


class Conflict(Exception):
    """Caller ETag, lifecycle or worker ownership is stale."""


def _keys(partition: str, row: str) -> dict:
    return {"PartitionKey": partition, "RowKey": row}


class Repository:
    """One authenticated user's metadata; never accepts a caller partition key."""

    def __init__(
        self, table: Table, principal: Principal,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.table = table
        self.partition = user_partition(principal)
        self.clock = clock

    def _now(self) -> datetime:
        return utc(self.clock())

    def _optional(self, row: str) -> Snapshot | None:
        try:
            return self.table.get(self.partition, row)
        except ResourceNotFoundError as exc:
            if getattr(exc, "error_code", None) not in {"ResourceNotFound", "EntityNotFound"}:
                raise
            return None

    def _deck(self, deck_id: str, deleting: bool = False) -> Snapshot:
        deck = self._optional("d:" + identifier(deck_id))
        if deck is None or deck.properties["State"] != ("deleting" if deleting else "active"):
            raise Inactive("Deck mapping unavailable")
        return deck

    def _entity(self, kind: str, deck_id: str, entity_id: str) -> Snapshot:
        self._deck(deck_id)
        entity = self._optional(f"{kind}:{deck_id}:{identifier(entity_id)}")
        if (
            entity is None or entity.properties["ExpiresAt"] <= self._now()
            or entity.properties.get("State") == State.DELETED
        ):
            raise Inactive("Operational metadata unavailable")
        if kind != "j":
            job = self._optional(f"j:{deck_id}:{entity.properties['JobId']}")
            if (
                job is None or job.properties["ExpiresAt"] <= self._now()
                or job.properties["State"] == State.DELETED
            ):
                raise Inactive("Parent job unavailable")
        properties = dict(entity.properties)
        if properties.get("ArtifactExpiresAt", self._now()) <= self._now():
            for key in ("ArtifactId", "ArtifactKind", "ArtifactExpiresAt"):
                properties.pop(key, None)
        return Snapshot(properties, entity.etag)

    def _commit(self, deck: Snapshot, writes: list[Write]) -> None:
        # Replacing the guard even without changing its properties advances its ETag.
        self.table.transact([Write("replace", deck.properties, deck.etag), *writes])

    def _operational(self, kind: str, deck_id: str, entity_id: str) -> dict:
        now = self._now()
        return {
            **_keys(self.partition, f"{kind}:{deck_id}:{entity_id}"),
            "Kind": {"j": "Jobs", "o": "Documents", "c": "Cards"}[kind],
            "DeckId": deck_id, "CreatedAt": now, "UpdatedAt": now,
            "ExpiresAt": now + timedelta(days=30),
        }

    def _reference(self, reference: ArtifactReference, metadata_expiry: datetime) -> dict:
        properties = reference.properties(self._now())
        properties["ArtifactExpiresAt"] = min(properties["ArtifactExpiresAt"], metadata_expiry)
        return properties

    def create_deck(self, *, subject_id: str | None = None, chapter_id: str | None = None) -> str:
        deck_id = str(uuid4())
        now = self._now()
        properties = {
            **_keys(self.partition, "d:" + deck_id), "Kind": "Decks",
            "DeckId": deck_id, "State": "active", "CreatedAt": now,
            "UpdatedAt": now, "ExpiresAt": now + timedelta(days=30),
        }
        if subject_id is not None:
            properties["SubjectId"] = identifier(subject_id)
        if chapter_id is not None:
            properties["ChapterId"] = identifier(chapter_id)
        self.table.transact([Write("create", properties)])
        return deck_id

    def get_deck(self, deck_id: str) -> Snapshot:
        deck = self._deck(deck_id)
        if deck.properties.get("ExpiresAt", self._now()) <= self._now():
            return Snapshot(self._minimal_deck(deck.properties), deck.etag)
        return deck

    @staticmethod
    def _minimal_deck(properties: dict) -> dict:
        return {key: properties[key] for key in (
            "PartitionKey", "RowKey", "Kind", "DeckId", "State",
        )}

    def list_decks(self):
        for deck in self.table.query(self.partition, "d:"):
            if deck.properties["State"] == "active":
                yield self.get_deck(deck.properties["DeckId"])

    def create_job(self, deck_id: str, settings_hash: str) -> str:
        deck = self._deck(deck_id)
        job_id = str(uuid4())
        properties = {
            **self._operational("j", deck_id, job_id),
            "JobId": job_id, "State": State.QUEUED.value,
            "SettingsHash": digest(settings_hash), **Usage().properties(),
        }
        self._commit(deck, [Write("create", properties)])
        return job_id

    def get_job(self, deck_id: str, job_id: str) -> Snapshot:
        return self._entity("j", deck_id, job_id)

    def list_jobs(self, deck_id: str):
        self._deck(deck_id)
        for job in self.table.query(self.partition, f"j:{deck_id}:"):
            if job.properties["ExpiresAt"] > self._now() and job.properties["State"] != State.DELETED:
                yield self.get_job(deck_id, job.properties["JobId"])

    def claim_job(
        self, deck_id: str, job_id: str, etag: str, *, lease: timedelta = timedelta(minutes=5),
    ) -> str:
        deck = self._deck(deck_id)
        job = self.get_job(deck_id, job_id)
        now = self._now()
        if (
            job.etag != etag or job.properties["State"] not in {
                State.QUEUED, State.EXTRACTING, State.GENERATING,
            } or job.properties.get("LeaseUntil", now) > now
        ):
            raise Conflict("Job cannot be claimed")
        if not timedelta(0) < lease <= timedelta(minutes=5):
            raise ValueError("Lease must be positive and at most five minutes")
        token = str(uuid4())
        properties = {
            **job.properties, "LeaseToken": token,
            "LeaseUntil": min(now + lease, job.properties["ExpiresAt"]), "UpdatedAt": now,
        }
        self._commit(deck, [Write("replace", properties, etag)])
        return token

    def _worker(self, deck_id: str, job_id: str, etag: str, token: str) -> Snapshot:
        job = self.get_job(deck_id, job_id)
        if (
            job.etag != etag or job.properties.get("LeaseToken") != identifier(token)
            or job.properties.get("LeaseUntil", self._now()) <= self._now()
            or job.properties["State"] not in {State.QUEUED, State.EXTRACTING, State.GENERATING}
        ):
            raise Conflict("Worker ownership is stale")
        return job

    def transition_job(
        self, deck_id: str, job_id: str, etag: str, target: State, *,
        lease_token: str | None = None, usage: Usage | None = None,
        result: ArtifactReference | None = None,
    ) -> None:
        if not isinstance(target, State):
            raise ValueError("Explicit job state required")
        deck = self._deck(deck_id)
        job = self.get_job(deck_id, job_id)
        source = State(job.properties["State"])
        if job.etag != etag or target not in TRANSITIONS[source]:
            raise Conflict("Job transition is stale or invalid")
        if target not in {State.DELETED, State.COMPLETED}:
            if lease_token is None:
                raise Conflict("Worker ownership required")
            self._worker(deck_id, job_id, etag, lease_token)
        properties = {**job.properties, "State": target.value, "UpdatedAt": self._now()}
        if usage is not None:
            properties.update(usage.properties())
        if result is not None:
            if target != State.READY or result.kind.value != "result":
                raise ValueError("Results belong only to ready_for_review")
            properties.update(self._reference(result, job.properties["ExpiresAt"]))
        elif target == State.READY:
            raise ValueError("Ready jobs require a result reference")
        if target in {State.READY, State.FAILED, State.COMPLETED, State.DELETED}:
            properties.pop("LeaseToken", None)
            properties.pop("LeaseUntil", None)
        if target == State.COMPLETED and "ArtifactExpiresAt" in properties:
            properties["ArtifactExpiresAt"] = min(
                properties["ArtifactExpiresAt"], self._now() + timedelta(days=1),
            )
        if target == State.DELETED:
            for key in ("ArtifactId", "ArtifactKind", "ArtifactExpiresAt"):
                properties.pop(key, None)
        self._commit(deck, [Write("replace", properties, etag)])

    def create_document(
        self, deck_id: str, job_id: str, job_etag: str, lease_token: str, *,
        source_hash: str, compatibility_hash: str, provenance: Provenance,
        original: ArtifactReference | None = None,
    ) -> str:
        deck = self._deck(deck_id)
        job = self._worker(deck_id, job_id, job_etag, lease_token)
        document_id = str(uuid4())
        properties = {
            **self._operational("o", deck_id, document_id), "DocumentId": document_id,
            "JobId": job_id, "SourceHash": digest(source_hash),
            "CompatibilityHash": digest(compatibility_hash),
            "State": State.EXTRACTING.value, **provenance.properties(),
        }
        properties["ExpiresAt"] = job.properties["ExpiresAt"]
        if original is not None:
            if original.kind.value != "original":
                raise ValueError("Original reference required")
            properties.update(self._reference(original, job.properties["ExpiresAt"]))
        self._commit(deck, [Write("create", properties)])
        return document_id

    def get_document(self, deck_id: str, document_id: str) -> Snapshot:
        return self._entity("o", deck_id, document_id)

    def transition_document(
        self, deck_id: str, document_id: str, etag: str, target: State, *,
        job_etag: str | None = None, lease_token: str | None = None,
    ) -> None:
        if not isinstance(target, State):
            raise ValueError("Explicit document state required")
        deck = self._deck(deck_id)
        document = self.get_document(deck_id, document_id)
        if document.etag != etag or target not in TRANSITIONS[State(document.properties["State"])]:
            raise Conflict("Document transition is stale or invalid")
        if target != State.DELETED:
            if job_etag is None or lease_token is None:
                raise Conflict("Worker ownership required")
            self._worker(deck_id, document.properties["JobId"], job_etag, lease_token)
        properties = {**document.properties, "State": target.value, "UpdatedAt": self._now()}
        if target == State.DELETED:
            for key in ("ArtifactId", "ArtifactKind", "ArtifactExpiresAt"):
                properties.pop(key, None)
        self._commit(deck, [Write("replace", properties, etag)])

    def create_card(
        self, deck_id: str, job_id: str, job_etag: str, lease_token: str, *,
        document_id: str, card_hash: str, provenance: Provenance,
        payload: ArtifactReference,
    ) -> str:
        deck = self._deck(deck_id)
        job = self._worker(deck_id, job_id, job_etag, lease_token)
        document = self.get_document(deck_id, document_id)
        if job.properties["State"] != State.GENERATING or document.properties["JobId"] != job_id:
            raise Conflict("Card source does not belong to generating job")
        if payload.kind.value != "result":
            raise ValueError("Result payload reference required")
        card_id = str(uuid4())
        properties = {
            **self._operational("c", deck_id, card_id), "CardId": card_id,
            "JobId": job_id, "DocumentId": document_id, "CardHash": digest(card_hash),
            "SourceHash": document.properties["SourceHash"],
            "State": State.READY.value, **provenance.properties(),
            **self._reference(payload, job.properties["ExpiresAt"]),
        }
        properties["ExpiresAt"] = job.properties["ExpiresAt"]
        self._commit(deck, [Write("create", properties)])
        return card_id

    def get_card(self, deck_id: str, card_id: str) -> Snapshot:
        return self._entity("c", deck_id, card_id)

    def record_import(
        self, deck_id: str, card_id: str, card_etag: str, import_id: str,
    ) -> None:
        """Call only after Anki commit; this method does not perform that commit."""
        deck = self._deck(deck_id)
        card = self.get_card(deck_id, card_id)
        job = self.get_job(deck_id, card.properties["JobId"])
        document = self.get_document(deck_id, card.properties["DocumentId"])
        if card.etag != card_etag or card.properties["State"] != State.READY:
            raise Conflict("Card acknowledgement is stale")
        if job.properties["State"] != State.READY:
            raise Conflict("Job is not ready for import")
        import_id = identifier(import_id)
        card_index = {
            **_keys(self.partition, f"h:{deck_id}:{card.properties['CardHash']}"),
            "Kind": "CardHash", "CardHash": card.properties["CardHash"], "ImportId": import_id,
        }
        source_row = (
            f"s:{deck_id}:{document.properties['SourceHash']}:"
            f"{document.properties['CompatibilityHash']}"
        )
        source_index = {
            **_keys(self.partition, source_row), "Kind": "SourceHash",
            "SourceHash": document.properties["SourceHash"],
            "CompatibilityHash": document.properties["CompatibilityHash"],
        }
        existing_source = self._optional(source_row)
        writes = [
            Write("replace", {
                **card.properties, "State": State.COMPLETED.value, "ImportId": import_id,
                "UpdatedAt": self._now(),
            }, card_etag),
            Write("create", card_index),
        ]
        if existing_source is None:
            writes.append(Write("create", source_index))
        if "ArtifactExpiresAt" in card.properties:
            writes[0].properties["ArtifactExpiresAt"] = min(
                card.properties["ArtifactExpiresAt"], self._now() + timedelta(days=1),
            )
        self._commit(deck, writes)

    def find_source(self, deck_id: str, source_hash: str, compatibility_hash: str) -> Snapshot | None:
        self._deck(deck_id)
        return self._optional(f"s:{deck_id}:{digest(source_hash)}:{digest(compatibility_hash)}")

    def find_card(self, deck_id: str, card_hash: str) -> Snapshot | None:
        self._deck(deck_id)
        return self._optional(f"h:{deck_id}:{digest(card_hash)}")

    def begin_deck_deletion(self, deck_id: str) -> None:
        deck = self._optional("d:" + identifier(deck_id))
        if deck is None or deck.properties["State"] == "deleting":
            return
        properties = {**self._minimal_deck(deck.properties), "State": "deleting"}
        self.table.transact([Write("replace", properties, deck.etag)])

    def finish_deck_deletion(self, deck_id: str) -> None:
        """Remove Table children then mapping. External artifacts must already be drained."""
        if self._optional("d:" + identifier(deck_id)) is None:
            return
        self._deck(deck_id, deleting=True)
        for kind in ("j", "o", "c", "s", "h"):
            batch = []
            for child in self.table.query(self.partition, f"{kind}:{deck_id}:"):
                batch.append(Write("delete", _keys(self.partition, child.properties["RowKey"]), child.etag))
                if len(batch) == 99:
                    self._commit(self._deck(deck_id, deleting=True), batch)
                    batch = []
            if batch:
                self._commit(self._deck(deck_id, deleting=True), batch)
        deck = self._deck(deck_id, deleting=True)
        self.table.transact([Write("delete", _keys(self.partition, "d:" + deck_id), deck.etag)])

    def purge_expired(self) -> int:
        """One user's sweep; scheduler/user inventory belongs to integration, not this schema."""
        removed = 0
        for entity in self.table.query(self.partition):
            properties = entity.properties
            expiry = properties.get("ExpiresAt")
            if expiry is None or expiry > self._now():
                continue
            deck = self._optional("d:" + properties["DeckId"])
            if deck is None:
                continue
            if properties["Kind"] == "Decks":
                self.table.transact([Write("replace", self._minimal_deck(properties), entity.etag)])
            else:
                self._commit(deck, [Write("delete", _keys(
                    self.partition, properties["RowKey"],
                ), entity.etag)])
                removed += 1
        return removed
