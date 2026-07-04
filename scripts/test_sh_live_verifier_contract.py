from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.verify_sh_public_housing_contests_live import (  # noqa: E402
    build_candidates,
    exit_code_for_status,
    write_outputs,
    write_parser_diagnostics,
)


def test_exit_codes() -> None:
    assert exit_code_for_status("success") == 0
    assert exit_code_for_status("success_no_matches") == 0
    assert exit_code_for_status("parser_mismatch") == 2
    assert exit_code_for_status("wrong_page_type") == 2
    assert exit_code_for_status("network_error") == 3
    assert exit_code_for_status("blocked") == 4
    assert exit_code_for_status("http_error") == 5
    assert exit_code_for_status("failed", "mutation_detected") == 1


def test_candidates_and_artifacts() -> None:
    publishable = SimpleNamespace(
        is_public_opportunity=True,
        source_record_id="306155",
        source_name="SH",
        source_type="public_agency_contest",
        title="Public housing private contest",
        posted_at="2026-06-24",
        stage="notice",
        classification_status="confirmed",
        modular_evidence=["private participation public housing"],
        board_url="https://www.i-sh.co.kr/main/lay2/program/S1T316C7212/www/m_2428/BidblancList.do",
        source_page_url="https://www.i-sh.co.kr/main/lay2/program/S1T294C299/www/brd/m_255/view.do?seq=306155",
        original_url="https://www.i-sh.co.kr/main/lay2/program/S1T294C299/www/brd/m_255/view.do?seq=306155",
        exact_link_verified=True,
        attachments=[{"name": "notice.pdf"}],
        link_validation_reason="verified",
    )
    result_record = SimpleNamespace(
        **{**publishable.__dict__, "source_record_id": "306156", "is_public_opportunity": False, "stage": "result", "classification_status": "result"}
    )
    discovery = SimpleNamespace(
        bid_no="R26BK01594237",
        bid_order="000",
        title="Linked G2B bid",
        posted_at="2026-06-22",
        source_page_url="https://www.i-sh.co.kr/main/lay2/program/S1T316C7212/www/m_2428/BidblancList.do",
        detail_url="https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo=R26BK01594237&bidPbancOrd=000&pbancType=pbanc",
    )
    stats = SimpleNamespace(records=[publishable, result_record], g2b_discoveries=[discovery, discovery])
    candidates = build_candidates(stats)
    assert len(candidates) == 3
    assert sum(1 for candidate in candidates if candidate["publish_eligible"]) == 1
    assert next(candidate for candidate in candidates if candidate["stage"] == "result")["publish_eligible"] is False
    assert next(candidate for candidate in candidates if candidate["classification"] == "g2b_linked")["publish_eligible"] is False

    report = {
        "checked_at": "2026-06-24T00:00:00+09:00",
        "status": "success_no_matches",
        "failure_reason": "",
        "source_url": "https://www.i-sh.co.kr/main/lay2/program/S1T316C7212/www/m_2428/BidblancList.do",
        "list_url": "https://www.i-sh.co.kr/main/lay2/program/S1T316C7212/www/m_2428/BidblancList.do",
        "final_url": "https://www.i-sh.co.kr/main/lay2/program/S1T316C7212/www/m_2428/BidblancList.do",
        "collector_mode": "http_html",
        "detected_page_type": "sh_bid_list",
        "http_status": 200,
        "row_count": 0,
        "rows_with_title": 0,
        "rows_with_identifier": 0,
        "parse_success_ratio": 0,
        "detail_link_candidate_count": 0,
        "unique_detail_candidate_count": 0,
        "detail_fetch_target_count": 0,
        "scanned_count": 0,
        "sh_notice_count": 0,
        "g2b_linked_count": 0,
        "confirmed_count": 0,
        "review_required_count": 0,
        "result_count": 0,
        "exact_link_count": 0,
        "attachment_count": 0,
        "publish_eligible_count": 0,
        "parser_mismatch": False,
        "parser_mismatch_reasons": [],
        "public_json_unchanged": True,
        "db_unchanged": True,
        "env_unchanged": True,
    }
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        output_dir = Path(tmp)
        write_outputs(report, [], output_dir, [])
        assert (output_dir / "report.json").exists()
        assert (output_dir / "report.md").exists()
        assert (output_dir / "stdout.log").exists()
        assert (output_dir / "candidates.json").read_text(encoding="utf-8").strip() == "[]"


def test_parser_mismatch_diagnostics() -> None:
    html = """
    <html>
      <head><title>SH Bid List</title><style>.secret{display:none}</style></head>
      <body>
        <script>window.token = "do-not-store";</script>
        <form action="/search.do">
          <table><tbody><tr><td><input type="hidden" name="session" value="abc123"><a href="BidblancView.do?seq=123">broken row</a></td></tr></tbody></table>
        </form>
      </body>
    </html>
    """
    report = {
        "page_sha256": "fixture-sha",
        "html_byte_count": len(html.encode("utf-8")),
        "page_title": "SH Bid List",
        "final_url": "https://www.i-sh.co.kr/main/lay2/program/S1T316C7212/www/m_2428/BidblancList.do",
        "detected_page_type": "sh_bid_list",
        "total_count": None,
        "current_page": None,
        "page_count": None,
        "empty_state_evidence": "ambiguous_zero_rows",
        "parser_mismatch_reasons": ["ambiguous_zero_rows"],
    }
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        output_dir = Path(tmp)
        assert write_parser_diagnostics(html, report, output_dir)
        structure_path = output_dir / "page_structure.json"
        excerpt_path = output_dir / "list_table_excerpt.html"
        assert structure_path.exists()
        assert excerpt_path.exists()
        structure = __import__("json").loads(structure_path.read_text(encoding="utf-8"))
        assert structure["page_sha256"] == "fixture-sha"
        assert structure["table_count"] == 1
        assert structure["form_count"] == 1
        assert structure["seq_parameter_count"] == 1
        assert structure["empty_state_evidence"] == "ambiguous_zero_rows"
        assert structure["parser_mismatch_reasons"] == ["ambiguous_zero_rows"]
        excerpt = excerpt_path.read_text(encoding="utf-8")
        assert "do-not-store" not in excerpt
        assert "<script" not in excerpt.lower()
        assert "<style" not in excerpt.lower()
        assert "abc123" not in excerpt
        assert "{masked}" in excerpt
        assert len(excerpt.encode("utf-8")) <= 50 * 1024


def main() -> int:
    test_exit_codes()
    test_candidates_and_artifacts()
    test_parser_mismatch_diagnostics()
    print("SH live verifier contract tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
