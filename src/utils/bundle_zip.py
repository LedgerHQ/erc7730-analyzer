"""Build and safely extract ERC-7730 descriptor bundles (zip) for remote analysis."""

from __future__ import annotations

import base64
import io
import json
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# Limits (defense in depth; must stay within service max body size after base64)
_MAX_ZIP_BYTES = 4 * 1024 * 1024  # 4 MiB raw zip payload
_MAX_UNCOMPRESSED_BYTES = 16 * 1024 * 1024  # 16 MiB total uncompressed
_MAX_FILES = 256
_MAX_ENTRYPOINT_LEN = 1024


class BundleError(ValueError):
    """Invalid bundle graph, zip, or path policy."""


def default_bundle_root_for_descriptor(file_path: Path) -> Path:
    """Default include/bundle root is the descriptor's parent directory."""
    return file_path.resolve().parent


def _reject_uri_or_absolute(include_name: str) -> None:
    if not isinstance(include_name, str) or not include_name.strip():
        raise BundleError("includes must be a non-empty string")
    s = include_name.strip()
    parsed = urlparse(s)
    if parsed.scheme or parsed.netloc:
        raise BundleError("includes must be a relative local path, not a URL")
    if Path(s).is_absolute():
        raise BundleError("absolute include paths are not allowed")


def validate_local_include_string(include_name: str) -> None:
    """Shared validation for descriptor ``includes`` (local relative path only)."""
    _reject_uri_or_absolute(include_name)


def _safe_arcname(name: str) -> str:
    """Normalize zip member name to a safe relative POSIX path (no abs, no ..)."""
    if not name or name.startswith("/") or ".." in Path(name).parts:
        raise BundleError(f"unsafe zip member name: {name!r}")
    p = Path(name)
    if p.is_absolute():
        raise BundleError(f"unsafe zip member name: {name!r}")
    return p.as_posix()


def normalize_bundle_entrypoint(entrypoint: str) -> str:
    """Normalize user-provided entrypoint to a safe relative path string."""
    if not entrypoint or not entrypoint.strip():
        raise BundleError("bundle_entrypoint is required")
    if len(entrypoint) > _MAX_ENTRYPOINT_LEN:
        raise BundleError("bundle_entrypoint too long")
    s = entrypoint.strip().replace("\\", "/")
    if s.startswith("/") or ".." in Path(s).parts:
        raise BundleError("bundle_entrypoint must be a relative path without '..'")
    return Path(s).as_posix()


def collect_descriptor_files_for_bundle(entry: Path, root: Path) -> list[Path]:
    """Walk the include graph starting at entry; all files must stay under root (resolved)."""
    root_r = root.resolve()
    entry_r = entry.resolve()
    try:
        entry_r.relative_to(root_r)
    except ValueError as exc:
        raise BundleError("entry file is outside bundle root") from exc
    if not entry_r.is_file():
        raise BundleError("bundle entry must be a regular file")

    seen: set[Path] = set()
    stack: list[Path] = [entry_r]

    while stack:
        p = stack.pop()
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)

        try:
            with open(rp, encoding="utf-8") as f:
                data: Any = json.load(f)
        except Exception as exc:
            raise BundleError(f"invalid JSON in {rp.name}") from exc

        if not isinstance(data, dict):
            raise BundleError("descriptor must be a JSON object")

        inc = data.get("includes")
        if inc is None:
            continue
        if not isinstance(inc, str):
            raise BundleError("includes must be a string")
        _reject_uri_or_absolute(inc)

        nxt = (rp.parent / inc).resolve()
        try:
            nxt.relative_to(root_r)
        except ValueError as exc:
            raise BundleError("include escapes bundle root") from exc
        if not nxt.is_file():
            raise BundleError(f"included file not found: {inc}")
        stack.append(nxt)

    return sorted(seen, key=lambda x: str(x))


def build_descriptor_bundle_zip_bytes(entry: Path, root: Path) -> bytes:
    """Zip all files in the include graph; paths inside the zip are relative to root."""
    files = collect_descriptor_files_for_bundle(entry, root)
    root_r = root.resolve()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fpath in files:
            arcname = fpath.resolve().relative_to(root_r).as_posix()
            _ = _safe_arcname(arcname)
            zf.write(fpath, arcname=arcname)
    raw = buf.getvalue()
    if len(raw) > _MAX_ZIP_BYTES:
        raise BundleError("bundle zip exceeds maximum size")
    return raw


def bundle_zip_to_base64(entry: Path, root: Path) -> str:
    """Build a zip bundle and return standard base64 (for JSON transport)."""
    raw = build_descriptor_bundle_zip_bytes(entry, root)
    return base64.standard_b64encode(raw).decode("ascii")


def safe_extract_bundle_zip(zip_bytes: bytes, dest_dir: Path) -> None:
    """Extract zip bytes into dest_dir with Zip-slip and size guards."""
    if len(zip_bytes) > _MAX_ZIP_BYTES:
        raise BundleError("bundle zip exceeds maximum size")

    dest_dir = dest_dir.resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    total_uncompressed = 0
    n_files = 0

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for info in zf.infolist():
                name = info.filename.replace("\\", "/").strip()
                if not name or name.endswith("/"):
                    continue
                arc = _safe_arcname(name)
                target = (dest_dir / arc).resolve()
                try:
                    target.relative_to(dest_dir)
                except ValueError as exc:
                    raise BundleError("zip path escapes extract directory") from exc

                total_uncompressed += info.file_size
                if total_uncompressed > _MAX_UNCOMPRESSED_BYTES:
                    raise BundleError("bundle uncompressed size exceeds limit")
                n_files += 1
                if n_files > _MAX_FILES:
                    raise BundleError("too many files in bundle")

                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as out:
                    chunk = src.read()
                    out.write(chunk)
    except zipfile.BadZipFile as exc:
        raise BundleError("invalid bundle zip payload") from exc

    if n_files == 0:
        raise BundleError("bundle zip is empty")


def decode_bundle_zip_from_base64(b64: str) -> bytes:
    if not b64 or not str(b64).strip():
        raise BundleError("descriptor_bundle_base64 is empty")
    try:
        raw = base64.standard_b64decode(b64.strip())
    except Exception as exc:
        raise BundleError("invalid base64 bundle payload") from exc
    if len(raw) > _MAX_ZIP_BYTES:
        raise BundleError("bundle zip exceeds maximum size")
    return raw
