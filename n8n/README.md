# n8n: AI Sales Lead Workflow

n8n **orchestrates**. The FastAPI backend remains the source of truth for CRM persistence, deterministic priority, and the human-approval flag on follow-up.

This workflow is truthful: missing API keys are skipped, not faked as successful sends.

## What it does

- Webhook intake (`/webhook/lead-intake`)
- Payload validation before CRM
- Local enrichment (domain / seniority)
- Official **AI Agent** + **Groq Chat Model** (`openai/gpt-oss-20b`)
- Official **Telegram** node for hot and warm sales alerts
- Official **Google Sheets** nodes after qualify
- HTTP Request for FastAPI CRM
- Human approval in the CRM dashboard; Telegram posts the decision from the backend
- Dedicated review responses when validation or `/qualify` fails
- Priority routing (hot vs not)

## Flow (intake)

1. `Lead Intake Webhook`
2. `Validate Incoming Lead` — invalid payloads go to **Invalid Payload Review** (no CRM write)
3. `Optional Lead Enrichment` — local only
4. `AI Agent` (Groq Chat Model) if `GROQ_API_KEY` is set **and** a Groq credential is attached, else skip
5. `Parse & Validate LLM JSON` — n8n pre-qualification is **audit only**; backend still qualifies
6. `Create Lead in CRM` → `POST /api/webhooks/leads` with `X-Webhook-Secret`
7. `Backend Qualify Lead` → `POST /api/leads/{id}/qualify?notify=false`
8. `Get CRM Lead`
9. Official Google Sheets: headers + upsert by CRM `id`. Skipped when `GOOGLE_SHEETS_SPREADSHEET_ID` is empty
10. If `priority == hot` → `Draft Follow-up (HITL)`
11. Telegram sales alert for hot and warm
12. Respond with `outcome`, routing, and channel statuses

Warm/cold leads are not auto-drafted. Follow-up copy is not sent to a customer on intake.

## Human approval

Approve or reject in the dashboard **Approval queue**. The backend updates CRM and posts the decision to Telegram.

## Telegram

| Channel | When |
|---------|------|
| n8n sales alert | After qualify, hot or warm, when `TELEGRAM_CHAT_ID` is set |
| Backend follow-up | After dashboard approve or reject |

Qualify is called with `notify=false` so the backend does not double-post the qualification alert.

Customer follow-up text is never auto-sent.

## Import

1. `docker compose up --build` from the repo root.
2. Open n8n (`http://localhost:5678`, or `N8N_PORT_HOST=5679`).
3. **Workflows → Import from File** → `n8n/workflows/lead-qualification.json`.
4. Map credentials on the official nodes:
   - **Groq Chat Model** → Groq account (API key from [console.groq.com](https://console.groq.com/keys))
   - **Send a text message** → Telegram account
   - **Ensure sheet headers** and **Append or update row in sheet** → Google Sheets OAuth2
5. **Publish / activate** the workflow. Until you Publish, dashboard runs return 503 (`webhook is not registered`).

Optional helper (imports the JSON, does **not** Publish):

```powershell
python scripts/bootstrap_n8n.py
```

Re-generate the JSON after editing `n8n/build_workflow.py`:

```powershell
python n8n/build_workflow.py
```

## Environment (n8n container)

Passed through `docker-compose.yml`:

| Variable | Purpose |
|----------|---------|
| `BACKEND_BASE_URL` | `http://backend:8000` on Docker |
| `WEBHOOK_SECRET` | Must match backend |
| `GROQ_API_KEY` / `GROQ_MODEL` | Gate + default model for the Groq Chat Model sub-node. Also create a **Groq** credential in n8n. |
| `TELEGRAM_CHAT_ID` | Chat id for the official Telegram node (bot token lives in the Telegram credential) |
| `GOOGLE_SHEETS_SPREADSHEET_ID` | Spreadsheet ID. Empty → skip |
| `GOOGLE_SHEETS_WORKSHEET` | Tab name (default `Qualified Leads`). Create sheet makes it if missing |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` | Injected into n8n as `CREDENTIALS_OVERWRITE_DATA` so you do not paste OAuth secrets in the UI |

`$env.VAR` in the editor shows `[ERROR: not accessible via UI, please run node]`. That is a preview limitation. Execute the node or run the workflow; the value is read at runtime.

Do not put `GROQ_BASE_URL=https://api.groq.com/openai/v1` on the n8n Groq credential. The Groq node already appends `/openai/v1`.

Empty keys → skip that provider/channel and say so in the JSON response.

n8n upserts one qualified lead per intake (match on `id`). The backend `POST /api/exports/google-sheets` is a complementary full snapshot using a service account — it does not replace the official n8n nodes.

## Webhook URLs (after activate)

```
POST http://localhost:5678/webhook/lead-intake
```

If host port 5678 is taken, use 5679.

n8n's public webhook does **not** need `X-Webhook-Secret`. n8n adds it when calling the backend.

## Batch dataset

See [examples/dataset/README.md](../examples/dataset/README.md).

```powershell
python scripts/generate_dataset.py
python scripts/run_batch_demo.py
```

The runner prints processed / qualified / routed / skipped / failed counts. It does not invent classifications.
