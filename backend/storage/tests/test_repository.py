from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from azure.core.exceptions import (
    HttpResponseError, ResourceExistsError, ResourceModifiedError, ResourceNotFoundError,
)
import pytest

from auth import Principal
from storage.azure import Snapshot
from storage.models import (
    ArtifactKind, ArtifactReference, Provenance, State, Usage, user_partition,
)
from storage.repository import Conflict, Inactive, Repository


HASH = "a" * 64
OTHER_HASH = "b" * 64
COMPATIBILITY = "c" * 64
PROVENANCE = Provenance("native-v1", "prompt-v1", "model-v1", "native", page=3)


class MemoryTable:
    """Atomic ETag test double, not Azure integration evidence."""

    def __init__(self):
        self.rows = {}
        self.revision = 0
        self.before_commit = None
        self.failure = None
        self.batch_sizes = []

    def get(self, partition, row):
        if self.failure:
            raise self.failure
        try:
            return deepcopy(self.rows[partition, row])
        except KeyError as exc:
            error = ResourceNotFoundError("Synthetic missing row")
            error.error_code = "ResourceNotFound"
            raise error from exc

    def query(self, partition, prefix=""):
        if self.failure:
            raise self.failure
        for (pk, rk), value in list(self.rows.items()):
            if pk == partition and rk.startswith(prefix):
                yield deepcopy(value)

    def transact(self, writes):
        if self.failure:
            raise self.failure
        if self.before_commit:
            hook, self.before_commit = self.before_commit, None
            hook()
        assert len(writes) <= 100
        assert len({write.properties["PartitionKey"] for write in writes}) == 1
        assert len({write.properties["RowKey"] for write in writes}) == len(writes)
        self.batch_sizes.append(len(writes))
        for write in writes:
            key = write.properties["PartitionKey"], write.properties["RowKey"]
            existing = self.rows.get(key)
            if write.operation == "create":
                if existing:
                    raise ResourceExistsError("Synthetic duplicate row")
            elif existing is None or existing.etag != write.etag:
                raise ResourceModifiedError("Synthetic ETag conflict")
        for write in writes:
            key = write.properties["PartitionKey"], write.properties["RowKey"]
            self.revision += 1
            if write.operation == "delete":
                del self.rows[key]
            else:
                self.rows[key] = Snapshot(deepcopy(write.properties), f'W/"{self.revision}"')


@pytest.fixture
def context():
    table = MemoryTable()
    time = [datetime(2026, 11, 21, tzinfo=timezone.utc)]
    repository = Repository(table, Principal("https://issuer.test/", "user-a"), lambda: time[0])
    return repository, table, time


def extracting(repository, deck=None):
    deck = deck or repository.create_deck()
    job = repository.create_job(deck, HASH)
    token = repository.claim_job(deck, job, repository.get_job(deck, job).etag)
    repository.transition_job(
        deck, job, repository.get_job(deck, job).etag, State.EXTRACTING, lease_token=token,
    )
    return deck, job, token


def generated(repository, now, deck=None, card_hash=HASH):
    deck, job, token = extracting(repository, deck)
    document = repository.create_document(
        deck, job, repository.get_job(deck, job).etag, token,
        source_hash=HASH, compatibility_hash=COMPATIBILITY, provenance=PROVENANCE,
    )
    repository.transition_job(
        deck, job, repository.get_job(deck, job).etag, State.GENERATING, lease_token=token,
    )
    payload = ArtifactReference(str(uuid4()), ArtifactKind.RESULT, now + timedelta(days=7))
    card = repository.create_card(
        deck, job, repository.get_job(deck, job).etag, token,
        document_id=document, card_hash=card_hash, provenance=PROVENANCE, payload=payload,
    )
    repository.transition_job(
        deck, job, repository.get_job(deck, job).etag, State.READY, lease_token=token,
        usage=Usage(input_tokens=100, output_tokens=25, proposed_notes=1, generated_cards=2),
        result=payload,
    )
    return deck, job, document, card


def test_user_identity_pair_and_every_lookup_are_isolated(context):
    repository, table, time = context
    deck, job, document, card = generated(repository, time[0])
    repository.record_import(deck, card, repository.get_card(deck, card).etag, str(uuid4()))
    assert user_partition(Principal("ab", "c")) != user_partition(Principal("a", "bc"))
    for principal in (
        Principal("https://issuer.test/", "user-b"),
        Principal("https://other-issuer.test/", "user-a"),
    ):
        other = Repository(table, principal, lambda: time[0])
        assert list(other.list_decks()) == []
        for operation in (
            lambda: other.get_job(deck, job), lambda: other.get_document(deck, document),
            lambda: other.get_card(deck, card), lambda: other.find_card(deck, HASH),
            lambda: other.find_source(deck, HASH, COMPATIBILITY),
            lambda: other.create_job(deck, HASH),
        ):
            with pytest.raises(Inactive):
                operation()
        other.begin_deck_deletion(deck)
        other.finish_deck_deletion(deck)
    assert repository.get_job(deck, job).properties["State"] == State.READY
    assert "user-a" not in repository.partition


def test_concrete_entities_provenance_usage_references_and_hash_scope(context):
    repository, table, time = context
    deck, job, document, card = generated(repository, time[0])
    import_id = str(uuid4())
    assert repository.find_source(deck, HASH, COMPATIBILITY) is None
    assert repository.find_card(deck, HASH) is None
    repository.record_import(deck, card, repository.get_card(deck, card).etag, import_id)
    assert repository.get_job(deck, job).properties["InputTokens"] == 100
    assert repository.get_job(deck, job).properties["GeneratedCards"] == 2
    assert repository.get_document(deck, document).properties["Page"] == 3
    assert repository.get_card(deck, card).properties["ArtifactKind"] == "result"
    assert repository.find_card(deck, HASH).properties["ImportId"] == import_id
    assert repository.find_source(deck, HASH, OTHER_HASH) is None
    other_deck = repository.create_deck()
    assert repository.find_card(other_deck, HASH) is None
    assert repository.find_source(other_deck, HASH, COMPATIBILITY) is None
    kinds = {row.properties["Kind"] for row in table.rows.values()}
    assert kinds == {"Jobs", "Documents", "Cards", "Decks", "SourceHash", "CardHash"}
    assert list(repository.list_jobs(deck))[0].properties["JobId"] == job
    assert repository.get_card(deck, card).properties["State"] == State.COMPLETED


def test_claim_conflict_lease_expiry_and_stale_worker(context):
    repository, table, time = context
    deck, job, token = extracting(repository)
    stale = repository.get_job(deck, job)
    with pytest.raises(Conflict):
        repository.claim_job(deck, job, stale.etag)
    time[0] += timedelta(minutes=5)
    replacement = repository.claim_job(deck, job, stale.etag)
    with pytest.raises(Conflict):
        repository.transition_job(deck, job, stale.etag, State.GENERATING, lease_token=token)
    with pytest.raises(Conflict):
        repository.create_document(
            deck, job, repository.get_job(deck, job).etag, token,
            source_hash=HASH, compatibility_hash=COMPATIBILITY, provenance=PROVENANCE,
        )
    repository.transition_job(
        deck, job, repository.get_job(deck, job).etag, State.GENERATING, lease_token=replacement,
    )


def test_atomic_fence_rejects_worker_racing_deck_deletion(context):
    repository, table, time = context
    deck, job, token = extracting(repository)
    table.before_commit = lambda: repository.begin_deck_deletion(deck)
    with pytest.raises(ResourceModifiedError):
        repository.create_document(
            deck, job, repository.get_job(deck, job).etag, token,
            source_hash=HASH, compatibility_hash=COMPATIBILITY, provenance=PROVENANCE,
        )
    assert not any(row.properties["Kind"] == "Documents" for row in table.rows.values())
    with pytest.raises(Inactive):
        repository.get_job(deck, job)
    repository.finish_deck_deletion(deck)
    assert table.rows == {}


def test_atomic_job_transition_race_rolls_back(context):
    repository, table, time = context
    deck, job, token = extracting(repository)
    etag = repository.get_job(deck, job).etag
    table.before_commit = lambda: repository.transition_job(
        deck, job, etag, State.FAILED, lease_token=token,
    )
    with pytest.raises(ResourceModifiedError):
        repository.transition_job(deck, job, etag, State.GENERATING, lease_token=token)
    assert repository.get_job(deck, job).properties["State"] == State.FAILED
    with pytest.raises(Conflict):
        repository.transition_job(
            deck, job, repository.get_job(deck, job).etag, State.EXTRACTING, lease_token=token,
        )


def test_import_requires_ready_job_and_unique_hash_transaction(context):
    repository, table, time = context
    deck, job, document, card = generated(repository, time[0])
    import_id = str(uuid4())
    etag = repository.get_card(deck, card).etag
    repository.record_import(deck, card, etag, import_id)
    with pytest.raises(Conflict):
        repository.record_import(deck, card, etag, import_id)
    _, other_job, _, other_card = generated(repository, time[0], deck)
    with pytest.raises(ResourceExistsError):
        repository.record_import(
            deck, other_card, repository.get_card(deck, other_card).etag, str(uuid4()),
        )
    assert repository.get_card(deck, other_card).properties["State"] == State.READY
    assert repository.find_card(deck, HASH).properties["ImportId"] == import_id
    repository.transition_job(
        deck, other_job, repository.get_job(deck, other_job).etag, State.DELETED,
    )
    with pytest.raises(Inactive):
        repository.record_import(
            deck, other_card, repository.get_card(deck, other_card).etag, str(uuid4()),
        )


def test_retention_exact_boundary_minimal_dedupe_then_deck_deletion(context):
    repository, table, time = context
    deck, job, document, card = generated(repository, time[0])
    import_id = str(uuid4())
    repository.record_import(deck, card, repository.get_card(deck, card).etag, import_id)
    time[0] += timedelta(days=30)
    for operation in (
        lambda: repository.get_job(deck, job), lambda: repository.get_document(deck, document),
        lambda: repository.get_card(deck, card),
    ):
        with pytest.raises(Inactive):
            operation()
    assert repository.purge_expired() == 3
    assert repository.purge_expired() == 0
    assert set(repository.get_deck(deck).properties) == {
        "PartitionKey", "RowKey", "Kind", "DeckId", "State",
    }
    assert set(repository.find_card(deck, HASH).properties) == {
        "PartitionKey", "RowKey", "Kind", "CardHash", "ImportId",
    }
    assert set(repository.find_source(deck, HASH, COMPATIBILITY).properties) == {
        "PartitionKey", "RowKey", "Kind", "SourceHash", "CompatibilityHash",
    }
    repository.begin_deck_deletion(deck)
    repository.begin_deck_deletion(deck)
    with pytest.raises(Inactive):
        repository.find_card(deck, HASH)
    repository.finish_deck_deletion(deck)
    repository.finish_deck_deletion(deck)
    assert table.rows == {}
    with pytest.raises(Inactive):
        repository.create_job(deck, HASH)
    assert repository.create_deck() != deck


def test_purge_cannot_race_renewal_or_deletion(context):
    repository, table, time = context
    deck, job, token = extracting(repository)
    time[0] += timedelta(days=30)
    table.before_commit = lambda: repository.begin_deck_deletion(deck)
    with pytest.raises(ResourceModifiedError):
        repository.purge_expired()
    assert repository.purge_expired() == 1
    assert table.rows[repository.partition, "d:" + deck].properties["State"] == "deleting"
    repository.finish_deck_deletion(deck)
    assert table.rows == {}


def test_expiry_never_slides_on_transition_or_new_children(context):
    repository, table, time = context
    deck, job, token = extracting(repository)
    expires = repository.get_job(deck, job).properties["ExpiresAt"]
    time[0] += timedelta(days=29)
    token = repository.claim_job(deck, job, repository.get_job(deck, job).etag)
    document = repository.create_document(
        deck, job, repository.get_job(deck, job).etag, token,
        source_hash=HASH, compatibility_hash=COMPATIBILITY, provenance=PROVENANCE,
        original=ArtifactReference(str(uuid4()), ArtifactKind.ORIGINAL, time[0] + timedelta(days=1)),
    )
    assert repository.get_document(deck, document).properties["ExpiresAt"] == expires
    repository.transition_job(
        deck, job, repository.get_job(deck, job).etag, State.GENERATING, lease_token=token,
    )
    card = repository.create_card(
        deck, job, repository.get_job(deck, job).etag, token,
        document_id=document, card_hash=HASH, provenance=PROVENANCE,
        payload=ArtifactReference(str(uuid4()), ArtifactKind.RESULT, time[0] + timedelta(days=7)),
    )
    assert repository.get_card(deck, card).properties["ArtifactExpiresAt"] == expires
    assert repository.get_job(deck, job).properties["ExpiresAt"] == expires
    time[0] += timedelta(days=1)
    with pytest.raises(Inactive):
        repository.claim_job(deck, job, repository.get_job(deck, job).etag)


def test_result_expiry_and_import_shortening_are_explicit(context):
    repository, table, time = context
    deck, job, document, card = generated(repository, time[0])
    repository.record_import(deck, card, repository.get_card(deck, card).etag, str(uuid4()))
    repository.transition_job(
        deck, job, repository.get_job(deck, job).etag, State.COMPLETED,
    )
    time[0] += timedelta(days=1)
    assert "ArtifactId" not in repository.get_card(deck, card).properties
    assert "ArtifactId" not in repository.get_job(deck, job).properties
    assert repository.get_job(deck, job).properties["State"] == State.COMPLETED
    assert "ArtifactId" not in list(repository.list_jobs(deck))[0].properties


def test_expired_result_does_not_prevent_late_import_acknowledgement(context):
    repository, table, time = context
    deck, job, document, card = generated(repository, time[0])
    time[0] += timedelta(days=7)
    assert "ArtifactId" not in repository.get_card(deck, card).properties
    repository.record_import(deck, card, repository.get_card(deck, card).etag, str(uuid4()))
    assert repository.find_card(deck, HASH) is not None


def test_deletion_is_resumable_bounded_and_does_not_remove_another_deck(context):
    repository, table, time = context
    deck = repository.create_deck()
    for _ in range(205):
        repository.create_job(deck, HASH)
    other = repository.create_deck()
    repository.create_job(other, HASH)
    repository.begin_deck_deletion(deck)
    failure = HttpResponseError("Synthetic service outage")
    table.failure = failure
    with pytest.raises(HttpResponseError) as raised:
        repository.finish_deck_deletion(deck)
    assert raised.value is failure
    table.failure = None
    assert table.rows[repository.partition, "d:" + deck].properties["State"] == "deleting"
    repository.finish_deck_deletion(deck)
    assert len(list(repository.list_jobs(other))) == 1
    assert max(table.batch_sizes) == 100
    assert all(deck not in row.properties["RowKey"] for row in table.rows.values())


@pytest.mark.parametrize("operation", ["get", "create", "query", "purge"])
def test_storage_errors_propagate_without_success_fallback(context, operation):
    repository, table, time = context
    deck = repository.create_deck()
    failure = HttpResponseError("Synthetic storage outage")
    table.failure = failure
    with pytest.raises(HttpResponseError) as raised:
        if operation == "get":
            repository.get_deck(deck)
        elif operation == "create":
            repository.create_job(deck, HASH)
        elif operation == "query":
            list(repository.list_decks())
        else:
            repository.purge_expired()
    assert raised.value is failure


def test_missing_table_is_an_outage_not_an_absent_mapping(context):
    repository, table, time = context
    deck = repository.create_deck()
    failure = ResourceNotFoundError("Synthetic unprovisioned table")
    failure.error_code = "TableNotFound"
    table.failure = failure
    with pytest.raises(ResourceNotFoundError) as raised:
        repository.begin_deck_deletion(deck)
    assert raised.value is failure


@pytest.mark.parametrize("bad", ["../private", "' or PartitionKey ne ''", "ABC", "a" * 63])
def test_rejects_invalid_key_material(context, bad):
    repository, table, time = context
    deck = repository.create_deck()
    with pytest.raises(ValueError):
        repository.create_job(deck, bad)
    assert len(table.rows) == 1


def test_content_free_typed_metadata_contract(context):
    repository, table, time = context
    with pytest.raises(TypeError):
        repository.create_deck(subject="Private study text")
    with pytest.raises(ValueError):
        repository.create_deck(subject_id="Private study text")
    with pytest.raises(ValueError):
        Provenance("v1", "arbitrary\nprompt text", "model", "native").properties()
    with pytest.raises(ValueError):
        Usage(input_tokens=-1).properties()
    with pytest.raises(ValueError):
        Usage(pages=True).properties()
    with pytest.raises(ValueError):
        ArtifactReference(str(uuid4()), ArtifactKind.RESULT, time[0] + timedelta(days=8)).properties(time[0])
    with pytest.raises(ValueError):
        ArtifactReference(str(uuid4()), ArtifactKind.ORIGINAL, time[0] + timedelta(days=2)).properties(time[0])
    with pytest.raises(ValueError):
        Repository(table, {"subject": "forged-header"})
    assert table.rows == {}


def test_document_conditional_transitions_and_stale_worker(context):
    repository, table, time = context
    deck, job, token = extracting(repository)
    document = repository.create_document(
        deck, job, repository.get_job(deck, job).etag, token,
        source_hash=HASH, compatibility_hash=COMPATIBILITY, provenance=PROVENANCE,
    )
    etag = repository.get_document(deck, document).etag
    repository.transition_document(
        deck, document, etag, State.GENERATING,
        job_etag=repository.get_job(deck, job).etag, lease_token=token,
    )
    with pytest.raises(Conflict):
        repository.transition_document(
            deck, document, etag, State.READY,
            job_etag=repository.get_job(deck, job).etag, lease_token=token,
        )
    repository.transition_document(
        deck, document, repository.get_document(deck, document).etag, State.DELETED,
    )
    with pytest.raises(Inactive):
        repository.get_document(deck, document)


def test_locally_expired_lease_is_rejected_without_reclaim(context):
    repository, table, time = context
    deck, job, token = extracting(repository)
    etag = repository.get_job(deck, job).etag
    time[0] += timedelta(minutes=5)
    with pytest.raises(Conflict):
        repository.create_document(
            deck, job, etag, token, source_hash=HASH,
            compatibility_hash=COMPATIBILITY, provenance=PROVENANCE,
        )
    with pytest.raises(Conflict):
        repository.transition_job(deck, job, etag, State.GENERATING, lease_token=token)
    assert not any(row.properties["Kind"] == "Documents" for row in table.rows.values())


def test_import_racing_deletion_cannot_create_durable_hashes(context):
    repository, table, time = context
    deck, job, document, card = generated(repository, time[0])
    table.before_commit = lambda: repository.begin_deck_deletion(deck)
    with pytest.raises(ResourceModifiedError):
        repository.record_import(deck, card, repository.get_card(deck, card).etag, str(uuid4()))
    assert not any(row.properties["Kind"] in {"SourceHash", "CardHash"} for row in table.rows.values())
    assert table.rows[repository.partition, f"c:{deck}:{card}"].properties["State"] == State.READY


@pytest.mark.parametrize("lease", [timedelta(0), timedelta(minutes=5, microseconds=1)])
def test_claim_lease_maximum_is_measured(context, lease):
    repository, table, time = context
    deck = repository.create_deck()
    job = repository.create_job(deck, HASH)
    with pytest.raises(ValueError):
        repository.claim_job(deck, job, repository.get_job(deck, job).etag, lease=lease)
    assert "LeaseToken" not in repository.get_job(deck, job).properties


def test_subject_chapter_ids_expire_without_removing_mapping(context):
    repository, table, time = context
    subject, chapter = str(uuid4()), str(uuid4())
    deck = repository.create_deck(subject_id=subject, chapter_id=chapter)
    assert repository.get_deck(deck).properties["SubjectId"] == subject
    assert repository.get_deck(deck).properties["ChapterId"] == chapter
    time[0] += timedelta(days=30)
    assert "SubjectId" not in repository.get_deck(deck).properties
    assert "ChapterId" not in list(repository.list_decks())[0].properties
    repository.purge_expired()
    assert "ExpiresAt" not in table.rows[repository.partition, "d:" + deck].properties
    assert repository.create_job(deck, HASH)
