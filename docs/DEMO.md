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

Backend: [http://localhost:8000](http://localhost:8000) (client dashboard)
Health: [http://localhost:8000/health](http://localhost:8000/health)
n8n: [http://localhost:5678](http://localhost:5678)

## Client dashboard

Open `/`. Leave **ارسال به n8n** selected after the workflow is **Published**. Each click POSTs that sample to ` /webhook/lead-intake `. Watch the run under n8n **Executions**.

The **مستقیم CRM** radio is only a fallback if n8n is down.

| Button | Outcome |
|--------|---------|
| **رد اعتبارسنجی** | Invalid payload; validate fails; **no CRM row** |
| **Cold / Warm** | Qualified with that priority; no auto-draft |
| **Hot** | Draft stored as `awaiting_approval` |
| **قبول پیش‌نویس** | `mock_sent`, lead `contacted` |
| **رد پیش‌نویس** | `skipped`, lead stays `qualified`, draft kept for audit |

1. Validates and enriches the lead (same steps as n8n)
2. Writes to CRM and qualifies (backend LLM or mock + deterministic priority)
3. Drafts a follow-up only for hot leads (still HITL)
4. Posts the **analysis result** to the Telegram channel when `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set

Empty Telegram credentials skip the channel post and show `skipped_unconfigured`. That is not a successful send.

Add the bot as a **channel administrator**, then set `TELEGRAM_CHAT_ID` to `-100…` or `@channelusername`.

## Direct API (no n8n)

Use the demo webhook secret from `.env.example`.

```powershell
curl.exe -s -X POST http://localhost:8000/api/webhooks/leads -H "Content-Type: application/json" -H "X-Webhook-Secret: dev-webhook-secret-change-me" --data-binary "@examples/lead_hot.json"
```

Qualify (computes priority; every successful qualify attempts a Telegram **result** post to the configured chat/channel):

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
# or reject instead of approve:
# curl.exe -s -X POST http://localhost:8000/api/leads/1/reject-followup
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
6. If `GOOGLE_SHEETS_SPREADSHEET_ID` is set and a Google Sheets credential is attached, the intake path upserts the qualified row. Otherwise the webhook JSON reports `google_sheets: skipped_unconfigured`.

Optional backend snapshot (does not replace the n8n nodes):

```powershell
curl.exe -s -X POST http://localhost:8000/api/exports/google-sheets
```

## Batch dataset (100+ synthetic leads)

```powershell
python scripts/generate_dataset.py
python scripts/run_batch_demo.py
```

See [examples/dataset/README.md](../examples/dataset/README.md). Classification is produced at runtime; the files do not ship expected priority labels.

## Human-in-the-loop check

Calling approve or reject **before** a draft exists must return 409. Calling approve a second time, or approve after reject, must return 409. The draft is never auto-sent.
