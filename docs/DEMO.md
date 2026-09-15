# Demo script

This walkthrough uses the **mock LLM** unless you set `OPENAI_API_KEY`. Telegram stays disabled unless both bot token and chat id are set. That is expected and honest.

Copy env first:

```powershell
copy .env.example .env
```

## Docker

```powershell
docker compose up --build
```

Backend: [http://localhost:8000/health](http://localhost:8000/health)
n8n: [http://localhost:5678](http://localhost:5678)

## Direct API (no n8n)

Use the demo webhook secret from `.env.example`.

```powershell
curl.exe -s -X POST http://localhost:8000/api/webhooks/leads -H "Content-Type: application/json" -H "X-Webhook-Secret: dev-webhook-secret-change-me" --data-binary "@examples/lead_hot.json"
```

Qualify (computes priority; hot leads attempt Telegram from this endpoint only):

```powershell
curl.exe -s -X POST http://localhost:8000/api/leads/1/qualify
```

Read the CRM record:

```powershell
curl.exe -s http://localhost:8000/api/leads/1
```

Follow-up draft (human still must approve before anything is "sent"):

```powershell
curl.exe -s -X POST http://localhost:8000/api/leads/1/followup/draft
curl.exe -s -X POST http://localhost:8000/api/leads/1/approve-followup
```

Duplicate webhook (same `external_id`) returns the existing lead:

```powershell
curl.exe -s -X POST http://localhost:8000/api/webhooks/leads -H "Content-Type: application/json" -H "X-Webhook-Secret: dev-webhook-secret-change-me" --data-binary "@examples/lead_hot.json"
```

Compare warm vs cold:

```powershell
curl.exe -s -X POST http://localhost:8000/api/webhooks/leads -H "Content-Type: application/json" -H "X-Webhook-Secret: dev-webhook-secret-change-me" --data-binary "@examples/lead_warm.json"
curl.exe -s -X POST http://localhost:8000/api/webhooks/leads -H "Content-Type: application/json" -H "X-Webhook-Secret: dev-webhook-secret-change-me" --data-binary "@examples/lead_cold.json"
```

Then qualify each new id. Mock LLM maps manufacturing / predictive maintenance → hot, SaaS scaling → warm, generic pricing → cold.

## n8n path

1. Import `n8n/workflows/lead-qualification.json` (see [n8n/README.md](../n8n/README.md)).
2. Activate the workflow.
3. POST `examples/lead_hot.json` to `http://localhost:5678/webhook/lead-intake` (or port 5679).
4. Confirm the backend has a qualified hot lead and a follow-up draft awaiting approval.
5. Approve via API **or** `POST /webhook/lead-approve` with `{ "lead_id": 1 }`. Customer WhatsApp/email send only if those adapters are configured.

## Batch dataset (100+ synthetic leads)

```powershell
python scripts/generate_dataset.py
python scripts/run_batch_demo.py
```

See [examples/dataset/README.md](../examples/dataset/README.md). Classification is produced at runtime; the files do not ship expected priority labels.

## Human-in-the-loop check

Calling approve **before** a draft exists must return 409. Calling approve a second time must return 409. The draft is never auto-sent.
