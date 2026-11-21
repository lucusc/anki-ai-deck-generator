from datetime import datetime, timedelta
from uuid import uuid4

from .azure import Snapshot, Write
from .blob import Access, Blobs, MAX_BYTES
from .models import ArtifactKind, ArtifactReference, State, identifier
from .repository import Conflict, Inactive, Repository, _keys


class DrainPending(Exception):
    """An initializer must settle before its empty placeholder can safely be removed."""


class Artifacts:
    """Private operations derive every locator from the authenticated repository."""

    def __init__(self, repository: Repository, blobs: Blobs):
        self.repository = repository
        self.blobs = blobs

    def _row(self, deck: str, job: str, reference: ArtifactReference) -> str:
        if not isinstance(reference.kind, ArtifactKind):
            raise ValueError("Explicit artifact kind required")
        return (
            f"b:{identifier(deck)}:{identifier(job)}:"
            f"{reference.kind.value}:{identifier(reference.artifact_id)}"
        )

    def _name(self, properties: dict) -> str:
        return "/".join((
            self.repository.partition, properties["DeckId"], properties["JobId"],
            properties["ArtifactKind"], properties["ArtifactId"],
        ))

    def _write_job(
        self, deck: str, job: str, kind: ArtifactKind, etag: str, token: str | None,
    ) -> Snapshot:
        repository = self.repository
        current = repository.get_job(deck, job)
        if kind == ArtifactKind.ORIGINAL and current.properties["State"] == State.QUEUED:
            if current.etag != etag:
                raise Conflict("Upload job ETag is stale")
            return current
        if token is None:
            raise Conflict("Current worker ownership required")
        return repository._worker(deck, job, etag, token)

    def reserve(
        self, deck: str, job: str, kind: ArtifactKind, job_etag: str, *,
        lease_token: str | None = None, lifetime: timedelta | None = None,
    ) -> ArtifactReference:
        if not isinstance(kind, ArtifactKind):
            raise ValueError("Explicit artifact kind required")
        repository = self.repository
        guard = repository._deck(deck)
        current = self._write_job(deck, job, kind, job_etag, lease_token)
        maximum = timedelta(days=7 if kind in {
            ArtifactKind.RESULT, ArtifactKind.REVIEW_IMAGE,
        } else 1)
        lifetime = maximum if lifetime is None else lifetime
        if not timedelta(0) < lifetime <= maximum:
            raise ValueError("Artifact lifetime exceeds temporary retention maximum")
        now = repository._now()
        reference = ArtifactReference(
            str(uuid4()), kind, min(now + lifetime, current.properties["ExpiresAt"]),
        )
        properties = {
            **_keys(repository.partition, self._row(deck, job, reference)),
            "Kind": "BlobArtifacts", "DeckId": deck, "JobId": job,
            **reference.properties(now), "State": "initializing",
            "CreatedAt": now, "LeaseId": str(uuid4()),
        }
        self.blobs.check_policy()
        repository._commit(guard, [Write("create", properties)])
        # No content authority exists until BOTH Blob operations have acknowledged.
        etag = self.blobs.initialize(self._name(properties), properties["LeaseId"])
        latest = repository._optional(properties["RowKey"])
        if latest is None or latest.properties["State"] != "initializing":
            raise Conflict("Initialization ownership changed")
        guard = repository._optional("d:" + deck)
        if guard is None:
            raise Conflict("Initialization guard was incorrectly removed")
        blocked = (
            guard.properties["State"] != "active"
            or latest.properties.get("DeleteRequested")
            or self.effective_expiry(latest.properties) <= repository._now()
        )
        properties = {
            **latest.properties, "State": "deleting" if blocked else "open",
            "BlobETag": etag,
        }
        repository._commit(guard, [Write("replace", properties, latest.etag)])
        if blocked:
            raise Inactive("Initialization settled after deletion or expiry")
        return reference

    def effective_expiry(self, properties: dict) -> datetime:
        repository = self.repository
        expiry = properties["ArtifactExpiresAt"]
        guard = repository._optional("d:" + properties["DeckId"])
        job = repository._optional(f"j:{properties['DeckId']}:{properties['JobId']}")
        if (
            guard is None or guard.properties["State"] != "active"
            or job is None or job.properties["State"] == State.DELETED
        ):
            return repository._now()
        values = job.properties
        expiry = min(expiry, values["ExpiresAt"])
        if "FailedAt" in values:
            expiry = min(expiry, values["FailedAt"] + timedelta(days=1))
        if "ImportCommittedAt" in values:
            expiry = min(expiry, values["ImportCommittedAt"] + timedelta(days=1))
        if properties["ArtifactKind"] in {"original", "extracted"}:
            if "ProcessingCompletedAt" in values:
                expiry = min(expiry, values["ProcessingCompletedAt"])
        return expiry

    def _active(self, deck: str, job: str, reference: ArtifactReference) -> Snapshot:
        self.repository.get_job(deck, job)
        row = self.repository._optional(self._row(deck, job, reference))
        if (
            row is None or row.properties["ArtifactKind"] != reference.kind.value
            or row.properties["State"] not in {"open", "stored"}
            or self.effective_expiry(row.properties) <= self.repository._now()
        ):
            raise Inactive("Artifact deleted or expired; re-upload is required")
        return row

    def put(
        self, deck: str, job: str, reference: ArtifactReference, data: bytes,
        job_etag: str, *, lease_token: str | None = None,
    ) -> None:
        if not isinstance(data, bytes) or not 0 < len(data) <= MAX_BYTES:
            raise ValueError("A nonempty, bounded bytes payload is required")
        repository = self.repository
        guard = repository._deck(deck)
        self._write_job(deck, job, reference.kind, job_etag, lease_token)
        row = self._active(deck, job, reference)
        if row.properties["State"] != "open":
            raise Conflict("Artifact is immutable once stored")
        self.blobs.check_policy()
        etag = self.blobs.put(
            self._name(row.properties), data, row.properties["LeaseId"],
            row.properties["BlobETag"],
        )
        repository._commit(guard, [Write("replace", {
            **row.properties, "State": "stored", "BlobETag": etag,
        }, row.etag)])

    def download(
        self, deck: str, job: str, reference: ArtifactReference, job_etag: str,
        lease_token: str,
    ) -> bytes:
        self.repository._worker(deck, job, job_etag, lease_token)
        row = self._active(deck, job, reference)
        if row.properties["State"] != "stored":
            raise Inactive("Artifact upload not acknowledged")
        data = self.blobs.download(self._name(row.properties), row.properties["BlobETag"])
        self._active(deck, job, reference)
        return data

    def read_access(
        self, deck: str, job: str, reference: ArtifactReference, *,
        lifetime: timedelta = timedelta(minutes=5),
    ) -> Access:
        if not timedelta(0) < lifetime <= timedelta(minutes=5):
            raise ValueError("Read access must be positive and at most five minutes")
        current = self.repository.get_job(deck, job)
        if (
            reference.kind not in {ArtifactKind.RESULT, ArtifactKind.REVIEW_IMAGE}
            or current.properties["State"] not in {State.READY, State.COMPLETED}
        ):
            raise Inactive("Only review artifacts have client read access")
        row = self._active(deck, job, reference)
        if row.properties["State"] != "stored":
            raise Inactive("Artifact upload not acknowledged")
        now = self.repository._now()
        expiry = min(now + lifetime, self.effective_expiry(row.properties))
        self.blobs.check_policy()
        access = self.blobs.read_access(self._name(row.properties), now, expiry)
        self._active(deck, job, reference)
        return access

    def delete(self, deck: str, job: str, reference: ArtifactReference) -> None:
        row = self.repository._optional(self._row(deck, job, reference))
        if row is None:
            return
        if row.properties["ArtifactKind"] != reference.kind.value:
            raise Inactive("Artifact class does not match")
        self._delete_row(row)

    def _delete_row(self, row: Snapshot) -> None:
        repository = self.repository
        guard = repository._optional("d:" + row.properties["DeckId"])
        if guard is None:
            raise Inactive("Missing artifact cleanup guard")
        if row.properties["State"] == "initializing":
            if not row.properties.get("DeleteRequested"):
                repository._commit(guard, [Write("replace", {
                    **row.properties, "DeleteRequested": True,
                }, row.etag)])
            raise DrainPending("Initializer not settled; retain deletion guard")
        if row.properties["State"] != "deleting":
            repository._commit(guard, [Write("replace", {
                **row.properties, "State": "deleting",
            }, row.etag)])
            row = repository.table.get(repository.partition, row.properties["RowKey"])
        self.blobs.check_policy()
        self.blobs.delete(self._name(row.properties), row.properties["LeaseId"])
        guard = repository._optional("d:" + row.properties["DeckId"])
        if guard is None:
            raise Inactive("Missing artifact cleanup guard")
        repository._commit(guard, [Write("delete", _keys(
            repository.partition, row.properties["RowKey"],
        ), row.etag)])

    def processing_completed(self, deck: str, job: str, *, limit: int = 100) -> bool:
        """Call immediately after the persisted READY transition, not only from the timer."""
        current = self.repository.get_job(deck, job)
        if "ProcessingCompletedAt" not in current.properties:
            raise Conflict("Processing completion must be persisted first")
        return self.cleanup_job(deck, job, limit=limit)

    def import_committed(self, deck: str, job: str, *, limit: int = 100) -> bool:
        current = self.repository.get_job(deck, job)
        if "ImportCommittedAt" not in current.properties:
            raise Conflict("Anki commit acknowledgement must be persisted first")
        # Delete immediately; the 24h maximum is not a reason to delay deletion.
        return self.cleanup_job(deck, job, limit=limit, force=True)

    def cleanup_job(self, deck: str, job: str, *, limit: int = 100, force: bool = False) -> bool:
        complete = True
        for kind in ArtifactKind:
            if not force and kind in {ArtifactKind.RESULT, ArtifactKind.REVIEW_IMAGE}:
                continue
            page = self.repository.table.page(
                self.repository.partition,
                f"b:{identifier(deck)}:{identifier(job)}:{kind.value}:", limit=limit,
            )
            for row in page.rows:
                if force or self.effective_expiry(row.properties) <= self.repository._now():
                    self._delete_row(row)
            complete = complete and page.continuation is None
        return complete

    def delete_deck(self, deck: str, *, limit: int = 100) -> bool:
        repository = self.repository
        repository.begin_deck_deletion(deck)
        page = repository.table.page(repository.partition, f"b:{identifier(deck)}:", limit=limit)
        for row in page.rows:
            self._delete_row(row)
        if page.continuation is not None:
            return False
        return repository.finish_deck_deletion(deck, limit=limit)
