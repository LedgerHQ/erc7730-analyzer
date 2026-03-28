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

from utils.screenshots.runner import (
    SINGLE_TX_TRIM_HEAD,
    SINGLE_TX_TRIM_TAIL,
    _dedup_consecutive,
    _sort_key,
    _strip_known_preamble,
    _strip_shared_screens,
    _trim_single_tx,
)

FIXTURES = Path(__file__).parent / "fixtures" / "screenshots"


def _load_pngs(case_dir: Path) -> list[Path]:
    return sorted(case_dir.glob("screenshot_*.png"), key=_sort_key)


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


class TestStripKnownPreamble:
    def test_strips_home_screen(self, tmp_path):
        """Removes all screenshots matching the known home hash."""
        home = tmp_path / "home.png"
        home.write_bytes(b"home_screen_content")
        data1 = tmp_path / "data1.png"
        data1.write_bytes(b"data_page_1")
        data2 = tmp_path / "data2.png"
        data2.write_bytes(b"data_page_2")
        home2 = tmp_path / "home2.png"
        home2.write_bytes(b"home_screen_content")

        home_hash = hashlib.md5(b"home_screen_content").hexdigest()
        tx = {"tx_hash": "0xaaa", "screenshots": [str(home), str(data1), str(data2), str(home2)]}

        result = _strip_known_preamble([tx], {home_hash}, "0xtest")
        assert len(result[0]["screenshots"]) == 2
        assert "data1" in result[0]["screenshots"][0]
        assert "data2" in result[0]["screenshots"][1]

    def test_no_preamble_hashes(self):
        """Returns unchanged when preamble_hashes is empty."""
        tx = {"tx_hash": "0xaaa", "screenshots": ["/some/path.png"]}
        result = _strip_known_preamble([tx], set(), "0xtest")
        assert result[0]["screenshots"] == ["/some/path.png"]

    def test_fallback_keeps_all_if_everything_matches(self, tmp_path):
        """If all screenshots match the home hash, keep originals as fallback."""
        f1 = tmp_path / "s1.png"
        f1.write_bytes(b"home")
        f2 = tmp_path / "s2.png"
        f2.write_bytes(b"home")

        home_hash = hashlib.md5(b"home").hexdigest()
        tx = {"tx_hash": "0xaaa", "screenshots": [str(f1), str(f2)]}

        result = _strip_known_preamble([tx], {home_hash}, "0xtest")
        assert len(result[0]["screenshots"]) == 2


class TestTrimSingleTx:
    def test_trims_head_and_tail(self, tmp_path):
        """7 screenshots → trim head=2 + tail=2 → 3 kept."""
        pngs = []
        for i in range(7):
            p = tmp_path / f"s{i}.png"
            p.write_bytes(f"content_{i}".encode())
            pngs.append(str(p))

        tx = {"tx_hash": "0xaaa", "screenshots": pngs}
        result = _trim_single_tx(tx, "0xtest")
        assert len(result["screenshots"]) == 7 - SINGLE_TX_TRIM_HEAD - SINGLE_TX_TRIM_TAIL

    def test_single_screenshot_unchanged(self, tmp_path):
        p = tmp_path / "s1.png"
        p.write_bytes(b"single")
        tx = {"tx_hash": "0xaaa", "screenshots": [str(p)]}
        result = _trim_single_tx(tx, "0xtest")
        assert len(result["screenshots"]) == 1

    def test_empty_screenshots(self):
        tx = {"tx_hash": "0xaaa", "screenshots": []}
        result = _trim_single_tx(tx, "0xtest")
        assert result["screenshots"] == []

    def test_keeps_at_least_one(self, tmp_path):
        """Even with aggressive trim, at least one screenshot is kept."""
        pngs = []
        for i in range(3):
            p = tmp_path / f"s{i}.png"
            p.write_bytes(f"c{i}".encode())
            pngs.append(str(p))
        tx = {"tx_hash": "0xaaa", "screenshots": pngs}
        result = _trim_single_tx(tx, "0xtest")
        assert len(result["screenshots"]) >= 1


class TestStripSharedScreens:
    def test_removes_shared_confirmation(self, tmp_path):
        """Shared 'hold-to-sign' screen is stripped from both txs."""
        shared_content = b"hold_to_sign_screen"
        tx1_dir = tmp_path / "tx1"
        tx2_dir = tmp_path / "tx2"
        tx1_dir.mkdir()
        tx2_dir.mkdir()

        (tx1_dir / "s1.png").write_bytes(b"tx1_data_page_1")
        (tx1_dir / "s2.png").write_bytes(b"tx1_data_page_2")
        (tx1_dir / "s3.png").write_bytes(shared_content)

        (tx2_dir / "s1.png").write_bytes(b"tx2_data_page_1")
        (tx2_dir / "s2.png").write_bytes(shared_content)

        tx_results = [
            {"tx_hash": "0xaaa", "screenshots": [str(tx1_dir / f"s{i}.png") for i in range(1, 4)]},
            {"tx_hash": "0xbbb", "screenshots": [str(tx2_dir / f"s{i}.png") for i in range(1, 3)]},
        ]

        cleaned = _strip_shared_screens(tx_results, "0xtest")

        assert len(cleaned[0]["screenshots"]) == 2
        assert len(cleaned[1]["screenshots"]) == 1

    def test_no_shared_keeps_all(self, tmp_path):
        """When no screenshots are shared, all are kept."""
        tx1_dir = tmp_path / "tx1"
        tx2_dir = tmp_path / "tx2"
        tx1_dir.mkdir()
        tx2_dir.mkdir()

        (tx1_dir / "s1.png").write_bytes(b"unique_1")
        (tx2_dir / "s1.png").write_bytes(b"unique_2")

        tx_results = [
            {"tx_hash": "0xaaa", "screenshots": [str(tx1_dir / "s1.png")]},
            {"tx_hash": "0xbbb", "screenshots": [str(tx2_dir / "s1.png")]},
        ]

        cleaned = _strip_shared_screens(tx_results, "0xtest")
        assert len(cleaned[0]["screenshots"]) == 1
        assert len(cleaned[1]["screenshots"]) == 1

    def test_fallback_if_all_shared(self, tmp_path):
        """If all screenshots would be removed, originals are kept."""
        tx1_dir = tmp_path / "tx1"
        tx2_dir = tmp_path / "tx2"
        tx1_dir.mkdir()
        tx2_dir.mkdir()

        (tx1_dir / "s1.png").write_bytes(b"same")
        (tx2_dir / "s1.png").write_bytes(b"same")

        tx_results = [
            {"tx_hash": "0xaaa", "screenshots": [str(tx1_dir / "s1.png")]},
            {"tx_hash": "0xbbb", "screenshots": [str(tx2_dir / "s1.png")]},
        ]

        cleaned = _strip_shared_screens(tx_results, "0xtest")
        assert len(cleaned[0]["screenshots"]) == 1
        assert len(cleaned[1]["screenshots"]) == 1


class TestRealFixtureTrim:
    """Test with real fixture data to verify no regression."""

    def test_case_5_no_dup_dedup_preserves_all(self):
        pngs = _load_pngs(FIXTURES / "case_5_no_dup")
        deduped = _dedup_consecutive(pngs)
        assert len(deduped) == 5

    def test_case_5_no_dup_no_preamble_after_home_strip(self):
        """After stripping home hash, preamble is reduced."""
        pngs = _load_pngs(FIXTURES / "case_5_no_dup")
        home_hash = hashlib.md5(pngs[0].read_bytes()).hexdigest()

        tx = {"tx_hash": "0xtest", "screenshots": [str(p) for p in pngs]}
        result = _strip_known_preamble([tx], {home_hash}, "0xtest")
        assert len(result[0]["screenshots"]) == 4

    def test_case_5_with_dup_dedup_then_single_trim(self):
        """5 raw → 3 unique → single-tx trim keeps at least 1."""
        pngs = _load_pngs(FIXTURES / "case_5_with_dup")
        deduped = _dedup_consecutive(pngs)
        assert len(deduped) == 3

        tx = {"tx_hash": "0xtest", "screenshots": [str(p) for p in deduped]}
        result = _trim_single_tx(tx, "0xtest")
        assert len(result["screenshots"]) >= 1

    def test_case_6_tail_dup_dedup_and_single_trim(self):
        """6 raw → 5 unique → single-tx trim: head=2 + tail=2 → 1 kept."""
        pngs = _load_pngs(FIXTURES / "case_6_tail_dup")
        deduped = _dedup_consecutive(pngs)
        assert len(deduped) == 5

        tx = {"tx_hash": "0xtest", "screenshots": [str(p) for p in deduped]}
        result = _trim_single_tx(tx, "0xtest")
        assert len(result["screenshots"]) == 1
