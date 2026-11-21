import json
import time

from azure.core.credentials import AccessToken
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError, ResourceModifiedError
from azure.core.pipeline.transport import HttpResponse, HttpTransport
from azure.data.tables import TableClient
import pytest

from backend.storage.azure import AzureTable, Write


class SyntheticCredential:
    def get_token(self, *scopes, **kwargs):
        return AccessToken("synthetic-offline-access", int(time.time()) + 3600)


class Response(HttpResponse):
    def __init__(self, request, status, body, headers):
        super().__init__(request, None)
        self.status_code = status
        self.headers = headers
        self.reason = "Synthetic"
        self._body = body.encode()
        self.content_type = headers.get("Content-Type")

    def body(self):
        return self._body

    def stream_download(self, pipeline, **kwargs):
        yield self._body


class Transport(HttpTransport):
    """Real SDK serialization/deserialization with no sockets or Azure account."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def send(self, request, **kwargs):
        self.requests.append(request)
        status, body, headers = self.responses.pop(0)
        return Response(request, status, body, headers)


def adapter(responses):
    transport = Transport(responses)
    client = TableClient(
        endpoint="https://offline.table.core.windows.net", table_name="Metadata",
        credential=SyntheticCredential(), transport=transport,
        retry_total=0, retry_status=0, retry_connect=0, retry_read=0,
    )
    return AzureTable(client), transport


def entity(row, etag='W/"synthetic-etag"'):
    return {
        "PartitionKey": "u123", "RowKey": row,
        "odata.etag": etag, "Kind": "Decks", "State": "active",
    }


def test_sdk_get_and_query_use_user_keys_etags_and_continuation_pages():
    table, transport = adapter([
        (200, json.dumps(entity("d:1")), {"Content-Type": "application/json", "ETag": 'W/"one"'}),
        (200, json.dumps({"value": [entity("d:1")]}), {
            "Content-Type": "application/json",
            "x-ms-continuation-NextPartitionKey": "u123",
            "x-ms-continuation-NextRowKey": "d:2",
        }),
        (200, json.dumps({"value": [entity("d:2")]}), {"Content-Type": "application/json"}),
    ])
    result = table.get("u123", "d:1")
    assert result.properties["RowKey"] == "d:1"
    assert result.etag == 'W/"synthetic-etag"'
    rows = list(table.query("u123", "d:"))
    assert [row.properties["RowKey"] for row in rows] == ["d:1", "d:2"]
    from urllib.parse import parse_qs, urlsplit
    query = parse_qs(urlsplit(transport.requests[1].url).query)
    assert query["$filter"] == ["PartitionKey eq 'u123' and RowKey ge 'd:' and RowKey lt 'd;'"]
    assert parse_qs(urlsplit(transport.requests[2].url).query)["NextRowKey"] == ["d:2"]
    assert all(request.headers["Authorization"].startswith("Bearer ") for request in transport.requests)
    table.close()


def batch_response(statuses):
    inner = []
    for index, status in enumerate(statuses):
        body = "" if status == 204 else json.dumps({
            "odata.error": {"code": "UpdateConditionNotSatisfied", "message": {"value": "Synthetic"}},
        })
        inner.append(
            "--changesetresponse\r\nContent-Type: application/http\r\n"
            f"Content-ID: {index}\r\n\r\nHTTP/1.1 {status} Synthetic\r\n"
            "Content-Type: application/json\r\n"
            f'ETag: W/"returned-{index}"\r\n\r\n{body}\r\n'
        )
    return (
        "--batchresponse\r\nContent-Type: multipart/mixed; boundary=changesetresponse\r\n\r\n"
        + "".join(inner)
        + "--changesetresponse--\r\n--batchresponse--\r\n"
    )


def test_real_sdk_transaction_serializes_conditional_replace_not_merge_or_upsert():
    table, transport = adapter([(
        202, batch_response([204, 204, 204]),
        {"Content-Type": "multipart/mixed; boundary=batchresponse"},
    )])
    table.transact([
        Write("replace", {"PartitionKey": "u123", "RowKey": "d:1", "State": "active"}, 'W/"guard"'),
        Write("create", {"PartitionKey": "u123", "RowKey": "j:1", "State": "queued"}),
        Write("delete", {"PartitionKey": "u123", "RowKey": "o:1"}, 'W/"document"'),
    ])
    request = transport.requests[0]
    body = request.body.decode() if isinstance(request.body, bytes) else request.body
    assert request.url.endswith("/$batch")
    assert "PUT https://" in body
    assert "POST https://" in body
    assert "DELETE https://" in body
    assert 'If-Match: W/"guard"' in body
    assert 'If-Match: W/"document"' in body
    assert "MERGE " not in body
    assert "If-Match: *" not in body


def test_real_sdk_transaction_surfaces_412():
    table, transport = adapter([(
        202, batch_response([412]), {"Content-Type": "multipart/mixed; boundary=batchresponse"},
    )])
    with pytest.raises(HttpResponseError) as raised:
        table.transact([Write("replace", {"PartitionKey": "u123", "RowKey": "d:1"}, 'W/"old"')])
    assert raised.value.status_code == 412


@pytest.mark.parametrize("status,error", [
    (404, ResourceNotFoundError), (412, ResourceModifiedError), (503, HttpResponseError),
])
def test_sdk_lookup_storage_errors_are_not_converted_to_success(status, error):
    code = {404: "ResourceNotFound", 412: "UpdateConditionNotSatisfied", 503: "ServerBusy"}[status]
    table, transport = adapter([(
        status, json.dumps({"odata.error": {"code": code, "message": {"value": "Synthetic"}}}),
        {"Content-Type": "application/json"},
    )])
    with pytest.raises(error) as raised:
        table.get("u123", "d:1")
    assert raised.value.status_code == status


@pytest.mark.parametrize("writes", [
    [],
    [Write("delete", {"PartitionKey": "u123", "RowKey": "d:1"}, "*")],
    [Write("replace", {"PartitionKey": "u123", "RowKey": "d:1"})],
    [Write("create", {"PartitionKey": "u123", "RowKey": "d:1"})] * 2,
    [
        Write("create", {"PartitionKey": "u123", "RowKey": "d:1"}),
        Write("create", {"PartitionKey": "other", "RowKey": "d:2"}),
    ],
])
def test_adapter_rejects_unconditional_or_nonatomic_operations(writes):
    table, transport = adapter([])
    with pytest.raises(ValueError):
        table.transact(writes)
    assert transport.requests == []


@pytest.mark.parametrize("endpoint", [
    "http://account.table.core.windows.net", "https://account.table.core.windows.net/?sig=secret",
    "https://username:password@account.table.core.windows.net",
])
def test_configuration_rejects_non_tls_and_embedded_credentials(endpoint):
    with pytest.raises(ValueError):
        AzureTable.connect(endpoint, "Metadata", SyntheticCredential())


def test_connect_uses_token_credential_without_provisioning_or_network():
    table = AzureTable.connect(
        "https://offline.table.core.windows.net", "Metadata", SyntheticCredential(),
    )
    assert table.client.table_name == "Metadata"
    table.close()
