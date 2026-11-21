from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
import hashlib
import json
import re
from uuid import UUID

from auth import Principal


class State(StrEnum):
    QUEUED = "queued"
    EXTRACTING = "extracting"
    GENERATING = "generating"
    READY = "ready_for_review"
    COMPLETED = "completed"
    FAILED = "failed"
    DELETED = "deleted"


TRANSITIONS = {
    State.QUEUED: {State.EXTRACTING, State.FAILED, State.DELETED},
    State.EXTRACTING: {State.GENERATING, State.FAILED, State.DELETED},
    State.GENERATING: {State.READY, State.FAILED, State.DELETED},
    State.READY: {State.COMPLETED, State.DELETED},
    State.FAILED: {State.DELETED},
    State.COMPLETED: {State.DELETED},
    State.DELETED: set(),
}


class ArtifactKind(StrEnum):
    ORIGINAL = "original"
    EXTRACTED = "extracted"
    RESULT = "result"
    REVIEW_IMAGE = "review_image"


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("UTC timestamp required")
    return value.astimezone(timezone.utc)


def identifier(value: str) -> str:
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("Canonical UUID required")
    return value


def digest(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{64}", value):
        raise ValueError("Lowercase SHA-256 required")
    return value


def label(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch("[A-Za-z0-9_.-]{1,64}", value):
        raise ValueError("Deployment-controlled version label required")
    return value


def user_partition(principal: Principal) -> str:
    if not isinstance(principal, Principal) or not principal.issuer or not principal.subject:
        raise ValueError("Validated Principal required")
    encoded = json.dumps(
        ["anki-tables-v1", principal.issuer, principal.subject],
        ensure_ascii=True, separators=(",", ":"),
    ).encode()
    return "u" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class Provenance:
    extraction_version: str
    prompt_version: str
    model_version: str
    method: str
    page: int = 0
    slide: int = 0
    section: int = 0

    def properties(self) -> dict:
        if self.method not in {"native", "ocr", "none"}:
            raise ValueError("Unknown extraction method")
        result = {
            "ExtractionVersion": label(self.extraction_version),
            "PromptVersion": label(self.prompt_version),
            "ModelVersion": label(self.model_version),
            "ExtractionMethod": self.method,
        }
        for key, value in (("Page", self.page), ("Slide", self.slide), ("Section", self.section)):
            if type(value) is not int or not 0 <= value <= 2**31 - 1:
                raise ValueError("Nonnegative bounded source location required")
            result[key] = value
        return result


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    pages: int = 0
    proposed_notes: int = 0
    imported_notes: int = 0
    generated_cards: int = 0
    duplicate_skips: int = 0
    attempts: int = 0
    duration_ms: int = 0

    def properties(self) -> dict:
        result = {}
        for key, value in (
            ("InputTokens", self.input_tokens), ("OutputTokens", self.output_tokens),
            ("Pages", self.pages), ("ProposedNotes", self.proposed_notes),
            ("ImportedNotes", self.imported_notes), ("GeneratedCards", self.generated_cards),
            ("DuplicateSkips", self.duplicate_skips), ("Attempts", self.attempts),
            ("DurationMs", self.duration_ms),
        ):
            if type(value) is not int or not 0 <= value <= 2**63 - 1:
                raise ValueError("Nonnegative bounded usage count required")
            result[key] = value
        return result


@dataclass(frozen=True)
class ArtifactReference:
    artifact_id: str
    kind: ArtifactKind
    expires_at: datetime

    def properties(self, now: datetime) -> dict:
        if not isinstance(self.kind, ArtifactKind):
            raise ValueError("Artifact kind required")
        maximum = timedelta(days=7 if self.kind in {
            ArtifactKind.RESULT, ArtifactKind.REVIEW_IMAGE,
        } else 1)
        expiry = utc(self.expires_at)
        if not utc(now) < expiry <= now + maximum:
            raise ValueError("Artifact reference exceeds retention window")
        return {
            "ArtifactId": identifier(self.artifact_id), "ArtifactKind": self.kind.value,
            "ArtifactExpiresAt": expiry,
        }
