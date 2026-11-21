from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum


class Audience(Enum):
    MIDDLE_SCHOOL = "middle_school"
    HIGH_SCHOOL = "high_school"
    UNIVERSITY = "university"
    CERTIFICATION = "certification"
    PROFESSIONAL = "professional"

    @property
    def label(self) -> str:
        return {
            Audience.MIDDLE_SCHOOL: "Middle School",
            Audience.HIGH_SCHOOL: "High School",
            Audience.UNIVERSITY: "University",
            Audience.CERTIFICATION: "Certification",
            Audience.PROFESSIONAL: "Professional",
        }[self]


class AudienceError(ValueError):
    MESSAGES = {
        "missing": "Select an audience before continuing.",
        "invalid": "Audience must be Middle School, High School, University, Certification or Professional.",
    }

    def __init__(self, code: str):
        self.code = code
        super().__init__(self.MESSAGES[code])


@dataclass(frozen=True, repr=False)
class AudienceSettings:
    audience: Audience

    def __post_init__(self):
        if not isinstance(self.audience, Audience):
            raise AudienceError("invalid")

    @classmethod
    def from_mapping(cls, settings: object) -> "AudienceSettings":
        if not isinstance(settings, Mapping):
            raise AudienceError("invalid")
        if "audience" not in settings:
            raise AudienceError("missing")
        value = settings["audience"]
        if type(value) is not str:
            raise AudienceError("invalid")
        try:
            audience = Audience(value)
        except ValueError:
            raise AudienceError("invalid") from None
        return cls(audience)

    def to_mapping(self) -> dict[str, str]:
        return {"audience": self.audience.value}

    @property
    def review_label(self) -> str:
        return f"Audience: {self.audience.label}"

    def __repr__(self) -> str:
        return "AudienceSettings(<study settings>)"


def validate_audience_settings(settings: object) -> AudienceSettings:
    return AudienceSettings.from_mapping(settings)
