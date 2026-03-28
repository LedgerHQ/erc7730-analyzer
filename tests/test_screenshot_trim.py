"""Tests for screenshot dedup + trim logic.

Fixtures in tests/fixtures/screenshots/ contain actual PNG screenshots from
Speculos/cs-tester runs on App Runner (Uniswap v3 Router 2 analysis).
"""

import hashlib
from pathlib import Path

from utils.screenshots.runner import (
    MIN_DATA_KEPT,
    TRIM_HEAD,
    TRIM_TAIL,
    _dedup_consecutive,
    _sort_key,
)

FIXTURES = Path(__file__).parent / "fixtures" / "screenshots"


def _load_pngs(case_dir: Path) -> list[Path]:
    return sorted(case_dir.glob("screenshot_*.png"), key=_sort_key)


def _trim(deduped: list[Path]) -> list[Path]:
    """Reproduce the trim logic from runner.py."""
    if len(deduped) > TRIM_HEAD:
        start = TRIM_HEAD
        remaining = len(deduped) - start
        tail = TRIM_TAIL if remaining > TRIM_TAIL + MIN_DATA_KEPT else max(0, remaining - MIN_DATA_KEPT)
        end = len(deduped) - tail
        result = deduped[start:end]
    elif deduped:
        result = deduped[-1:]
    else:
        result = []
    if len(result) < MIN_DATA_KEPT and len(deduped) >= MIN_DATA_KEPT:
        result = deduped[-MIN_DATA_KEPT:]
    return result


def _hashes(pngs: list[Path]) -> list[str]:
    return [hashlib.md5(p.read_bytes()).hexdigest() for p in pngs]


class TestDedupConsecutive:
    def test_empty(self):
        assert _dedup_consecutive([]) == []

    def test_no_duplicates(self):
        pngs = _load_pngs(FIXTURES / "case_5_no_dup")
        assert len(pngs) == 5
        deduped = _dedup_consecutive(pngs)
        assert len(deduped) == 5

    def test_removes_consecutive_dups(self):
        """case_5_with_dup: screenshot_1==screenshot_2, screenshot_3==screenshot_4."""
        pngs = _load_pngs(FIXTURES / "case_5_with_dup")
        assert len(pngs) == 5
        hashes = _hashes(pngs)
        assert hashes[0] == hashes[1]
        assert hashes[2] == hashes[3]

        deduped = _dedup_consecutive(pngs)
        assert len(deduped) == 3
        assert deduped[0].name == "screenshot_1.png"
        assert deduped[1].name == "screenshot_3.png"
        assert deduped[2].name == "screenshot_5.png"

    def test_removes_tail_dup(self):
        """case_6_tail_dup: screenshot_5==screenshot_6."""
        pngs = _load_pngs(FIXTURES / "case_6_tail_dup")
        assert len(pngs) == 6
        hashes = _hashes(pngs)
        assert hashes[4] == hashes[5]

        deduped = _dedup_consecutive(pngs)
        assert len(deduped) == 5


class TestTrimLogic:
    def test_preserves_min_data(self, tmp_path):
        """5 items: TRIM_HEAD=2, tail reduced to keep MIN_DATA_KEPT=2."""
        pngs = [tmp_path / f"s{i}.png" for i in range(5)]
        for i, p in enumerate(pngs):
            p.write_bytes(f"content_{i}".encode())
        kept = _trim(pngs)
        assert len(kept) >= MIN_DATA_KEPT

    def test_normal_8_items(self, tmp_path):
        """8 items → head=2, tail=2 → 4 kept."""
        pngs = [tmp_path / f"s{i}.png" for i in range(8)]
        for i, p in enumerate(pngs):
            p.write_bytes(f"content_{i}".encode())
        kept = _trim(pngs)
        assert len(kept) == 4

    def test_normal_9_items(self, tmp_path):
        """9 items → head=2, tail=2 → 5 kept."""
        pngs = [tmp_path / f"s{i}.png" for i in range(9)]
        for i, p in enumerate(pngs):
            p.write_bytes(f"content_{i}".encode())
        kept = _trim(pngs)
        assert len(kept) == 5

    def test_short_3_items(self, tmp_path):
        """3 items → head=2, remaining=1, fallback to last 2."""
        pngs = [tmp_path / f"s{i}.png" for i in range(3)]
        for i, p in enumerate(pngs):
            p.write_bytes(f"content_{i}".encode())
        kept = _trim(pngs)
        assert len(kept) >= MIN_DATA_KEPT

    def test_single_item(self, tmp_path):
        p = tmp_path / "s1.png"
        p.write_bytes(b"single")
        kept = _trim([p])
        assert len(kept) == 1

    def test_empty(self):
        assert _trim([]) == []

    def test_7_items_preserves_data(self, tmp_path):
        """7 items (dedup removed 1 preamble): head=2, tail=2, keeps 3."""
        pngs = [tmp_path / f"s{i}.png" for i in range(7)]
        for i, p in enumerate(pngs):
            p.write_bytes(f"content_{i}".encode())
        kept = _trim(pngs)
        assert len(kept) == 3

    def test_2_items_unchanged(self, tmp_path):
        """2 items ≤ TRIM_HEAD → fallback to MIN_DATA_KEPT."""
        pngs = [tmp_path / f"s{i}.png" for i in range(2)]
        for i, p in enumerate(pngs):
            p.write_bytes(f"content_{i}".encode())
        kept = _trim(pngs)
        assert len(kept) == 2


class TestRealFixtureTrim:
    """Test with real fixture data."""

    def test_case_5_no_dup(self):
        pngs = _load_pngs(FIXTURES / "case_5_no_dup")
        deduped = _dedup_consecutive(pngs)
        kept = _trim(deduped)
        assert len(kept) >= MIN_DATA_KEPT

    def test_case_5_with_dup(self):
        """5 raw → 3 unique → fallback keeps last 2."""
        pngs = _load_pngs(FIXTURES / "case_5_with_dup")
        deduped = _dedup_consecutive(pngs)
        assert len(deduped) == 3
        kept = _trim(deduped)
        assert len(kept) >= MIN_DATA_KEPT

    def test_case_6_tail_dup(self):
        """6 raw → 5 unique → head=2, tail reduced, keeps ≥2."""
        pngs = _load_pngs(FIXTURES / "case_6_tail_dup")
        deduped = _dedup_consecutive(pngs)
        assert len(deduped) == 5
        kept = _trim(deduped)
        assert len(kept) >= MIN_DATA_KEPT
