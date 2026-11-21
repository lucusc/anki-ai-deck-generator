from dataclasses import dataclass
import re
from typing import Iterable, Protocol
from urllib.parse import urlsplit

from azure.core import MatchConditions
from azure.core.credentials import TokenCredential
from azure.data.tables import TableClient, UpdateMode
from azure.identity import DefaultAzureCredential


@dataclass(frozen=True)
class Snapshot:
    properties: dict
    etag: str


@dataclass(frozen=True)
class Write:
    operation: str
    properties: dict
    etag: str | None = None


class Table(Protocol):
    def get(self, partition: str, row: str) -> Snapshot: ...
    def query(self, partition: str, prefix: str = "") -> Iterable[Snapshot]: ...
    def transact(self, writes: list[Write]) -> None: ...


class AzureTable:
    """Production SDK adapter. The table must already be provisioned."""

    def __init__(self, client: TableClient):
        self.client = client

    @classmethod
    def connect(
        cls, endpoint: str, table_name: str, credential: TokenCredential | None = None,
    ) -> "AzureTable":
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme != "https" or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("Credential-free HTTPS Table endpoint required")
        if not re.fullmatch("[A-Za-z][A-Za-z0-9]{2,62}", table_name):
            raise ValueError("Valid Azure table name required")
        return cls(TableClient(
            endpoint=endpoint, table_name=table_name,
            credential=credential if credential is not None else DefaultAzureCredential(),
        ))

    def get(self, partition: str, row: str) -> Snapshot:
        entity = self.client.get_entity(partition_key=partition, row_key=row)
        return Snapshot(dict(entity), entity.metadata["etag"])

    def query(self, partition: str, prefix: str = "") -> Iterable[Snapshot]:
        parameters = {"partition": partition}
        expression = "PartitionKey eq @partition"
        if prefix:
            # Repository prefixes use only ASCII keys ending in ':'.
            if not prefix.endswith(":") or not re.fullmatch("[a-z0-9:-]+", prefix):
                raise ValueError("Canonical row prefix required")
            parameters.update(low=prefix, high=prefix[:-1] + ";")
            expression += " and RowKey ge @low and RowKey lt @high"
        for entity in self.client.query_entities(
            query_filter=expression, parameters=parameters, results_per_page=100,
        ):
            yield Snapshot(dict(entity), entity.metadata["etag"])

    def transact(self, writes: list[Write]) -> None:
        if not 1 <= len(writes) <= 100:
            raise ValueError("Table transaction requires 1-100 operations")
        if len({write.properties["PartitionKey"] for write in writes}) != 1:
            raise ValueError("A Table transaction requires one partition")
        if len({write.properties["RowKey"] for write in writes}) != len(writes):
            raise ValueError("A Table transaction cannot repeat an entity")
        operations = []
        for write in writes:
            if write.operation == "create":
                operations.append(("create", write.properties))
            elif write.operation in {"replace", "delete"} and write.etag and write.etag != "*":
                options = {"etag": write.etag, "match_condition": MatchConditions.IfNotModified}
                if write.operation == "replace":
                    options["mode"] = UpdateMode.REPLACE
                operations.append((
                    "update" if write.operation == "replace" else "delete",
                    write.properties, options,
                ))
            else:
                raise ValueError("Conditional replace/delete requires a concrete ETag")
        self.client.submit_transaction(operations)

    def close(self) -> None:
        self.client.close()
