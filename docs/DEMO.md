# Demo

Copy env first:

```powershell
copy .env.example .env
```

## Docker

```powershell
docker compose up --build
```

- Dashboard: [http://localhost:8000](http://localhost:8000)
- Health: [http://localhost:8000/health](http://localhost:8000/health)
- n8n: [http://localhost:5678](http://localhost:5678)

Import and **Publish** `n8n/workflows/lead-qualification.json` before running samples from the dashboard.

## Dashboard

Each sample posts to n8n `POST /webhook/lead-intake`. Watch the run under n8n **Executions**.

| Action | Outcome |
|--------|---------|
| **Invalid payload** | Validation fails; no CRM row |
| **Cold** | Qualified; no auto-draft; no Telegram qualification alert |
| **Warm** | Qualified; Telegram sales alert |
| **Hot** | Draft stored as `awaiting_approval`; Telegram sales alert |
| **Approve** | CRM `sent` / `contacted`; decision posted to Telegram |
| **Reject** | CRM `skipped`; customer is not contacted; rejection posted to Telegram |

Empty Telegram or Sheets credentials skip that channel and report `skipped_unconfigured`. That is not a successful send.

The bot must be a **channel administrator**. Set `TELEGRAM_CHAT_ID` to `-100…` or `@channelusername`.

## API

Use the webhook secret from `.env.example`.

```powershell
curl.exe -s -X POST http://localhost:8000/api/webhooks/leads -H "Content-Type: application/json" -H "X-Webhook-Secret: dev-webhook-secret-change-me" --data-binary "@examples/lead_hot.json"
curl.exe -s -X POST http://localhost:8000/api/leads/1/qualify?notify=false
curl.exe -s http://localhost:8000/api/leads/1
curl.exe -s -X POST http://localhost:8000/api/leads/1/followup/draft
curl.exe -s -X POST http://localhost:8000/api/leads/1/approve-followup
```

Reject instead of approve:

```powershell
curl.exe -s -X POST http://localhost:8000/api/leads/1/reject-followup
```

Duplicate webhook (same `external_id`) returns the existing lead with HTTP 200.

## n8n intake

1. Import `n8n/workflows/lead-qualification.json` (see [n8n/README.md](../n8n/README.md)).
2. Publish the workflow.
3. POST `examples/lead_hot.json` to `http://localhost:5678/webhook/lead-intake`.
4. Approve or reject from the dashboard **Approval queue**.

If `GOOGLE_SHEETS_SPREADSHEET_ID` is set and a Google Sheets credential is attached, intake upserts the qualified row. Otherwise the response reports `google_sheets: skipped_unconfigured`.

## Human-in-the-loop

Approve or reject **before** a draft exists returns 409. Approve a second time, or approve after reject, returns 409. Follow-up copy is never auto-sent.
