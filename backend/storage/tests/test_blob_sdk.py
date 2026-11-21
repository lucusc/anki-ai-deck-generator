import base64
from datetime import datetime, timedelta, timezone
import json
from urllib.parse import parse_qs, urlsplit

from azure.core.exceptions import HttpResponseError, ResourceModifiedError, ResourceNotFoundError
from azure.mgmt.storage import StorageManagementClient
from azure.storage.blob import BlobServiceClient
import pytest

from storage.blob import AzureBlobs, MAX_BYTES, StoragePolicyError
from storage.tests.test_azure import SyntheticCredential, Transport


LEASE = "11111111-1111-4111-8111-111111111111"
SUBSCRIPTION = "22222222-2222-4222-8222-222222222222"
NAME = "u123/33333333-3333-4333-8333-333333333333/44444444-4444-4444-8444-444444444444/result/55555555-5555-4555-8555-555555555555"
XML = {"Content-Type": "application/xml"}
EMPTY_LIST = '<EnumerationResults><Blobs/><NextMarker/></EnumerationResults>'


def adapter(responses=(), management_responses=()):
    transport, management_transport = Transport(responses), Transport(management_responses)
    credential = SyntheticCredential()
    client = BlobServiceClient(
        "https://offline.blob.core.windows.net", credential=credential,
        transport=transport, retry_total=0, max_single_put_size=MAX_BYTES,
    )
    management = StorageManagementClient(
        credential, SUBSCRIPTION, transport=management_transport, retry_total=0,
    )
    return AzureBlobs(client, "temporary", management, "synthetic-group", "offline"), transport, management_transport


def success(etag='"one"'):
    return (201, "", {"ETag": etag, "x-ms-request-id": "synthetic", "x-ms-version": "2025-11-05"})


def error(status, code):
    return (status, f"<Error><Code>{code}</Code><Message>Synthetic private detail</Message></Error>", XML)


def test_real_sdk_create_empty_then_infinite_lease_and_single_conditional_payload_put():
    blobs, transport, _ = adapter([
        success(), (201, "", {"x-ms-lease-id": LEASE}), success('"two"'),
    ])
    assert blobs.initialize(NAME, LEASE) == '"one"'
    assert blobs.put(NAME, b"synthetic result", LEASE, '"one"') == '"two"'
    initialize, lease, put = transport.requests
    assert initialize.body == b""
    assert initialize.headers["If-None-Match"] == "*"
    assert initialize.headers["x-ms-blob-type"] == "BlockBlob"
    assert lease.headers["x-ms-lease-action"] == "acquire"
    assert lease.headers["x-ms-lease-duration"] == "-1"
    assert lease.headers["x-ms-proposed-lease-id"] == LEASE
    assert put.body == b"synthetic result"
    assert put.headers["If-Match"] == '"one"'
    assert put.headers["x-ms-lease-id"] == LEASE
    assert put.headers["x-ms-blob-content-type"] == "application/octet-stream"
    assert all(request.headers["Authorization"].startswith("Bearer ") for request in transport.requests)
    assert all(parse_qs(urlsplit(request.url).query)["timeout"] == ["30"] for request in transport.requests)
    assert "blocklist" not in put.url and "comp=block" not in put.url


def test_real_sdk_delete_uses_lease_includes_snapshots_and_has_no_stale_etag():
    blobs, transport, _ = adapter([(200, EMPTY_LIST, XML), (202, "", {})])
    blobs.delete(NAME, LEASE)
    listing, deletion = transport.requests
    query = parse_qs(urlsplit(listing.url).query)
    assert query["prefix"] == [NAME] and query["include"] == ["versions,deleted"]
    assert query["maxresults"] == ["100"]
    assert deletion.method == "DELETE"
    assert deletion.headers["x-ms-lease-id"] == LEASE
    assert deletion.headers["x-ms-delete-snapshots"] == "include"
    assert "If-Match" not in deletion.headers


@pytest.mark.parametrize("code,error_type", [
    ("BlobNotFound", None), ("ContainerNotFound", ResourceNotFoundError),
    ("LeaseIdMismatchWithBlobOperation", HttpResponseError), ("ServerBusy", HttpResponseError),
])
def test_only_missing_blob_is_idempotent_success(code, error_type):
    status = 404 if code.endswith("NotFound") else 412 if code.startswith("Lease") else 503
    blobs, transport, _ = adapter([(200, EMPTY_LIST, XML), error(status, code)])
    if error_type is None:
        blobs.delete(NAME, LEASE)
    else:
        with pytest.raises(error_type):
            blobs.delete(NAME, LEASE)
    assert len(transport.requests) == 2


@pytest.mark.parametrize("status,code,exception", [
    (412, "LeaseNotPresentWithBlobOperation", HttpResponseError),
    (412, "ConditionNotMet", ResourceModifiedError),
    (503, "ServerBusy", HttpResponseError),
])
def test_real_sdk_stale_put_and_outage_surface_without_retry(status, code, exception):
    blobs, transport, _ = adapter([error(status, code)])
    with pytest.raises(exception):
        blobs.put(NAME, b"synthetic", LEASE, '"old"')
    assert len(transport.requests) == 1
    assert transport.requests[0].headers["x-ms-lease-id"] == LEASE
    assert transport.requests[0].headers["If-Match"] == '"old"'


def test_real_sdk_ambiguous_initialization_is_not_retried_or_given_content():
    blobs, transport, _ = adapter([error(503, "ServerBusy")])
    with pytest.raises(HttpResponseError):
        blobs.initialize(NAME, LEASE)
    assert len(transport.requests) == 1 and transport.requests[0].body == b""


def test_actual_user_delegation_key_request_and_read_only_blob_sas_expiry():
    start = datetime(2026, 11, 21, tzinfo=timezone.utc)
    expiry = start + timedelta(minutes=5)
    key = base64.b64encode(b"synthetic-not-a-production-signing-key").decode()
    xml = (
        "<UserDelegationKey><SignedOid>synthetic</SignedOid><SignedTid>synthetic</SignedTid>"
        "<SignedStart>2026-11-21T00:00:00Z</SignedStart>"
        "<SignedExpiry>2026-11-21T00:05:00Z</SignedExpiry><SignedService>b</SignedService>"
        f"<SignedVersion>2025-11-05</SignedVersion><Value>{key}</Value></UserDelegationKey>"
    )
    blobs, transport, _ = adapter([(200, xml, XML)])
    grant = blobs.read_access(NAME, start, expiry)
    query = parse_qs(urlsplit(grant.url).query)
    assert query["sp"] == ["r"] and query["sr"] == ["b"] and query["spr"] == ["https"]
    assert query["se"] == ["2026-11-21T00:05:00Z"]
    assert query["rscc"] == ["no-store"] and "sig" in query
    assert NAME in urlsplit(grant.url).path
    assert grant.expires_at == expiry
    assert "sig" not in repr(grant) and key not in repr(grant)
    request = transport.requests[0]
    assert request.method == "POST"
    assert "comp=userdelegationkey" in request.url
    body = request.body.decode() if isinstance(request.body, bytes) else request.body
    assert "2026-11-21T00:05:00Z" in body


def policy_responses(**changes):
    properties = {
        "isVersioningEnabled": False, "deleteRetentionPolicy": {"enabled": False},
        "restorePolicy": {"enabled": False},
    }
    properties.update(changes)
    account = {"properties": {
        "allowBlobPublicAccess": False, "allowSharedKeyAccess": False, "isHnsEnabled": False,
        "primaryEndpoints": {"blob": "https://offline.blob.core.windows.net/"},
    }}
    return [
        (200, json.dumps({"properties": properties}), {"Content-Type": "application/json"}),
        (200, json.dumps(account), {"Content-Type": "application/json"}),
    ]


def test_real_management_sdk_policy_and_data_plane_container_private_check():
    blobs, transport, management = adapter([(200, "", {})], policy_responses())
    blobs.check_policy()
    assert len(management.requests) == 2
    assert all(request.method == "GET" for request in management.requests)
    assert all(f"/subscriptions/{SUBSCRIPTION}/resourceGroups/synthetic-group/" in request.url for request in management.requests)
    assert "/blobServices/default" in management.requests[0].url
    assert all(request.headers["Authorization"].startswith("Bearer ") for request in management.requests)
    assert transport.requests[0].method == "GET"
    assert "restype=container" in transport.requests[0].url


@pytest.mark.parametrize("changes", [
    {"isVersioningEnabled": True}, {"isVersioningEnabled": None},
    {"deleteRetentionPolicy": {"enabled": True, "days": 7}},
    {"restorePolicy": {"enabled": True}}, {"automaticSnapshotPolicyEnabled": True},
])
def test_actual_arm_retained_copy_settings_fail_closed(changes):
    blobs, transport, management = adapter(management_responses=policy_responses(**changes))
    with pytest.raises(StoragePolicyError):
        blobs.check_policy()
    assert transport.requests == []


def test_public_container_and_management_outage_fail_closed():
    blobs, _, _ = adapter([(200, "", {"x-ms-blob-public-access": "blob"})], policy_responses())
    with pytest.raises(StoragePolicyError):
        blobs.check_policy()
    blobs, _, management = adapter(management_responses=[(
        503, json.dumps({"error": {"code": "ServerBusy", "message": "Synthetic"}}),
        {"Content-Type": "application/json"},
    )])
    with pytest.raises(HttpResponseError):
        blobs.check_policy()
    assert len(management.requests) == 1


def test_real_sdk_worker_read_has_concrete_etag_and_bounded_size():
    headers = {"ETag": '"stored"', "Content-Length": "9", "x-ms-blob-type": "BlockBlob"}
    blobs, transport, _ = adapter([
        (200, "", headers),
        (206, "synthetic", {**headers, "Content-Range": "bytes 0-8/9"}),
    ])
    assert blobs.download(NAME, '"stored"') == b"synthetic"
    assert [request.method for request in transport.requests] == ["HEAD", "GET"]
    assert all(request.headers["If-Match"] == '"stored"' for request in transport.requests)
    blobs, transport, _ = adapter([(200, "", {**headers, "Content-Length": str(MAX_BYTES + 1)})])
    with pytest.raises(StoragePolicyError):
        blobs.download(NAME, '"stored"')
    assert len(transport.requests) == 1


def test_retained_versions_are_detected_before_base_deletion():
    listing = (
        f'<EnumerationResults><Blobs><Blob><Name>{NAME}</Name><VersionId>opaque</VersionId>'
        '<Properties><BlobType>BlockBlob</BlobType><Content-Length>1</Content-Length></Properties>'
        '</Blob></Blobs><NextMarker/></EnumerationResults>'
    )
    blobs, transport, _ = adapter([(200, listing, XML)])
    with pytest.raises(StoragePolicyError):
        blobs.delete(NAME, LEASE)
    assert len(transport.requests) == 1


def test_real_source_mutation_of_lease_header_is_rejected(monkeypatch):
    import storage.blob as module
    from pathlib import Path
    import sys
    source = Path(module.__file__).read_text()
    protected = "lease=lease_id, etag=etag,"
    assert source.count(protected) == 1
    namespace = vars(module).copy()
    exec(compile(source.replace(protected, "etag=etag,"), module.__file__, "exec"), namespace)
    monkeypatch.setattr(sys.modules[__name__], "AzureBlobs", namespace["AzureBlobs"])
    with pytest.raises(KeyError, match="x-ms-lease-id"):
        test_real_sdk_create_empty_then_infinite_lease_and_single_conditional_payload_put()


def test_configured_timer_path_uses_real_table_blob_and_management_sdk_transports(monkeypatch):
    from azure.data.tables import TableClient
    import storage.azure as table_module
    import storage.blob as blob_module
    import storage.retention as retention
    from storage.tests.test_azure import batch_response

    table_transport = Transport([
        (404, json.dumps({"odata.error": {"code": "ResourceNotFound", "message": {"value": "Synthetic"}}}),
         {"Content-Type": "application/json"}),
        (200, '{"value":[]}', {"Content-Type": "application/json"}),
        (202, batch_response([204]), {"Content-Type": "multipart/mixed; boundary=batchresponse"}),
    ])
    blob_transport = Transport([(200, "", {})])
    management_transport = Transport(policy_responses())

    class Credential(SyntheticCredential):
        def close(self):
            pass

    monkeypatch.setattr(retention, "DefaultAzureCredential", Credential)
    monkeypatch.setattr(table_module, "TableClient", lambda **kwargs: TableClient(
        **kwargs, transport=table_transport, retry_total=0,
    ))
    monkeypatch.setattr(blob_module, "BlobServiceClient", lambda *args, **kwargs: BlobServiceClient(
        *args, **kwargs, transport=blob_transport,
    ))
    monkeypatch.setattr(blob_module, "StorageManagementClient", lambda *args, **kwargs: StorageManagementClient(
        *args, **kwargs, transport=management_transport,
    ))
    values = {
        "STORAGE_TABLE_ENDPOINT": "https://offline.table.core.windows.net",
        "STORAGE_TABLE_NAME": "Metadata",
        "STORAGE_BLOB_ENDPOINT": "https://offline.blob.core.windows.net",
        "STORAGE_BLOB_CONTAINER": "temporary",
        "STORAGE_SUBSCRIPTION_ID": SUBSCRIPTION,
        "STORAGE_RESOURCE_GROUP": "synthetic-group",
        "STORAGE_ACCOUNT_NAME": "offline",
        "RETENTION_USERS": json.dumps([{"issuer": "https://issuer.test/", "subject": "synthetic"}]),
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    retention.run_configured_sweep()
    assert len(table_transport.requests) == 3
    assert len(blob_transport.requests) == 1 and len(management_transport.requests) == 2
    body = table_transport.requests[-1].body.decode()
    assert "RetentionCursor" in body and "LastCompletedAt" in body
    assert "synthetic" not in body and "https://issuer.test" not in body
