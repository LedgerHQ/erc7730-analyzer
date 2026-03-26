"""Tests for zip bundle building and safe extraction."""

import io
import zipfile
from pathlib import Path

import pytest

from utils.bundle_zip import (
    BundleError,
    build_descriptor_bundle_zip_bytes,
    collect_descriptor_files_for_bundle,
    default_bundle_root_for_descriptor,
    normalize_bundle_entrypoint,
    safe_extract_bundle_zip,
)


def test_normalize_bundle_entrypoint_rejects_traversal() -> None:
    with pytest.raises(BundleError):
        normalize_bundle_entrypoint("../evil.json")


def test_safe_extract_rejects_zip_slip(tmp_path: Path) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../../etc/passwd", b"x")
    with pytest.raises(BundleError):
        safe_extract_bundle_zip(buf.getvalue(), tmp_path)


def test_build_and_extract_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / "sub").mkdir(parents=True)
    main = root / "sub" / "main.json"
    inc = root / "other" / "inc.json"
    inc.parent.mkdir(parents=True)
    main.write_text('{"includes": "../other/inc.json", "metadata": {"x": 1}}')
    inc.write_text("{}")

    raw = build_descriptor_bundle_zip_bytes(main, root)
    dest = tmp_path / "out"
    safe_extract_bundle_zip(raw, dest)
    assert (dest / "sub" / "main.json").is_file()
    assert (dest / "other" / "inc.json").is_file()


def test_collect_rejects_escape(tmp_path: Path) -> None:
    root = tmp_path / "r"
    (root / "a").mkdir(parents=True)
    main = root / "a" / "m.json"
    main.write_text('{"includes": "../../outside.json"}')
    with pytest.raises(BundleError, match="escapes bundle root"):
        collect_descriptor_files_for_bundle(main, root)


def test_decode_bundle_base64_invalid() -> None:
    from utils.bundle_zip import decode_bundle_zip_from_base64

    with pytest.raises(BundleError):
        decode_bundle_zip_from_base64("not-valid-base64!!!")


def test_default_bundle_root_uses_descriptor_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    cwd = repo / "unrelated-cwd"
    cwd.mkdir(parents=True)
    (repo / ".git").mkdir()

    descriptor = repo / "specs" / "descriptor.json"
    descriptor.parent.mkdir(parents=True)
    descriptor.write_text("{}")

    monkeypatch.chdir(cwd)

    assert default_bundle_root_for_descriptor(descriptor) == descriptor.parent.resolve()
