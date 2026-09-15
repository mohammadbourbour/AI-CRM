#!/usr/bin/env python3
"""Feed examples/dataset/batch_payloads.json through the n8n lead-intake webhook.

Produces a concise execution summary. Classification is whatever the running
workflow/backend returned — this script does not pre-label priority.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BATCH = ROOT / "examples" / "dataset" / "batch_payloads.json"
DEFAULT_SUMMARY = ROOT / "examples" / "dataset" / "last_run_summary.json"


def _post_json(url: str, payload: dict, timeout: float) -> tuple[int, dict | str]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw
    except urllib.error.URLError as exc:
        return 0, str(exc.reason if getattr(exc, "reason", None) else exc)


def _get_json(url: str, timeout: float) -> tuple[int, dict | list | str]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        return 0, str(exc)


def _probe_n8n(urls: list[str], timeout: float) -> str | None:
    """Pick a webhook whose n8n host responds. Does not create a lead."""
    for url in urls:
        host = url.split("/webhook/")[0] + "/"
        code, _ = _get_json(host, timeout=min(timeout, 5.0))
        if code != 0:
            return url
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch-feed synthetic leads through n8n")
    parser.add_argument("--batch", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument(
        "--n8n-url",
        default="",
        help="Full lead-intake webhook URL. If omitted, 5678 then 5679 are probed.",
    )
    parser.add_argument("--backend-url", default="http://localhost:8000")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--sleep", type=float, default=0.05)
    parser.add_argument("--limit", type=int, default=0, help="Process only the first N batch items")
    args = parser.parse_args()

    items = json.loads(args.batch.read_text(encoding="utf-8"))
    if args.limit:
        items = items[: args.limit]

    urls = (
        [args.n8n_url]
        if args.n8n_url
        else [
            "http://localhost:5678/webhook/lead-intake",
            "http://localhost:5679/webhook/lead-intake",
        ]
    )
    n8n_url = _probe_n8n(urls, timeout=min(args.timeout, 8.0))
    if not n8n_url:
        print(
            "Could not reach the n8n lead-intake webhook.\n"
            "Import and activate n8n/workflows/lead-qualification.json, then retry.\n"
            "Tried: " + ", ".join(urls),
            file=sys.stderr,
        )
        return 2

    print(f"Using n8n webhook: {n8n_url}")
    print(f"Batch items: {len(items)}")

    results = []
    outcomes: Counter[str] = Counter()
    routed: Counter[str] = Counter()
    http_fail = 0
    seen_external: set[str] = set()
    duplicate_hits = 0

    for index, item in enumerate(items, start=1):
        drop = {"record_type", "reason", "duplicate_of", "industry_hint"}
        payload = {k: v for k, v in item.items() if k not in drop and v is not None}

        code, body = _post_json(n8n_url, payload, timeout=args.timeout)
        outcome = "http_error"
        if isinstance(body, dict):
            outcome = str(body.get("outcome") or ("processed" if code == 200 else "failed"))
        if code == 0 or code >= 400:
            http_fail += 1
            if outcome == "processed":
                outcome = "failed"
        outcomes[outcome] += 1
        if isinstance(body, dict) and body.get("routed"):
            routed[str(body["routed"])] += 1

        ext = payload.get("external_id")
        if isinstance(ext, str) and ext:
            if ext in seen_external:
                duplicate_hits += 1
            seen_external.add(ext)

        results.append(
            {
                "index": index,
                "record_type": item.get("record_type"),
                "external_id": payload.get("external_id"),
                "http_status": code,
                "outcome": outcome,
                "lead_id": body.get("lead_id") if isinstance(body, dict) else None,
                "priority": body.get("priority") if isinstance(body, dict) else None,
                "routed": body.get("routed") if isinstance(body, dict) else None,
                "review_queue": body.get("review_queue") if isinstance(body, dict) else None,
                "errors": body.get("errors") if isinstance(body, dict) else [body],
            }
        )
        if index % 10 == 0 or index == len(items):
            print(f"  {index}/{len(items)} posted")
        if args.sleep:
            time.sleep(args.sleep)

    crm_code, crm = _get_json(args.backend_url.rstrip("/") + "/api/leads", timeout=args.timeout)
    crm_rows = crm if isinstance(crm, list) else []
    crm_priority = Counter(str(row.get("priority")) for row in crm_rows)
    crm_status = Counter(str(row.get("status")) for row in crm_rows)
    qualified = sum(1 for row in crm_rows if row.get("status") in {"qualified", "contacted", "meeting", "proposal", "won"})
    awaiting = sum(1 for row in crm_rows if row.get("follow_up_status") == "awaiting_approval")

    processed = outcomes.get("processed", 0)
    skipped = outcomes.get("validation_failed", 0) + outcomes.get("skipped", 0)
    failed = (
        outcomes.get("failed", 0)
        + outcomes.get("qualification_failed", 0)
        + outcomes.get("http_error", 0)
        + outcomes.get("crm_create_failed", 0)
    )

    summary = {
        "n8n_webhook": n8n_url,
        "batch_items": len(items),
        "processed": processed,
        "qualified_in_crm": qualified,
        "routed": dict(routed),
        "skipped": skipped,
        "failed": failed,
        "duplicate_posts_in_batch": duplicate_hits,
        "outcomes": dict(outcomes),
        "http_transport_failures": http_fail,
        "crm": {
            "reachable": crm_code == 200,
            "lead_count": len(crm_rows),
            "by_priority": dict(crm_priority),
            "by_status": dict(crm_status),
            "awaiting_approval": awaiting,
        },
        "results": results,
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print("\n=== Execution summary ===")
    print(f"Processed:     {processed}")
    print(f"Qualified CRM: {qualified}")
    print(f"Routed:        {dict(routed)}")
    print(f"Skipped:       {skipped}")
    print(f"Failed:        {failed}")
    print(f"Duplicate posts (same external_id in this batch): {duplicate_hits}")
    print(f"CRM leads:     {len(crm_rows)} | awaiting approval: {awaiting}")
    print(f"Wrote {args.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
