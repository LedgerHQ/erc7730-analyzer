"""Unit tests for run-key derivation and caller metadata extraction."""

from __future__ import annotations

import pytest

from service.auth import derive_run_key, extract_caller_metadata


class TestDeriveRunKey:
    def test_success(self):
        claims = {"repository": "org/repo", "run_id": "123", "run_attempt": "2"}
        assert derive_run_key(claims) == "org/repo:123:2"

    def test_default_run_attempt(self):
        claims = {"repository": "org/repo", "run_id": "123"}
        assert derive_run_key(claims) == "org/repo:123:1"

    def test_empty_run_attempt_defaults_to_1(self):
        claims = {"repository": "org/repo", "run_id": "123", "run_attempt": ""}
        assert derive_run_key(claims) == "org/repo:123:1"

    def test_missing_repository_raises(self):
        with pytest.raises(ValueError, match="repository"):
            derive_run_key({"run_id": "123"})

    def test_missing_run_id_raises(self):
        with pytest.raises(ValueError, match="run_id"):
            derive_run_key({"repository": "org/repo"})

    def test_empty_claims_raises(self):
        with pytest.raises(ValueError):
            derive_run_key({})


class TestExtractCallerMetadata:
    def test_all_fields_present(self):
        claims = {
            "repository": "org/repo",
            "workflow": "CI",
            "ref": "refs/heads/main",
            "sha": "abc123",
            "sub": "repo:org/repo:ref:refs/heads/main",
            "run_id": "456",
            "run_attempt": "2",
        }
        meta = extract_caller_metadata(claims)
        assert meta == {
            "repository": "org/repo",
            "workflow": "CI",
            "ref": "refs/heads/main",
            "sha": "abc123",
            "sub": "repo:org/repo:ref:refs/heads/main",
            "run_id": "456",
            "run_attempt": "2",
        }

    def test_missing_fields_default_to_empty(self):
        meta = extract_caller_metadata({})
        assert meta["repository"] == ""
        assert meta["workflow"] == ""
        assert meta["run_attempt"] == "1"

    def test_non_string_values_coerced(self):
        claims = {"repository": 123, "run_id": 456}
        meta = extract_caller_metadata(claims)
        assert meta["repository"] == "123"
        assert meta["run_id"] == "456"
