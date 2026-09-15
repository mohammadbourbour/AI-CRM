#!/usr/bin/env python3
"""Generate a deterministic synthetic lead dataset (seed=42).

Records do not include a pre-labeled priority/intent. Classification is produced
when the workflow and backend actually process the lead.
"""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path

SEED = 42
VALID_COUNT = 110
DUPLICATE_COUNT = 8
ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "examples" / "dataset"

FIRST_NAMES = [
    "Ava", "Noah", "Mia", "Liam", "Zoe", "Eli", "Nina", "Omar", "Rita", "Jules",
    "Priya", "Chen", "Sofia", "Mateo", "Hana", "Ibrahim", "Lucia", "Soren", "Amara", "Viktor",
    "Yara", "Diego", "Freya", "Kai", "Leila", "Theo", "Ines", "Ravi", "Noor", "Felix",
]
LAST_NAMES = [
    "Quill", "Nimbus", "Pebble", "Lumen", "Harbor", "Vesper", "Cobalt", "Maple", "Orchid", "Wren",
    "Sato", "Okoye", "Berg", "Duval", "Khan", "Silva", "Novak", "Okafor", "Bergstrom", "Moreau",
]
COMPANY_STEMS = [
    "Nimbus", "Cedar", "Helix", "Orion", "Pylon", "Quartz", "Harbor", "Lumen", "Fable", "Vellum",
    "Cobalt", "Aether", "Brine", "Tinder", "Sable", "Rowan", "Kite", "Meadow", "North", "Solace",
]
COMPANY_SUFFIXES = [
    "Labs", "Works", "Systems", "Analytics", "Industrial", "Energy", "Software", "Health",
    "Logistics", "Retail", "Finance", "Robotics", "Fabrics", "Metals", "Cloud",
]
JOB_TITLES = [
    "Chief Operating Officer", "VP of Operations", "Director of Reliability", "Plant Manager",
    "Head of Customer Success", "CTO", "Data Analyst", "Maintenance Supervisor",
    "RevOps Manager", "Procurement Lead", "Marketing Intern", "Founder",
    "IT Manager", "Quality Engineer", "Sales Operations Analyst",
]
SIZES = ["1-10", "11-50", "50-100", "100-500", "500-1000", "1000+"]
SOURCES = ["website", "form", "webhook", "referral", "outbound", "linkedin", "unknown"]
INDUSTRY_HINTS = [
    "manufacturing", "energy", "saas", "healthcare", "logistics", "retail",
    "finance", "construction", "education", "agriculture",
]


def _company(rng: random.Random) -> str:
    return f"{rng.choice(COMPANY_STEMS)} {rng.choice(COMPANY_SUFFIXES)} Synthetic Ltd"


def _person(rng: random.Random, index: int) -> tuple[str, str]:
    first = rng.choice(FIRST_NAMES)
    last = rng.choice(LAST_NAMES)
    name = f"{first} {last}"
    slug = f"{first}.{last}.{index:04d}".lower()
    return name, slug


def _industrial_message(rng: random.Random, company: str, title: str) -> str:
    sites = rng.randint(3, 18)
    return (
        f"I am {title} at {company}. We run about {sites} facilities and are evaluating an AI "
        "solution for predictive maintenance across multiple sites. Unplanned downtime on rotating "
        "equipment is our main cost driver. We want a discovery call this quarter and need "
        f"multi-site monitoring, not a generic dashboard. Timeline is {rng.choice(['6 weeks', 'this quarter', '90 days'])}."
    )


def _saas_message(rng: random.Random, company: str, title: str) -> str:
    seats = rng.choice([40, 80, 120, 200, 400])
    return (
        f"This is {title} at {company}, a SaaS company scaling onboarding for roughly {seats} seats. "
        "We are looking at automation for customer success handoffs and reducing time-to-value. "
        f"Not an emergency, but we will compare two vendors {rng.choice(['next month', 'this half', 'after QBR'])}."
    )


def _cold_message(rng: random.Random, company: str) -> str:
    return rng.choice(
        [
            f"Please send general pricing information for {company}. Just browsing for now.",
            "Do you have a one-pager? No active project, checking options.",
            "Is there a free plan? We might look at this next year.",
            "Add us to the newsletter. Not evaluating software at the moment.",
            "Curious how this compares to spreadsheets. No budget yet.",
        ]
    )


def _ambiguous_message(rng: random.Random, company: str, hint: str, title: str) -> str:
    return (
        f"{title} at {company} ({hint}). We have a loosely defined initiative around reporting "
        f"and maybe some automation. Budget is {rng.choice(['unclear', 'exploratory', 'not approved'])}. "
        f"Message length filler: {rng.choice(['short note.', 'We can share more on a call if useful.'])}"
    )


def build_valid_leads(rng: random.Random) -> list[dict]:
    leads: list[dict] = []
    buckets = (
        ["industrial"] * 40 + ["saas"] * 35 + ["cold"] * 25 + ["ambiguous"] * 10
    )
    rng.shuffle(buckets)
    for i, bucket in enumerate(buckets, start=1):
        name, slug = _person(rng, i)
        company = _company(rng)
        title = rng.choice(JOB_TITLES)
        hint = rng.choice(INDUSTRY_HINTS)
        if bucket == "industrial":
            hint = rng.choice(["manufacturing", "energy", "construction"])
            message = _industrial_message(rng, company, title)
        elif bucket == "saas":
            hint = "saas"
            message = _saas_message(rng, company, title)
        elif bucket == "cold":
            message = _cold_message(rng, company)
        else:
            message = _ambiguous_message(rng, company, hint, title)
        if rng.random() < 0.12:
            message = message + " " + ("Additional context. " * rng.randint(2, 6)).strip()
        domain = f"synth-{i:04d}.example"
        leads.append(
            {
                "external_id": f"syn-{i:04d}",
                "name": name,
                "email": f"{slug}@{domain}",
                "company": company,
                "company_size": rng.choice(SIZES),
                "source": rng.choice(SOURCES),
                "job_title": title,
                "industry_hint": hint,
                "message": message,
            }
        )
    return leads


def build_malformed() -> list[dict]:
    return [
        {"record_type": "invalid", "reason": "missing_email", "name": "No Email", "company": "Void Co", "message": "Hello"},
        {"record_type": "invalid", "reason": "bad_email", "name": "Bad Email", "email": "not-an-email", "company": "Void Co", "message": "Hello there"},
        {"record_type": "invalid", "reason": "empty_message", "name": "Quiet Person", "email": "quiet@synth.example", "company": "Void Co", "message": "   "},
        {"record_type": "invalid", "reason": "missing_name", "email": "noname@synth.example", "company": "Void Co", "message": "Need a demo"},
        {"record_type": "invalid", "reason": "missing_company", "name": "Solo", "email": "solo@synth.example", "message": "Need a demo next week"},
        {"record_type": "invalid", "reason": "empty_object"},
        {"record_type": "invalid", "reason": "null_message", "name": "Null Msg", "email": "nullmsg@synth.example", "company": "Void Co", "message": None},
        {"record_type": "invalid", "reason": "blank_company", "name": "Blank Co", "email": "blankco@synth.example", "company": "  ", "message": "Pricing please"},
        {"record_type": "invalid", "reason": "missing_all"},
        {"record_type": "invalid", "reason": "email_spaces", "name": "Spaced", "email": " spaced @ synth.example ", "company": "Void Co", "message": "Hi"},
    ]


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "external_id",
        "name",
        "email",
        "company",
        "company_size",
        "source",
        "job_title",
        "industry_hint",
        "message",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    rng = random.Random(SEED)
    valid = build_valid_leads(rng)
    malformed = build_malformed()
    duplicates = []
    for lead in valid[:DUPLICATE_COUNT]:
        copy = dict(lead)
        copy["record_type"] = "duplicate"
        copy["duplicate_of"] = lead["external_id"]
        duplicates.append(copy)

    batch: list[dict] = []
    for lead in valid:
        item = dict(lead)
        item["record_type"] = "valid"
        batch.append(item)
    batch.extend(duplicates)
    batch.extend(malformed)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    leads_json = OUT_DIR / "leads.json"
    leads_csv = OUT_DIR / "leads.csv"
    batch_json = OUT_DIR / "batch_payloads.json"
    manifest = OUT_DIR / "MANIFEST.json"

    leads_json.write_text(json.dumps(valid, indent=2) + "\n", encoding="utf-8")
    write_csv(leads_csv, valid)
    batch_json.write_text(json.dumps(batch, indent=2) + "\n", encoding="utf-8")
    manifest.write_text(
        json.dumps(
            {
                "seed": SEED,
                "valid_leads": len(valid),
                "duplicate_posts": len(duplicates),
                "malformed_records": len(malformed),
                "batch_items": len(batch),
                "notes": [
                    "No priority/intent labels are stored. The workflow classifies at runtime.",
                    "industry_hint describes the fictional company, not a model target.",
                    "All contacts use .example domains and synthetic names.",
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Wrote {len(valid)} leads, {len(duplicates)} duplicates, "
        f"{len(malformed)} malformed, batch={len(batch)} -> {OUT_DIR}"
    )


if __name__ == "__main__":
    main()
