from datetime import datetime, timedelta, timezone
from uuid import uuid4

from azure.core.exceptions import HttpResponseError, ResourceModifiedError
import pytest

from auth import Principal
from storage.artifacts import Artifacts, DrainPending
from storage.azure import Page
from storage.blob import Access, MAX_BYTES, StoragePolicyError
from storage.models import ArtifactKind, ArtifactReference, State
from storage.repository import Conflict, Inactive, Repository
from storage.retention import RetentionUnavailable, Settings, run_sweep, sweep_user
from storage.tests.test_repository import MemoryTable, HASH


class PagedTable(MemoryTable):
    def page(self, partition, prefix="", *, continuation=None, limit=100):
        if not 1 <= limit <= 100:
            raise ValueError("Invalid page size")
        rows = sorted(self.query(partition, prefix), key=lambda row: row.properties["RowKey"])
        if continuation:
            rows = [row for row in rows if row.properties["RowKey"] > continuation["after"]]
        selected = rows[:limit]
        token = {"after": selected[-1].properties["RowKey"]} if len(rows) > limit else None
        return Page(tuple(selected), token)


class LeasedBlobs:
    """Synthetic atomic lease/conditional semantics; not a live Azure test."""

    def __init__(self):
        self.rows = {}
        self.revision = 0
        self.failure = None
        self.before_put = None
        self.before_initialize = None
        self.policy = True
        self.grants = []

    def check_policy(self):
        if not self.policy:
            raise StoragePolicyError("Synthetic unsafe container")
        if self.failure:
            raise self.failure

    def initialize(self, name, lease_id):
        if self.before_initialize:
            hook, self.before_initialize = self.before_initialize, None
            hook()
        self.revision += 1
        etag = f'"{self.revision}"'
        assert name not in self.rows
        self.rows[name] = (b"", lease_id, etag)
        return etag

    def put(self, name, data, lease_id, etag):
        if self.before_put:
            hook, self.before_put = self.before_put, None
            hook()
        if self.failure:
            raise self.failure
        existing = self.rows.get(name)
        if existing is None or existing[1:] != (lease_id, etag):
            raise ResourceModifiedError("Synthetic missing lease or stale ETag")
        self.revision += 1
        new_etag = f'"{self.revision}"'
        self.rows[name] = (data, lease_id, new_etag)
        return new_etag

    def download(self, name, etag):
        if self.failure:
            raise self.failure
        data, _, current = self.rows[name]
        if current != etag:
            raise ResourceModifiedError("Synthetic stale read")
        return data

    def delete(self, name, lease_id):
        if self.failure:
            raise self.failure
        if name in self.rows:
            assert self.rows[name][1] == lease_id
            del self.rows[name]

    def read_access(self, name, start, expiry):
        access = Access(f"https://synthetic.invalid/{name}?sp=r", expiry)
        self.grants.append(access)
        return access


@pytest.fixture
def context():
    table, blobs = PagedTable(), LeasedBlobs()
    time = [datetime(2026, 11, 21, tzinfo=timezone.utc)]
    repository = Repository(table, Principal("https://issuer.test/", "user-a"), lambda: time[0])
    artifacts = Artifacts(repository, blobs)
    deck = repository.create_deck()
    job = repository.create_job(deck, HASH)
    return repository, artifacts, table, blobs, time, deck, job


def store_original(context):
    repository, artifacts, _, _, _, deck, job = context
    reference = artifacts.reserve(deck, job, ArtifactKind.ORIGINAL, repository.get_job(deck, job).etag)
    artifacts.put(deck, job, reference, b"synthetic original", repository.get_job(deck, job).etag)
    return reference


def ready(context):
    repository, artifacts, _, _, _, deck, job = context
    token = repository.claim_job(deck, job, repository.get_job(deck, job).etag)
    for state in (State.EXTRACTING, State.GENERATING):
        repository.transition_job(
            deck, job, repository.get_job(deck, job).etag, state, lease_token=token,
        )
    refs = []
    for kind in (ArtifactKind.EXTRACTED, ArtifactKind.RESULT, ArtifactKind.REVIEW_IMAGE):
        reference = artifacts.reserve(
            deck, job, kind, repository.get_job(deck, job).etag, lease_token=token,
        )
        artifacts.put(
            deck, job, reference, b"synthetic payload", repository.get_job(deck, job).etag,
            lease_token=token,
        )
        refs.append(reference)
    repository.transition_job(
        deck, job, repository.get_job(deck, job).etag, State.READY, lease_token=token, result=refs[1],
    )
    return refs


def test_every_class_private_locator_and_issuer_subject_isolation(context):
    repository, artifacts, table, blobs, time, deck, job = context
    original = store_original(context)
    refs = ready(context)
    for name in blobs.rows:
        partition, deck_id, job_id, kind, artifact_id = name.split("/")
        assert partition == repository.partition
        assert deck_id == deck and job_id == job
        assert kind in {kind.value for kind in ArtifactKind}
        assert len(artifact_id) == 36
        assert "user-a" not in name
    for principal in (
        Principal("https://issuer.test/", "user-b"), Principal("https://other.test/", "user-a"),
    ):
        other = Artifacts(Repository(table, principal, lambda: time[0]), blobs)
        for reference in (original, *refs):
            other.delete(deck, job, reference)
            with pytest.raises(Inactive):
                other.read_access(deck, job, reference)
            with pytest.raises(Inactive):
                other.put(deck, job, reference, b"forbidden", repository.get_job(deck, job).etag)
        assert other.delete_deck(deck)
    assert len(blobs.rows) == 4
    assert artifacts.read_access(deck, job, refs[1]).expires_at == time[0] + timedelta(minutes=5)
    assert "sp=r" not in repr(blobs.grants[-1])


def test_exact_expiry_and_bounds_do_not_trust_reference_deadline(context):
    repository, artifacts, table, blobs, time, deck, job = context
    original = store_original(context)
    with pytest.raises(ValueError):
        artifacts.reserve(
            deck, job, ArtifactKind.ORIGINAL, repository.get_job(deck, job).etag,
            lifetime=timedelta(days=1, seconds=1),
        )
    forged = ArtifactReference(original.artifact_id, original.kind, time[0] + timedelta(days=100))
    time[0] = original.expires_at
    with pytest.raises(Inactive):
        artifacts.put(deck, job, forged, b"late", repository.get_job(deck, job).etag)
    artifacts.delete(deck, job, original)
    artifacts.delete(deck, job, original)
    assert blobs.rows == {}
    assert not any(row.properties["Kind"] == "BlobArtifacts" for row in table.rows.values())


def test_processing_completion_deletes_only_originals_and_extraction_intermediates(context):
    repository, artifacts, table, blobs, time, deck, job = context
    store_original(context)
    refs = ready(context)
    assert artifacts.processing_completed(deck, job)
    assert {name.split("/")[-2] for name in blobs.rows} == {"result", "review_image"}
    with pytest.raises(Inactive):
        artifacts.read_access(deck, job, refs[0])
    time[0] += timedelta(days=7)
    for reference in refs[1:]:
        with pytest.raises(Inactive):
            artifacts.read_access(deck, job, reference)
    sweep_user(repository, blobs)
    assert blobs.rows == {}
    assert repository.get_job(deck, job).properties["State"] == State.READY


def test_anki_ack_caps_existing_results_and_immediately_deletes_backend_media(context):
    repository, artifacts, _, blobs, time, deck, job = context
    refs = ready(context)
    artifacts.processing_completed(deck, job)
    with pytest.raises(Conflict):
        artifacts.import_committed(deck, job)
    time[0] += timedelta(hours=1)
    repository.transition_job(deck, job, repository.get_job(deck, job).etag, State.COMPLETED)
    for reference in refs[1:]:
        row = artifacts._active(deck, job, reference)
        assert artifacts.effective_expiry(row.properties) == time[0] + timedelta(days=1)
    assert artifacts.import_committed(deck, job)
    assert blobs.rows == {}


def test_failed_files_are_physically_removed_by_bounded_sweep(context):
    repository, artifacts, _, blobs, time, deck, job = context
    store_original(context)
    token = repository.claim_job(deck, job, repository.get_job(deck, job).etag)
    repository.transition_job(
        deck, job, repository.get_job(deck, job).etag, State.FAILED, lease_token=token,
    )
    time[0] += timedelta(hours=23)
    sweep_user(repository, blobs)
    assert blobs.rows == {}
    assert repository.get_job(deck, job).properties["State"] == State.FAILED


def test_deleted_blob_rejects_inflight_put_and_new_workers(context):
    repository, artifacts, table, blobs, _, deck, job = context
    reference = artifacts.reserve(deck, job, ArtifactKind.ORIGINAL, repository.get_job(deck, job).etag)
    row = artifacts._active(deck, job, reference)
    name = artifacts._name(row.properties)
    blobs.before_put = lambda: artifacts.delete_deck(deck)
    with pytest.raises(ResourceModifiedError):
        artifacts.put(deck, job, reference, b"racing content", repository.get_job(deck, job).etag)
    assert blobs.rows == {} and table.rows == {}
    with pytest.raises(ResourceModifiedError):
        blobs.put(name, b"stale content", row.properties["LeaseId"], row.properties["BlobETag"])
    with pytest.raises(Inactive):
        artifacts.reserve(deck, job, ArtifactKind.ORIGINAL, 'W/"old"')
    assert artifacts.delete_deck(deck)


def test_put_that_wins_before_delete_is_removed_and_never_published(context):
    repository, artifacts, table, blobs, _, deck, job = context
    reference = artifacts.reserve(deck, job, ArtifactKind.ORIGINAL, repository.get_job(deck, job).etag)
    row = artifacts._active(deck, job, reference)
    blobs.put(artifacts._name(row.properties), b"raced committed PUT", row.properties["LeaseId"], row.properties["BlobETag"])
    assert artifacts.delete_deck(deck)
    assert blobs.rows == {} and table.rows == {}


def test_initialization_racing_delete_retains_guard_until_acknowledged(context):
    repository, artifacts, table, blobs, _, deck, job = context

    def race():
        with pytest.raises(DrainPending):
            artifacts.delete_deck(deck)
        with pytest.raises(Conflict):
            repository.finish_deck_deletion(deck)

    blobs.before_initialize = race
    with pytest.raises(Inactive):
        artifacts.reserve(deck, job, ArtifactKind.ORIGINAL, repository.get_job(deck, job).etag)
    assert repository._optional("d:" + deck).properties["State"] == "deleting"
    assert artifacts.delete_deck(deck)
    assert blobs.rows == {} and table.rows == {}


def test_delete_outage_and_lost_table_ack_keep_guard_and_recover(context):
    repository, artifacts, table, blobs, _, deck, job = context
    reference = store_original(context)
    blobs.failure = HttpResponseError("sensitive synthetic detail")
    with pytest.raises(HttpResponseError):
        artifacts.delete_deck(deck)
    assert repository._optional("d:" + deck).properties["State"] == "deleting"
    with pytest.raises(Inactive):
        artifacts.put(deck, job, reference, b"late content", 'W/"old"')
    blobs.failure = None
    original_delete = blobs.delete

    def lost_ack(name, lease_id):
        original_delete(name, lease_id)
        table.failure = HttpResponseError("sensitive Table outage")

    blobs.delete = lost_ack
    with pytest.raises(HttpResponseError):
        artifacts.delete_deck(deck)
    assert blobs.rows == {}
    table.failure = None
    blobs.delete = original_delete
    assert artifacts.delete_deck(deck)
    assert table.rows == {}


def test_expired_worker_and_immutable_payload_reject_rewrites(context):
    repository, artifacts, _, blobs, time, deck, job = context
    original = store_original(context)
    with pytest.raises(Conflict):
        artifacts.put(deck, job, original, b"overwrite", repository.get_job(deck, job).etag)
    token = repository.claim_job(deck, job, repository.get_job(deck, job).etag)
    reference = artifacts.reserve(
        deck, job, ArtifactKind.EXTRACTED, repository.get_job(deck, job).etag, lease_token=token,
    )
    time[0] += timedelta(minutes=5)
    with pytest.raises(Conflict):
        artifacts.put(
            deck, job, reference, b"stale", repository.get_job(deck, job).etag, lease_token=token,
        )
    assert [data for data, _, _ in blobs.rows.values()].count(b"") == 1


def test_unsafe_policy_and_size_fail_before_content_write(context):
    repository, artifacts, _, blobs, _, deck, job = context
    reference = artifacts.reserve(deck, job, ArtifactKind.ORIGINAL, repository.get_job(deck, job).etag)
    for data in (b"", b"x" * (MAX_BYTES + 1)):
        with pytest.raises(ValueError):
            artifacts.put(deck, job, reference, data, repository.get_job(deck, job).etag)
    blobs.policy = False
    with pytest.raises(StoragePolicyError):
        artifacts.put(deck, job, reference, b"synthetic", repository.get_job(deck, job).etag)
    assert list(blobs.rows.values())[0][0] == b""


def test_physical_metadata_purge_is_paged_resumable_and_preserves_only_deck_guard(context):
    repository, artifacts, table, blobs, time, deck, job = context
    for _ in range(8):
        repository.create_job(deck, HASH)
    time[0] += timedelta(days=30) - timedelta(minutes=30)
    first = sweep_user(repository, blobs, limit=3)
    assert not first.complete and first.inspected == 3
    assert repository._optional("r:retention").properties["Cursor"]
    for _ in range(5):
        result = sweep_user(repository, blobs, limit=3)
        if result.complete:
            break
    assert result.complete
    assert {row.properties["Kind"] for row in table.rows.values()} == {"Decks", "RetentionCursor"}
    assert set(repository.get_deck(deck).properties) == {"PartitionKey", "RowKey", "Kind", "DeckId", "State"}


def test_user_outage_is_content_free_does_not_hide_failure_and_other_user_progresses(context, caplog):
    repository, artifacts, table, blobs, time, deck, job = context
    store_original(context)
    time[0] += timedelta(days=1)
    other = Principal("https://issuer.test/", "user-b")
    blobs.failure = HttpResponseError("sensitive study content")
    factory = lambda table, user: Repository(table, user, lambda: time[0])
    with pytest.raises(RetentionUnavailable):
        run_sweep(table, blobs, (Principal("https://issuer.test/", "user-a"), other), repository_factory=factory)
    assert "sensitive" not in caplog.text and "user-a" not in caplog.text
    assert Repository(table, other)._optional("r:retention") is not None
    blobs.failure = None
    run_sweep(table, blobs, (Principal("https://issuer.test/", "user-a"), other), repository_factory=factory)
    assert blobs.rows == {}


def test_inventory_fails_closed_and_never_discovers_account_users(monkeypatch):
    monkeypatch.setenv("RETENTION_USERS", "[]")
    with pytest.raises(RetentionUnavailable):
        Settings.from_environment()
    with pytest.raises(RetentionUnavailable):
        run_sweep(PagedTable(), LeasedBlobs(), ())


def test_ambiguous_initializer_blocks_finalization_but_not_other_expiry_work(context, monkeypatch, caplog):
    repository, artifacts, table, blobs, time, deck, job = context
    store_original(context)

    def ambiguous(*args):
        raise HttpResponseError("synthetic ambiguous initial request")

    monkeypatch.setattr(blobs, "initialize", ambiguous)
    with pytest.raises(HttpResponseError):
        artifacts.reserve(deck, job, ArtifactKind.ORIGINAL, repository.get_job(deck, job).etag)
    repository.begin_deck_deletion(deck)
    with pytest.raises(Conflict):
        repository.finish_deck_deletion(deck)
    time[0] += timedelta(days=30)
    with pytest.raises(RetentionUnavailable):
        sweep_user(repository, blobs)
    assert blobs.rows == {}
    assert repository._optional("d:" + deck).properties["State"] == "deleting"
    assert not any(row.properties["Kind"] == "Jobs" for row in table.rows.values())
    assert "retention_record_failed" in caplog.text
    assert not repository._optional("r:retention").properties.get("Cursor")


def test_multi_page_deck_drain_is_bounded_and_cannot_reopen_for_new_writes(context):
    repository, artifacts, table, blobs, _, deck, job = context
    for _ in range(10):
        artifacts.reserve(deck, job, ArtifactKind.ORIGINAL, repository.get_job(deck, job).etag)
    assert artifacts.delete_deck(deck, limit=3) is False
    assert len(blobs.rows) == 7
    with pytest.raises(Inactive):
        artifacts.reserve(deck, job, ArtifactKind.ORIGINAL, 'W/"stale"')
    for _ in range(5):
        if artifacts.delete_deck(deck, limit=3):
            break
    assert blobs.rows == {} and table.rows == {}


def test_monitored_cursor_reports_overdue_cycle_after_advancing(context):
    repository, _, table, blobs, time, deck, job = context
    for _ in range(5):
        repository.create_job(deck, HASH)
    sweep_user(repository, blobs, limit=2)
    cursor = repository._optional("r:retention").properties["Cursor"]
    time[0] += timedelta(minutes=16)
    with pytest.raises(RetentionUnavailable, match="cycle_overdue"):
        sweep_user(repository, blobs, limit=2)
    assert repository._optional("r:retention").properties["Cursor"] != cursor


def test_physical_purge_default_cutoff_works_with_a_real_advancing_clock(context):
    repository, _, table, _, time, deck, job = context
    time[0] += timedelta(days=30)

    def advancing():
        time[0] += timedelta(microseconds=1)
        return time[0]

    repository.clock = advancing
    row = table.get(repository.partition, f"j:{deck}:{job}")
    assert repository.purge_entity(row)
    assert repository._optional(f"j:{deck}:{job}") is None


@pytest.mark.parametrize("mutation,verification,expected", [
    (
        '        self.blobs.delete(self._name(row.properties), row.properties["LeaseId"])',
        test_deleted_blob_rejects_inflight_put_and_new_workers, AssertionError,
    ),
    (
        '            or self.effective_expiry(row.properties) <= self.repository._now()',
        test_processing_completion_deletes_only_originals_and_extraction_intermediates,
        pytest.fail.Exception,
    ),
])
def test_real_source_mutations_break_physical_deletion_and_exact_expiry_gates(context, mutation, verification, expected):
    import storage.artifacts as module
    from pathlib import Path
    source = Path(module.__file__).read_text()
    assert source.count(mutation) == 1
    namespace = vars(module).copy()
    exec(compile(source.replace(mutation, ""), module.__file__, "exec"), namespace)
    repository, _, table, blobs, time, deck, job = context
    mutated = (repository, namespace["Artifacts"](repository, blobs), table, blobs, time, deck, job)
    with pytest.raises(expected):
        verification(mutated)
