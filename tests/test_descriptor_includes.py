"""Tests for include merging with allowed root."""

from pathlib import Path

import pytest

from utils.core import ERC7730Analyzer


def test_parse_resolves_sibling_under_include_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    sub = root / "sub"
    sub.mkdir(parents=True)
    other = root / "other"
    other.mkdir()
    main = sub / "main.json"
    inc = other / "inc.json"
    main.write_text('{"includes": "../other/inc.json", "metadata": {"a": 1}}')
    inc.write_text('{"metadata": {"b": 2}}')

    an = ERC7730Analyzer(etherscan_api_key="test")
    data = an.parse_erc7730_file(main, include_root=root)
    assert "includes" not in data
    assert data.get("metadata", {}).get("b") == 2
    assert data.get("metadata", {}).get("a") == 1


def test_parse_rejects_traversal_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "job"
    root.mkdir()
    main = root / "main.json"
    outside = tmp_path / "secret.json"
    outside.write_text("{}")
    main.write_text('{"includes": "../secret.json"}')

    an = ERC7730Analyzer(etherscan_api_key="test")
    with pytest.raises(ValueError, match="escapes allowed root"):
        an.parse_erc7730_file(main, include_root=root)


def test_nested_include_uses_including_files_directory(tmp_path: Path) -> None:
    """Middle file includes a path relative to its own directory, not the entry directory."""
    root = tmp_path / "r"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir()
    entry = root / "a" / "entry.json"
    mid = root / "a" / "mid.json"
    leaf = root / "b" / "leaf.json"
    entry.write_text('{"includes": "mid.json"}')
    mid.write_text('{"includes": "../b/leaf.json", "metadata": {"mid": true}}')
    leaf.write_text('{"metadata": {"leaf": 1}}')

    an = ERC7730Analyzer(etherscan_api_key="test")
    data = an.parse_erc7730_file(entry, include_root=root)
    assert data.get("metadata", {}).get("leaf") == 1
