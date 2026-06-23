from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collectors.public_housing_contests.sh_probe import (  # noqa: E402
    BID_LIST_URL,
    LANDING_URL,
    SOURCE_CODE,
    SOURCE_NAME,
    build_g2b_bid_url,
    find_bid_list_url,
    is_official_url,
    keyword_flags,
    now_iso,
    parse_bid_list_rows,
    parse_landing_notice_links,
    parse_notice_detail,
    parse_page_count,
    sanitize_request_url,
    summarize_markdown,
)


USER_AGENT = "ModularHubSHProbe/0.1 (+https://github.com/mkpark1016-ctrl/modularhub-public)"
LOG_DIR = Path("logs")
ARTIFACT_DIR = LOG_DIR / "sh_probe_artifacts"


def sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def safe_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_minimal_list_snapshot(rows: list[dict[str, Any]]) -> str:
    row_html = "\n".join(
        "<tr>"
        f"<td>{row.get('row_no', '')}</td>"
        f"<td><a onclick=\"openBidblancDetail('{row.get('bid_no', '')}', '{row.get('bid_order', '')}')\">{row.get('title', '')}</a></td>"
        f"<td>{row.get('posted_at', '')}</td>"
        f"<td>{row.get('bid_open_at', '')}</td>"
        f"<td>{row.get('opening_at', '')}</td>"
        "</tr>"
        for row in rows[:20]
    )
    return (
        "<!doctype html><meta charset=\"utf-8\"><title>SH bid list minimal fixture</title>"
        "<table id=\"listTb\"><tbody>"
        f"{row_html}"
        "</tbody></table>"
    )


def make_minimal_detail_snapshot(detail: dict[str, Any]) -> str:
    attachments = "\n".join(
        f"<li><a onclick=\"existFile('{idx}')\">{item.get('name', '')}</a></li>"
        for idx, item in enumerate(detail.get("attachments", []))
    )
    down_list = [
        {
            "brdId": item.get("brd_id", ""),
            "seq": item.get("seq", ""),
            "fileSeq": item.get("file_seq", ""),
            "oriFileNm": item.get("name", ""),
            "fileTp": item.get("file_tp", ""),
        }
        for item in detail.get("attachments", [])
    ]
    return (
        "<!doctype html><meta charset=\"utf-8\"><title>SH detail minimal fixture</title>"
        f"<h2>{detail.get('title', '')}</h2>"
        f"<p>등록일 : {detail.get('posted_at', '')}</p>"
        "<dl><dt>첨부</dt><dd><ul>"
        f"{attachments}"
        "</ul></dd></dl>"
        "<script>"
        f"initParam = {{}}; initParam.downList = {json.dumps(down_list, ensure_ascii=False)};"
        "</script>"
    )


def notice_links_from_dom(links: list[dict[str, str]], base_url: str) -> list[dict[str, Any]]:
    notices: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in links:
        onclick = link.get("onclick") or ""
        match = re.search(r"viewLink\('([^']*?view\.do\?[^']*seq=(\d+)[^']*)'\)", onclick)
        if not match:
            continue
        source_record_id = match.group(2)
        if source_record_id in seen:
            continue
        seen.add(source_record_id)
        detail_url = urljoin(base_url, match.group(1))
        title = " ".join((link.get("text") or "").split())
        notices.append(
            {
                "source_record_id": source_record_id,
                "title": title,
                "detail_url": detail_url,
                "record_id_source": "seq",
                **keyword_flags(title),
            }
        )
    return notices


def bid_rows_from_dom(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for row in rows:
        onclick = row.get("onclick") or ""
        match = re.search(r"openBidblancDetail\('([^']+)'\s*,\s*'([^']+)'\)", onclick)
        cells = row.get("cells") or []
        title = " ".join((row.get("title") or "").split())
        if not match or len(cells) < 5 or not title:
            continue
        bid_no, bid_order = match.groups()
        parsed.append(
            {
                "row_no": int(cells[0]) if str(cells[0]).isdigit() else len(parsed) + 1,
                "title": title,
                "posted_at": cells[2],
                "bid_open_at": cells[3],
                "opening_at": cells[4],
                "bid_no": bid_no,
                "bid_order": bid_order,
                "source_record_id": f"{bid_no}:{bid_order}",
                "record_id_source": "openBidblancDetail(bidNtceNo,bidNtceOrd)",
                "detail_url": build_g2b_bid_url(bid_no, bid_order),
                "detail_url_kind": "g2b_link",
                **keyword_flags(title),
            }
        )
    return parsed


def request_recorder(events: list[dict[str, Any]]):
    def on_request(request) -> None:
        url = request.url
        if "i-sh.co.kr" not in url:
            return
        resource_type = request.resource_type
        if resource_type not in {"document", "xhr", "fetch"}:
            return
        events.append(
            {
                "kind": "request",
                "method": request.method,
                "resource_type": resource_type,
                "url": sanitize_request_url(url),
            }
        )

    return on_request


def response_recorder(events: list[dict[str, Any]]):
    def on_response(response) -> None:
        request = response.request
        url = response.url
        if "i-sh.co.kr" not in url:
            return
        resource_type = request.resource_type
        if resource_type not in {"document", "xhr", "fetch"}:
            return
        events.append(
            {
                "kind": "response",
                "method": request.method,
                "resource_type": resource_type,
                "status": response.status,
                "content_type": response.headers.get("content-type", ""),
                "url": sanitize_request_url(url),
            }
        )

    return on_response


def launch_browser(playwright, *, headed: bool, browser_channel: str):
    try:
        return playwright.chromium.launch(channel=browser_channel, headless=not headed)
    except Exception:
        if browser_channel:
            return playwright.chromium.launch(headless=not headed)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Playwright probe for SH public housing/private contest boards.")
    parser.add_argument("--max-pages", type=int, default=3, help="Maximum SH list pages to inspect.")
    parser.add_argument("--headed", action="store_true", help="Run Chromium with a visible window.")
    parser.add_argument("--save-snapshot", action="store_true", help="Also save sanitized full-ish HTML snippets for debugging.")
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--request-interval-seconds", type=float, default=1.0)
    parser.add_argument("--browser-channel", default="chrome", help="Preferred local browser channel. Use empty for bundled chromium.")
    args = parser.parse_args()

    before_hashes = {
        "business.json": sha256_file(Path("frontend/public/data/business.json")),
        "news.json": sha256_file(Path("frontend/public/data/news.json")),
        "meta.json": sha256_file(Path("frontend/public/data/meta.json")),
    }

    LOG_DIR.mkdir(exist_ok=True)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        print("Python Playwright is not installed. Run: python -m pip install -r requirements-playwright.txt", file=sys.stderr)
        raise SystemExit(2) from exc

    checked_at = now_iso()
    request_events: list[dict[str, Any]] = []
    failure_reason = ""
    screenshot_paths: list[str] = []
    snapshot_paths: list[str] = []
    list_rows: list[dict[str, Any]] = []
    notice_links: list[dict[str, Any]] = []
    detail_samples: list[dict[str, Any]] = []
    page_count_info = {"total_count": None, "current_page": None, "page_count": None}
    source_final_url = LANDING_URL
    bid_list_final_url = BID_LIST_URL

    with sync_playwright() as playwright:
        browser = launch_browser(playwright, headed=args.headed, browser_channel=args.browser_channel)
        context = browser.new_context(user_agent=USER_AGENT, locale="ko-KR")
        page = context.new_page()
        page.on("request", request_recorder(request_events))
        page.on("response", response_recorder(request_events))
        try:
            page.goto(LANDING_URL, wait_until="domcontentloaded", timeout=args.timeout_ms)
            page.wait_for_timeout(2000)
            source_final_url = page.url
            landing_html = page.content()
            landing_links = page.locator("a").evaluate_all(
                """links => links.map((a) => ({
                    text: (a.innerText || a.textContent || '').trim(),
                    href: a.href,
                    onclick: a.getAttribute('onclick') || ''
                }))"""
            )
            landing_shot = ARTIFACT_DIR / "sh_landing.png"
            page.screenshot(path=str(landing_shot), full_page=False)
            screenshot_paths.append(str(landing_shot))

            notice_links = notice_links_from_dom(landing_links, source_final_url)
            discovered_bid_url = next((link["href"] for link in landing_links if "BidblancList.do" in link.get("href", "")), "")
            discovered_bid_url = discovered_bid_url or find_bid_list_url(landing_html, source_final_url)
            if not is_official_url(discovered_bid_url):
                discovered_bid_url = BID_LIST_URL

            time.sleep(max(args.request_interval_seconds, 1.0))
            page.goto(discovered_bid_url, wait_until="domcontentloaded", timeout=args.timeout_ms)
            try:
                page.wait_for_selector("#listTb tbody tr td.txtL a", timeout=10000)
            except PlaywrightTimeoutError:
                failure_reason = "list_selector_timeout"
            page.wait_for_timeout(1000)
            bid_list_final_url = page.url
            list_html = page.content()
            list_text = page.locator("body").inner_text(timeout=10000)
            dom_rows = page.locator("#listTb tbody tr").evaluate_all(
                """rows => rows.map((tr) => {
                    const cells = Array.from(tr.querySelectorAll('td')).map((td) => (td.innerText || td.textContent || '').trim());
                    const a = tr.querySelector('td.txtL a');
                    return {
                        cells,
                        title: a ? (a.innerText || a.textContent || '').trim() : '',
                        onclick: a ? (a.getAttribute('onclick') || '') : ''
                    };
                })"""
            )
            list_rows = bid_rows_from_dom(dom_rows) or parse_bid_list_rows(list_html)
            page_count_info = parse_page_count(list_text)
            list_shot = ARTIFACT_DIR / "sh_bid_list.png"
            page.screenshot(path=str(list_shot), full_page=False)
            screenshot_paths.append(str(list_shot))

            minimal_list = ARTIFACT_DIR / "sh_bid_list_minimal.html"
            safe_write_text(minimal_list, make_minimal_list_snapshot(list_rows))
            snapshot_paths.append(str(minimal_list))

            if args.save_snapshot:
                full_list = ARTIFACT_DIR / "sh_bid_list_snapshot.html"
                safe_write_text(full_list, list_html[:200000])
                snapshot_paths.append(str(full_list))

            public_housing_notices = [item for item in notice_links if item.get("public_housing_candidate")]
            general_private_notices = [item for item in notice_links if item.get("general_private_contest_candidate")]
            detail_targets = public_housing_notices[:3] or general_private_notices[:1]
            for target in detail_targets[:3]:
                time.sleep(max(args.request_interval_seconds, 1.0))
                detail_url = target["detail_url"]
                page.goto(detail_url, wait_until="domcontentloaded", timeout=args.timeout_ms)
                page.wait_for_timeout(1000)
                detail_html = page.content()
                detail_text = page.locator("body").inner_text(timeout=10000)
                detail = parse_notice_detail(detail_html, page.url, detail_text)
                detail["source_kind"] = "sh_notice_detail"
                detail_samples.append(detail)
                detail_shot = ARTIFACT_DIR / f"sh_detail_{detail.get('source_record_id') or len(detail_samples)}.png"
                page.screenshot(path=str(detail_shot), full_page=False)
                screenshot_paths.append(str(detail_shot))
                minimal_detail = ARTIFACT_DIR / f"sh_detail_{detail.get('source_record_id') or len(detail_samples)}_minimal.html"
                safe_write_text(minimal_detail, make_minimal_detail_snapshot(detail))
                snapshot_paths.append(str(minimal_detail))
                if args.save_snapshot:
                    full_detail = ARTIFACT_DIR / f"sh_detail_{detail.get('source_record_id') or len(detail_samples)}_snapshot.html"
                    safe_write_text(full_detail, detail_html[:200000])
                    snapshot_paths.append(str(full_detail))
        except Exception as exc:
            failure_reason = failure_reason or f"probe_error: {type(exc).__name__}: {exc}"
            fail_shot = ARTIFACT_DIR / "sh_probe_failure.png"
            try:
                page.screenshot(path=str(fail_shot), full_page=False)
                screenshot_paths.append(str(fail_shot))
            except Exception:
                pass
        finally:
            page.close()
            context.close()
            browser.close()

    scanned_count = len(list_rows) + len(notice_links)
    keyword_match_count = sum(1 for item in [*list_rows, *notice_links] if item.get("public_housing_candidate"))
    general_private_count = sum(1 for item in [*list_rows, *notice_links] if item.get("general_private_contest_candidate"))
    result_keyword_count = sum(1 for item in [*list_rows, *notice_links, *detail_samples] if item.get("result_keyword"))
    candidate_requests = [
        event
        for event in request_events
        if event.get("resource_type") in {"document", "xhr", "fetch"}
        and not any(token in event.get("url", "").lower() for token in [".css", ".png", ".jpg", ".gif", ".woff"])
    ]
    has_independent_html = any(
        event.get("kind") == "response"
        and event.get("status") == 200
        and event.get("resource_type") == "document"
        and "BidblancList.do" in event.get("url", "")
        for event in candidate_requests
    )
    recommended_mode = "public_xhr" if has_independent_html and not failure_reason else "blocked_or_unstable"
    data_loading_mode = "public_html_document" if has_independent_html else "playwright_dom"

    after_hashes = {
        "business.json": sha256_file(Path("frontend/public/data/business.json")),
        "news.json": sha256_file(Path("frontend/public/data/news.json")),
        "meta.json": sha256_file(Path("frontend/public/data/meta.json")),
    }
    unchanged_public_json = before_hashes == after_hashes

    report = {
        "checked_at": checked_at,
        "source_code": SOURCE_CODE,
        "source_name": SOURCE_NAME,
        "source_url": LANDING_URL,
        "final_url": source_final_url,
        "official_bid_list_url": bid_list_final_url,
        "navigation_status": "ok" if not failure_reason else "warning",
        "parser_mode": "playwright_probe",
        "data_loading_mode": data_loading_mode,
        "list_selector_candidates": [
            "a[href*='BidblancList.do']",
            "#listTb tbody tr",
            "#listTb tbody tr td.txtL a",
            "a[onclick^='viewLink(']",
        ],
        "pagination_mode": {
            "mode": "post_form_getPaging_reqPage",
            "page_count": page_count_info,
            "selector_or_function": "getPaging(pageNo) with #pagingForm input[name=reqPage]",
            "max_pages_requested": args.max_pages,
        },
        "search_supported": {
            "bid_list": {
                "form": "#mainform",
                "fields": ["bsnsDivNm", "inqryDiv", "srchFr", "srchTo", "bidNtceNm"],
            },
            "notice_board": {
                "form": "#mainform",
                "fields": ["srchWord", "srchTp", "multi_itm_seq", "seq"],
            },
        },
        "record_id_candidate": {
            "sh_notice_detail": {
                "field": "seq",
                "example": detail_samples[0].get("source_record_id") if detail_samples else "",
                "recommended_id": "sh_contest:{seq}",
            },
            "sh_bid_g2b_link": {
                "field": "openBidblancDetail(bidNtceNo,bidNtceOrd)",
                "example": list_rows[0].get("source_record_id") if list_rows else "",
                "recommended_id": "sh_g2b_bid:{bidNtceNo}:{bidNtceOrd}",
            },
        },
        "detail_url_pattern": {
            "sh_notice_detail": "https://www.i-sh.co.kr/main/lay2/program/{path}/view.do?...&seq={seq}",
            "sh_bid_g2b_link": "https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo={bidNtceNo}&bidPbancOrd={bidNtceOrd}&pbancType=pbanc",
        },
        "attachment_pattern": "initParam.downList metadata; preview via /main/com/util/htmlConverter.do; download check via POST /main/com/file/existFile.do and existFile(num)",
        "scanned_count": scanned_count,
        "bid_list_count": len(list_rows),
        "notice_link_count": len(notice_links),
        "keyword_match_count": keyword_match_count,
        "general_private_contest_count": general_private_count,
        "result_keyword_count": result_keyword_count,
        "candidate_xhr": candidate_requests[:80],
        "bid_list_samples": list_rows[:10],
        "notice_link_samples": notice_links[:20],
        "detail_samples": detail_samples,
        "recommended_collector_mode": recommended_mode,
        "failure_reason": failure_reason,
        "captcha_or_login_detected": False,
        "screenshot_paths": screenshot_paths,
        "snapshot_paths": snapshot_paths,
        "public_json_hashes_before": before_hashes,
        "public_json_hashes_after": after_hashes,
        "public_json_unchanged": unchanged_public_json,
        "operating_plan": {
            "public_xhr": "Implement an HTTP HTML collector against BidblancList.do and seq-based notice view.do pages; Playwright is only needed for discovery.",
            "playwright_dom": "Only needed if SH changes the board to client-rendered DOM without reproducible public HTML.",
            "blocked_or_unstable": "Do not automate if CAPTCHA/login/access restriction appears; keep existing public data and report warning.",
        },
    }

    write_json(LOG_DIR / "sh_public_housing_contest_probe.json", report)
    safe_write_text(LOG_DIR / "sh_public_housing_contest_probe.md", summarize_markdown(report))
    print(
        json.dumps(
            {
                "source": SOURCE_CODE,
                "recommended_collector_mode": recommended_mode,
                "data_loading_mode": data_loading_mode,
                "scanned_count": scanned_count,
                "bid_list_count": len(list_rows),
                "notice_link_count": len(notice_links),
                "keyword_match_count": keyword_match_count,
                "general_private_contest_count": general_private_count,
                "result_keyword_count": result_keyword_count,
                "public_json_unchanged": unchanged_public_json,
                "report_path": str(LOG_DIR / "sh_public_housing_contest_probe.json"),
                "report_md_path": str(LOG_DIR / "sh_public_housing_contest_probe.md"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if unchanged_public_json else 1


if __name__ == "__main__":
    raise SystemExit(main())
