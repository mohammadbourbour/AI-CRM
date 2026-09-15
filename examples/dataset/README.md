# Synthetic lead dataset

Deterministic fake leads for demos. Seed **42**. Contacts use `.example` domains and invented names — not real people.

There is **no** stored `priority` or `intent` label. The running workflow and backend produce classification.

## Files

| File | Contents |
|------|----------|
| `leads.json` / `leads.csv` | 110 valid leads |
| `batch_payloads.json` | 110 valid + 8 duplicate `external_id` posts + 10 malformed records |
| `MANIFEST.json` | Counts and seed |
| `last_run_summary.json` | Written by the batch runner (gitignored if you prefer; committed only if you save a demo run) |

## Regenerate

```powershell
python scripts/generate_dataset.py
```

## Batch through n8n

Workflow must be imported **and activated**.

```powershell
python scripts/run_batch_demo.py
```

Optional:

```powershell
python scripts/run_batch_demo.py --n8n-url http://localhost:5679/webhook/lead-intake --limit 20
```

The console summary reports how many leads were processed, qualified in CRM, routed, skipped (validation), and failed.
