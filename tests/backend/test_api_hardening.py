import pytest

from app.main import configured_cors_origins


def test_cors_origins_are_explicit_and_normalized():
    assert configured_cors_origins(" http://localhost:5173/ ,https://demo.example ") == [
        "http://localhost:5173",
        "https://demo.example",
    ]


def test_cors_wildcard_is_rejected_when_credentials_are_enabled():
    with pytest.raises(ValueError, match="explicit origins"):
        configured_cors_origins("*")
