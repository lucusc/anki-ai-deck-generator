"""Blob transport primitives; only Artifacts exposes user-facing operations."""

from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Protocol
from urllib.parse import urlsplit

from azure.core import MatchConditions
from azure.core.credentials import TokenCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.mgmt.storage import StorageManagementClient
from azure.storage.blob import BlobSasPermissions, BlobServiceClient, ContentSettings, generate_blob_sas


MAX_BYTES = 16 * 1024 * 1024


class StoragePolicyError(Exception):
    """Provisioned storage would retain copies or expose private content."""


@dataclass(frozen=True)
class Access:
    url: str = field(repr=False)
    expires_at: datetime


class Blobs(Protocol):
    def check_policy(self) -> None: ...
    def initialize(self, name: str, lease_id: str) -> str: ...
    def put(self, name: str, data: bytes, lease_id: str, etag: str) -> str: ...
    def download(self, name: str, etag: str) -> bytes: ...
    def delete(self, name: str, lease_id: str) -> None: ...
    def read_access(self, name: str, start: datetime, expiry: datetime) -> Access: ...


class AzureBlobs:
    """Preprovisioned private container, token credentials, no write SAS or copy APIs."""

    def __init__(
        self, client: BlobServiceClient, container: str, management: StorageManagementClient,
        resource_group: str, account_name: str,
    ):
        if not re.fullmatch("[a-z0-9](?:[a-z0-9-]{1,61})[a-z0-9]", container) or "--" in container:
            raise ValueError("Valid private container name required")
        self.client = client
        self.container = client.get_container_client(container)
        if not re.fullmatch("[a-z0-9]{3,24}", account_name) or not resource_group:
            raise ValueError("Storage account/resource group required")
        if client.url.rstrip("/") != f"https://{account_name}.blob.core.windows.net":
            raise ValueError("Policy account must match the Blob endpoint")
        self.management = management
        self.resource_group = resource_group
        self.account_name = account_name

    @classmethod
    def connect(
        cls, endpoint: str, container: str, credential: TokenCredential | None = None,
        *, subscription_id: str, resource_group: str, account_name: str,
    ) -> "AzureBlobs":
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme != "https" or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("Credential-free HTTPS Blob endpoint required")
        credential = credential if credential is not None else DefaultAzureCredential()
        return cls(BlobServiceClient(
            endpoint, credential=credential,
            max_single_put_size=MAX_BYTES, max_block_size=MAX_BYTES,
            retry_total=0, connection_timeout=5, read_timeout=30, logging_enable=False,
        ), container, StorageManagementClient(
            credential, subscription_id, retry_total=0, connection_timeout=5,
            read_timeout=30, logging_enable=False,
        ), resource_group, account_name)

    def check_policy(self) -> None:
        # The data-plane SDK omits versioning/restore settings. Read the actual ARM policy.
        properties = self.management.blob_services.get_service_properties(
            self.resource_group, self.account_name,
        )
        if (
            properties.is_versioning_enabled is not False
            or properties.automatic_snapshot_policy_enabled
            or (properties.delete_retention_policy and properties.delete_retention_policy.enabled)
            or (properties.restore_policy and properties.restore_policy.enabled)
        ):
            raise StoragePolicyError("Temporary storage must disable retained versions and recovery")
        account = self.management.storage_accounts.get_properties(self.resource_group, self.account_name)
        if (
            account.allow_blob_public_access is not False or account.allow_shared_key_access is not False
            or account.is_hns_enabled
            or not account.primary_endpoints
            or account.primary_endpoints.blob.rstrip("/") != self.client.url.rstrip("/")
        ):
            raise StoragePolicyError("Require the private, no-Shared-Key, non-HNS policy account")
        container = self.container.get_container_properties(timeout=30)
        if container.get("public_access"):
            raise StoragePolicyError("Temporary container must be private")

    def initialize(self, name: str, lease_id: str) -> str:
        # Exactly one create-only, zero-byte request. Ambiguous failures are NOT retried.
        blob = self.container.get_blob_client(name)
        created = blob.upload_blob(b"", overwrite=False, timeout=30)
        blob.acquire_lease(lease_duration=-1, lease_id=lease_id, timeout=30)
        return created["etag"]

    def put(self, name: str, data: bytes, lease_id: str, etag: str) -> str:
        if not isinstance(data, bytes) or not 0 < len(data) <= MAX_BYTES:
            raise ValueError("A nonempty, bounded bytes payload is required")
        if not etag or etag == "*":
            raise ValueError("Concrete Blob ETag required")
        result = self.container.get_blob_client(name).upload_blob(
            data, overwrite=True, lease=lease_id, etag=etag,
            match_condition=MatchConditions.IfNotModified, timeout=30,
            content_settings=ContentSettings(content_type="application/octet-stream"),
        )
        return result["etag"]

    def download(self, name: str, etag: str) -> bytes:
        blob = self.container.get_blob_client(name)
        properties = blob.get_blob_properties(
            etag=etag, match_condition=MatchConditions.IfNotModified, timeout=30,
        )
        if not 0 < properties.size <= MAX_BYTES:
            raise StoragePolicyError("Stored payload exceeds bounded read size")
        return blob.download_blob(
            etag=etag, match_condition=MatchConditions.IfNotModified,
            max_concurrency=1, timeout=30,
        ).readall()

    def delete(self, name: str, lease_id: str) -> None:
        blob = self.container.get_blob_client(name)
        pages = self.container.list_blobs(
            name_starts_with=name, include=["versions", "deleted"],
            results_per_page=100, timeout=30,
        ).by_page()
        for item in next(pages):
            if item.name == name and (item.version_id or item.deleted):
                raise StoragePolicyError("Retained versions require explicit operator removal")
        if pages.continuation_token:
            raise StoragePolicyError("Unexpected retained-copy inventory exceeds deletion bound")
        # Do not use an ETag here: any PUT that wins before this DELETE is removed.
        # Later PUTs carry a lease + If-Match and cannot recreate a missing blob.
        try:
            blob.delete_blob(lease=lease_id, delete_snapshots="include", timeout=30)
        except ResourceNotFoundError as exc:
            if getattr(exc, "error_code", None) != "BlobNotFound":
                raise

    def read_access(self, name: str, start: datetime, expiry: datetime) -> Access:
        blob = self.container.get_blob_client(name)
        key = self.client.get_user_delegation_key(start, expiry, timeout=30)
        token = generate_blob_sas(
            account_name=blob.account_name, container_name=blob.container_name,
            blob_name=blob.blob_name, user_delegation_key=key,
            permission=BlobSasPermissions(read=True), start=start, expiry=expiry,
            protocol="https", cache_control="no-store",
            content_disposition="attachment", content_type="application/octet-stream",
        )
        return Access(f"{blob.url}?{token}", expiry)

    def close(self) -> None:
        self.client.close()
        self.management.close()
