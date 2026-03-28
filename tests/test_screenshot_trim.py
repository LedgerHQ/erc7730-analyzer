"""Tests for screenshot dedup + trim logic using real App Runner captures.

Fixtures in tests/fixtures/screenshots/ contain actual PNG screenshots from
Speculos/cs-tester runs on App Runner (Uniswap v3 Router 2 analysis).

Three cases cover the scenarios observed in production:
  - case_5_no_dup:   5 unique frames (home, opt-in, review, data1, data2)
  - case_5_with_dup: 5 raw but only 3 unique (duplicates from slow QEMU polling)
  - case_6_tail_dup: 6 raw but 5 unique (duplicate at tail)
"""

import hashlib
from pathlib import Path

from utils.screenshots.runner import MIN_DATA_KEPT, TRIM_HEAD, TRIM_TAIL, _dedup_consecutive, _sort_key

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
        meaningful = deduped[start:end]
    elif deduped:
        meaningful = deduped[-1:]
    else:
        meaningful = []
    if len(meaningful) < MIN_DATA_KEPT and len(deduped) >= MIN_DATA_KEPT:
        meaningful = deduped[-MIN_DATA_KEPT:]
    return meaningful


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
        assert hashes[0] == hashes[1], "screenshot_1 and screenshot_2 should be identical"
        assert hashes[2] == hashes[3], "screenshot_3 and screenshot_4 should be identical"

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
        assert hashes[4] == hashes[5], "screenshot_5 and screenshot_6 should be identical"

        deduped = _dedup_consecutive(pngs)
        assert len(deduped) == 5


class TestTrimLogic:
    def test_case_5_no_dup_keeps_data(self):
        """5 unique: trim head 2, tail shrinks to 1 to preserve MIN_DATA_KEPT → keep 2."""
        pngs = _load_pngs(FIXTURES / "case_5_no_dup")
        deduped = _dedup_consecutive(pngs)
        kept = _trim(deduped)

        assert len(kept) >= MIN_DATA_KEPT
        assert kept[0].name == "screenshot_3.png"
        assert kept[1].name == "screenshot_4.png"

    def test_case_5_no_dup_no_home_screen(self):
        """Verify the kept screenshots don't include the home screen (first 2)."""
        pngs = _load_pngs(FIXTURES / "case_5_no_dup")
        preamble_hashes = set(_hashes(pngs[:TRIM_HEAD]))
        deduped = _dedup_consecutive(pngs)
        kept = _trim(deduped)

        for p in kept:
            h = hashlib.md5(p.read_bytes()).hexdigest()
            assert h not in preamble_hashes, f"{p.name} is a preamble screen"

    def test_case_5_with_dup_dedup_then_trim(self):
        """5 raw → 3 unique → trim head 2, remaining 1 → fallback to MIN_DATA_KEPT."""
        pngs = _load_pngs(FIXTURES / "case_5_with_dup")
        deduped = _dedup_consecutive(pngs)
        assert len(deduped) == 3

        kept = _trim(deduped)
        assert len(kept) >= MIN_DATA_KEPT

    def test_case_6_tail_dup_keeps_data(self):
        """6 raw → 5 unique → trim head 2, tail shrinks to 1 → keep 2."""
        pngs = _load_pngs(FIXTURES / "case_6_tail_dup")
        deduped = _dedup_consecutive(pngs)
        assert len(deduped) == 5

        kept = _trim(deduped)
        assert len(kept) >= MIN_DATA_KEPT
        assert kept[0].name == "screenshot_3.png"
        assert kept[1].name == "screenshot_4.png"

    def test_case_6_tail_dup_no_home_screen(self):
        """Verify kept screenshots don't include the home screen."""
        pngs = _load_pngs(FIXTURES / "case_6_tail_dup")
        home_hash = hashlib.md5(pngs[0].read_bytes()).hexdigest()
        deduped = _dedup_consecutive(pngs)
        kept = _trim(deduped)

        for p in kept:
            h = hashlib.md5(p.read_bytes()).hexdigest()
            assert h != home_hash, f"{p.name} is the home screen"


class TestTrimEdgeCases:
    def test_single_screenshot(self, tmp_path):
        p = tmp_path / "screenshot_1.png"
        p.write_bytes(b"single")
        kept = _trim([p])
        assert len(kept) == 1

    def test_empty(self):
        assert _trim([]) == []

    def test_exactly_trim_head(self, tmp_path):
        """2 screenshots (exactly TRIM_HEAD) → MIN_DATA_KEPT fallback keeps both."""
        pngs = []
        for i in range(TRIM_HEAD):
            p = tmp_path / f"screenshot_{i + 1}.png"
            p.write_bytes(f"content_{i}".encode())
            pngs.append(p)
        kept = _trim(pngs)
        assert len(kept) == MIN_DATA_KEPT

    def test_three_screenshots(self, tmp_path):
        """3 unique → trim head 2, remaining 1 → fallback to MIN_DATA_KEPT."""
        pngs = []
        for i in range(3):
            p = tmp_path / f"screenshot_{i + 1}.png"
            p.write_bytes(f"content_{i}".encode())
            pngs.append(p)
        kept = _trim(pngs)
        assert len(kept) >= MIN_DATA_KEPT

    def test_many_screenshots(self, tmp_path):
        """10 unique → trim 2 head + 2 tail = 6 kept."""
        pngs = []
        for i in range(10):
            p = tmp_path / f"screenshot_{i + 1}.png"
            p.write_bytes(f"unique_content_{i}".encode())
            pngs.append(p)
        kept = _trim(pngs)
        assert len(kept) == 6
        assert kept[0].name == "screenshot_3.png"
        assert kept[-1].name == "screenshot_8.png"
