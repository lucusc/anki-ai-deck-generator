import importlib.util
import os
import shutil
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from contracts import Audience, AudienceError, AudienceSettings, validate_audience_settings

EXPECTED = [
    ("middle_school", "Middle School"), ("high_school", "High School"),
    ("university", "University"), ("certification", "Certification"),
    ("professional", "Professional"),
]


@pytest.fixture
def client_contract():
    path = Path(__file__).resolve().parents[2] / "addon/models/audience.py"
    spec = importlib.util.spec_from_file_location("client_audience_contract", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        del sys.modules[spec.name]


def test_client_server_wire_labels_and_validation_parity(client_contract):
    assert [(item.value, item.label) for item in Audience] == EXPECTED
    assert [(item.value, item.label) for item in client_contract.Audience] == EXPECTED
    for wire, label in EXPECTED:
        client = client_contract.AudienceSettings.from_mapping({"audience": wire})
        server = validate_audience_settings(client.to_mapping())
        assert server.to_mapping() == {"audience": wire}
        assert server.review_label == client.review_label == "Audience: " + label
        assert client_contract.AudienceSettings.from_mapping(server.to_mapping()) == client
    for payload in ({}, None, [], {"audience": None}, {"audience": "University"},
                    {"audience": "university "}, {"audience": True}, {"audience": []},
                    {"audience": "unknown"}, {"audience": 1}):
        with pytest.raises(client_contract.AudienceError) as client_error:
            client_contract.AudienceSettings.from_mapping(payload)
        with pytest.raises(AudienceError) as server_error:
            validate_audience_settings(payload)
        assert server_error.value.code == client_error.value.code
        assert str(server_error.value) == str(client_error.value)


def test_missing_audience_never_defaults():
    with pytest.raises(AudienceError) as error:
        validate_audience_settings({})
    assert error.value.code == "missing"
    with pytest.raises(TypeError):
        AudienceSettings()


@pytest.mark.parametrize("value", [
    None, "", "Middle School", "HIGH_SCHOOL", "university ", " university",
    "private-study-content", 0, 1, True, [], {}, Audience.UNIVERSITY,
])
def test_invalid_audience_never_defaults_or_echoes_input(value):
    with pytest.raises(AudienceError) as error:
        validate_audience_settings({"audience": value})
    assert error.value.code == "invalid"
    assert "private" not in str(error.value)


@pytest.mark.parametrize("payload", [None, [], "university", False])
def test_non_mapping_settings_fail_explicitly(payload):
    with pytest.raises(AudienceError) as error:
        validate_audience_settings(payload)
    assert error.value.code == "invalid"


def test_server_snapshot_cannot_change_with_request_or_output():
    payload = {"audience": "certification", "future_setting": ["synthetic"]}
    accepted = validate_audience_settings(payload)
    payload["audience"] = "professional"
    emitted = accepted.to_mapping()
    emitted["audience"] = "middle_school"
    with pytest.raises(FrozenInstanceError):
        accepted.audience = Audience.PROFESSIONAL
    assert accepted.to_mapping() == {"audience": "certification"}
    assert accepted.review_label == "Audience: Certification"
    assert "certification" not in repr(accepted)
    for value in (None, "university", True):
        with pytest.raises(AudienceError):
            AudienceSettings(value)


@pytest.mark.parametrize("before,after,selector", [
    ('raise AudienceError("missing")', "return cls(Audience.UNIVERSITY)",
     "test_missing_audience_never_defaults"),
    ('raise AudienceError("invalid") from None', "return cls(Audience.UNIVERSITY)",
     "test_invalid_audience_never_defaults_or_echoes_input"),
    ("@dataclass(frozen=True, repr=False)", "@dataclass(frozen=False, repr=False)",
     "test_server_snapshot_cannot_change_with_request_or_output"),
])
def test_server_default_and_mutable_snapshot_regressions_turn_tests_red(
    tmp_path, before, after, selector,
):
    root = Path(__file__).resolve().parents[1]
    shutil.copytree(root / "contracts", tmp_path / "contracts")
    (tmp_path / "tests").mkdir()
    shutil.copyfile(Path(__file__), tmp_path / "tests/test_audience.py")
    source = tmp_path / "contracts/audience.py"
    text = source.read_text()
    assert before in text
    source.write_text(text.replace(before, after, 1))
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", f"tests/test_audience.py::{selector}"],
        cwd=tmp_path, capture_output=True, text=True, timeout=30, check=False,
        env={**os.environ, "PYTHONPATH": str(tmp_path), "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Failed: DID NOT RAISE" in result.stdout
