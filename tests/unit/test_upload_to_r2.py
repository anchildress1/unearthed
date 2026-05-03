"""Unit tests for scripts/upload_to_r2.py."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.upload_to_r2 import _build_client, _iter_parquet_files, main


# ─── _build_client ────────────────────────────────────────────────────────────


def test_build_client_missing_env_raises(monkeypatch):
    for k in ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_ENDPOINT"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(SystemExit, match="Missing R2 credentials"):
        _build_client()


def test_build_client_partial_env_raises(monkeypatch):
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
    monkeypatch.delenv("R2_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("R2_ENDPOINT", raising=False)
    with pytest.raises(SystemExit, match="Missing R2 credentials"):
        _build_client()


@patch("scripts.upload_to_r2.boto3.client")
def test_build_client_uses_r2_region_env(mock_boto, monkeypatch):
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("R2_ENDPOINT", "https://example.r2.cloudflarestorage.com")
    monkeypatch.setenv("R2_REGION", "wnam")
    _build_client()
    _, kwargs = mock_boto.call_args
    assert kwargs["region_name"] == "wnam"


@patch("scripts.upload_to_r2.boto3.client")
def test_build_client_defaults_region_to_auto(mock_boto, monkeypatch):
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("R2_ENDPOINT", "https://example.r2.cloudflarestorage.com")
    monkeypatch.delenv("R2_REGION", raising=False)
    _build_client()
    _, kwargs = mock_boto.call_args
    assert kwargs["region_name"] == "auto"


# ─── _iter_parquet_files ──────────────────────────────────────────────────────


def test_iter_parquet_files_yields_posix_keys(tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "mines.parquet").write_bytes(b"")
    (tmp_path / "mrt").mkdir()
    (tmp_path / "mrt" / "emissions.parquet").write_bytes(b"")

    pairs = list(_iter_parquet_files(tmp_path))
    keys = [k for _, k in pairs]
    assert "raw/mines.parquet" in keys
    assert "mrt/emissions.parquet" in keys


def test_iter_parquet_files_empty_dir(tmp_path):
    assert list(_iter_parquet_files(tmp_path)) == []


def test_iter_parquet_files_ignores_non_parquet(tmp_path):
    (tmp_path / "data.csv").write_bytes(b"")
    (tmp_path / "readme.txt").write_bytes(b"")
    assert list(_iter_parquet_files(tmp_path)) == []


# ─── main ─────────────────────────────────────────────────────────────────────


def test_main_missing_src_raises(tmp_path):
    with pytest.raises(SystemExit, match="Source directory not found"):
        main(["--src", str(tmp_path / "nonexistent")])


def test_main_no_files_returns_0(tmp_path):
    assert main(["--src", str(tmp_path)]) == 0


def test_main_dry_run_returns_0(tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "mines.parquet").write_bytes(b"")
    assert main(["--src", str(tmp_path), "--dry-run"]) == 0


@patch("scripts.upload_to_r2._build_client")
def test_main_upload_success_returns_0(mock_build, tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "mines.parquet").write_bytes(b"fake")
    mock_client = MagicMock()
    mock_build.return_value = mock_client
    result = main(["--src", str(tmp_path), "--bucket", "test-bucket"])
    assert result == 0
    mock_client.put_object.assert_called_once()


@patch("scripts.upload_to_r2._build_client")
def test_main_upload_failure_returns_1(mock_build, tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "mines.parquet").write_bytes(b"fake")
    mock_client = MagicMock()
    mock_client.put_object.side_effect = RuntimeError("connection refused")
    mock_build.return_value = mock_client
    result = main(["--src", str(tmp_path), "--bucket", "test-bucket"])
    assert result == 1


@patch("scripts.upload_to_r2._build_client")
def test_main_partial_failure_stops_on_first_error(mock_build, tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "a.parquet").write_bytes(b"fake")
    (tmp_path / "raw" / "b.parquet").write_bytes(b"fake")
    mock_client = MagicMock()
    mock_client.put_object.side_effect = [None, RuntimeError("boom")]
    mock_build.return_value = mock_client
    result = main(["--src", str(tmp_path), "--bucket", "test-bucket"])
    assert result == 1
    assert mock_client.put_object.call_count == 2
