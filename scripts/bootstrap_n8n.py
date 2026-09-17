#!/usr/bin/env python3
"""Import Lead Qualification into a running n8n instance. Does not Publish.

Morning flow: docker compose up → this script (optional) → open n8n → click Publish.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "n8n" / "workflows" / "lead-qualification.json"
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5678"
OWNER = {
    "email": "demo@aicrm.local",
    "firstName": "Demo",
    "lastName": "Owner",
    "password": "DemoN8n!23456",
}


def wait_health(client: httpx.Client) -> None:
    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            response = client.get("/healthz", timeout=3.0)
            if response.status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise SystemExit("n8n did not become ready on " + BASE + " — run docker compose up first.")


def main() -> None:
    workflow = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    workflow["active"] = False
    with httpx.Client(base_url=BASE, timeout=30.0, follow_redirects=True) as client:
        wait_health(client)
        setup = client.post("/rest/owner/setup", json=OWNER)
        if setup.status_code not in {200, 201, 400, 409}:
            print("owner setup HTTP", setup.status_code, setup.text[:300])
        login = client.post("/rest/login", json={"emailOrLdapLoginId": OWNER["email"], "password": OWNER["password"]})
        if login.status_code >= 400:
            login = client.post("/rest/login", json={"email": OWNER["email"], "password": OWNER["password"]})
        if login.status_code >= 400:
            print("Could not log in to n8n automatically.")
            print("Do this in the UI instead:")
            print("  1. Open", BASE)
            print("  2. Create the owner account")
            print("  3. Workflows → Import from File → n8n/workflows/lead-qualification.json")
            print("  4. Click Publish (leave it inactive until you are ready)")
            raise SystemExit(1)
        existing = client.get("/rest/workflows")
        names = []
        if existing.status_code == 200:
            payload = existing.json()
            items = payload.get("data") if isinstance(payload, dict) else payload
            names = [item.get("name") for item in items or [] if isinstance(item, dict)]
        if "Lead Qualification" in names:
            print("Workflow already imported. Open", BASE, "and click Publish.")
            return
        created = client.post("/rest/workflows", json=workflow)
        if created.status_code >= 400:
            print("Import failed HTTP", created.status_code, created.text[:500])
            print("Import from the n8n UI: Workflows → Import from File.")
            raise SystemExit(1)
        print("Imported Lead Qualification (inactive).")
        print("Open", BASE, "→ Lead Qualification → Publish")
        print("Then open http://localhost:8000 and send a scenario with via=n8n.")


if __name__ == "__main__":
    main()
