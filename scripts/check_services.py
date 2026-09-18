#!/usr/bin/env python3
"""Print whether backend, n8n, and the intake webhook are reachable."""

from __future__ import annotations

import json
import sys

import httpx

BACKEND = "http://localhost:8000"
N8N = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5678"


def check(title: str, ok: bool, detail: str) -> None:
    mark = "OK " if ok else "NO "
    print(f"{mark} {title}: {detail}")


def main() -> None:
    failures = 0
    try:
        health = httpx.get(f"{BACKEND}/health", timeout=5.0)
        body = health.json()
        check("backend", health.status_code == 200, json.dumps(body))
        if health.status_code != 200:
            failures += 1
    except httpx.HTTPError as exc:
        check("backend", False, str(exc))
        failures += 1

    try:
        meta = httpx.get(f"{BACKEND}/api/demo/meta", timeout=5.0).json()
        check("n8n webhook URL in backend", bool(meta.get("n8n_webhook_configured")), str(meta.get("n8n_webhook_configured")))
        check("sheets id", bool(meta.get("n8n_sheets_configured")), str(meta.get("n8n_sheets_configured")))
        check("telegram", meta.get("telegram") == "enabled", str(meta.get("telegram")))
    except httpx.HTTPError as exc:
        check("demo meta", False, str(exc))
        failures += 1

    try:
        n8n = httpx.get(f"{N8N}/healthz", timeout=5.0)
        check("n8n healthz", n8n.status_code < 500, f"HTTP {n8n.status_code}")
        if n8n.status_code >= 500:
            failures += 1
    except httpx.HTTPError as exc:
        check("n8n healthz", False, str(exc))
        failures += 1

    webhook = f"{N8N}/webhook/lead-intake"
    try:
        posted = httpx.post(
            webhook,
            json={"name": " ", "email": "not-an-email", "company": "", "message": ""},
            timeout=20.0,
        )
        if posted.status_code == 404:
            check("intake webhook", False, "404 — workflow is not Published")
            failures += 1
        elif posted.status_code >= 400:
            check("intake webhook", False, f"HTTP {posted.status_code} {posted.text[:200]}")
            failures += 1
        else:
            check("intake webhook", True, f"HTTP {posted.status_code} (Publish looks OK)")
    except httpx.HTTPError as exc:
        check("intake webhook", False, str(exc))
        failures += 1

    if failures:
        print("Fix the NO lines, then send a scenario from http://localhost:8000")
        raise SystemExit(1)
    print("Ready: Publish is live. Open the dashboard and send a scenario via n8n.")


if __name__ == "__main__":
    main()
