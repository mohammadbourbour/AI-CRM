# n8n: AI Sales Lead Workflow

n8n **orchestrates**. The FastAPI backend remains the source of truth for CRM persistence, deterministic priority, and the human-approval flag on follow-up.

This workflow is truthful: missing API keys are skipped, not faked as successful sends.

## What it demonstrates

- Webhook intake (`/webhook/lead-intake`)
- Payload validation before CRM
- Optional local lead enrichment (domain / seniority — no fake enrichment API)
- Official **AI Agent** + **OpenAI Chat Model** as primary structured qualification
- Official **Google Gemini Chat Model** as fallback when OpenAI is missing or unusable
- JSON parse + schema checks before CRM writes
- Official **Telegram** node for the optional sales alert
- Official **WhatsApp Business Cloud** node after human approval
- Official **Google Sheets** nodes (`Create sheet` + `Append or update row`) after qualify
- Human-approval webhook before customer-facing WhatsApp / email
- HTTP Request only for FastAPI CRM and Resend (no first-party Resend node)
- Backend CRM create + qualify
- Dedicated review responses when validation or `/qualify` fails
- Priority routing (hot vs not)

## Flow (intake)

1. `Lead Intake Webhook`
2. `Validate Incoming Lead` — invalid payloads go to **Invalid Payload Review** (no CRM write)
3. `Optional Lead Enrichment` — local only
4. `AI Agent` (OpenAI Chat Model) if `OPENAI_API_KEY` is set **and** an OpenAI credential is attached, else skip
5. `AI Agent — Gemini Fallback` if OpenAI failed/skipped and `GEMINI_API_KEY` is set **and** a Gemini credential is attached
6. `Parse & Validate LLM JSON` — n8n pre-qualification is **audit only**; backend still qualifies
7. `Create Lead in CRM` → `POST /api/webhooks/leads` with `X-Webhook-Secret`
8. `Backend Qualify Lead` → `POST /api/leads/{id}/qualify` (retries, then review path on failure)
9. `Get CRM Lead`
10. Official Google Sheets: `Plan Sheets Export` → `Create sheet` (continue if the tab already exists) → `Append or update row in sheet` matched on CRM `id`. Skipped when `GOOGLE_SHEETS_SPREADSHEET_ID` is empty
11. `Resume CRM Lead` so `$json.priority` is the CRM record again
12. If `priority == hot` → `Draft Follow-up (HITL)` then optional Telegram sales alert
13. Respond with `outcome`, routing, and channel statuses (`sent` | `exported` | `skipped_unconfigured` | `awaiting_human_approval` | `not_applicable`)

Warm/cold leads are not auto-drafted. Customer WhatsApp/email are **not** sent on intake.

## Human approval (separate webhook)

After a hot lead has `follow_up_status=awaiting_approval`:

```
POST /webhook/lead-approve
{ "lead_id": 1 }
```

The workflow:

1. Loads the CRM lead
2. Blocks unless `follow_up_status == awaiting_approval`
3. Calls `POST /api/leads/{id}/approve-followup` (backend mock send — CRM state)
4. Official WhatsApp node — only if the WhatsApp credential is attached and `WHATSAPP_PHONE_NUMBER_ID` + `WHATSAPP_TO` are set
5. Email adapter (HTTP Resend) — only if `RESEND_API_KEY` and `EMAIL_FROM` are set
6. Unconfigured adapters return `skipped_unconfigured`, never `sent`

## Telegram: two optional paths (do not double-enable casually)

| Channel | When | Default |
|---------|------|---------|
| Backend Telegram | Inside `POST /api/leads/{id}/qualify` when priority is hot and backend Telegram env is set | Off if tokens empty |
| n8n sales alert | After hot draft, only if `N8N_TELEGRAM_ALERTS=true` **and** n8n has Telegram env | **Off** (`false`) |

Customer follow-up text is never auto-sent.

## Import

1. `docker compose up --build` from the repo root.
2. Open n8n (`http://localhost:5678`, or `N8N_PORT_HOST=5679`).
3. **Workflows → Import from File** → `n8n/workflows/lead-qualification.json`.
4. Map credentials on the official nodes:
   - **OpenAI Chat Model** → OpenAI account
   - **Google Gemini Chat Model** → Google Gemini (PaLM) API (fallback only)
   - **Send a text message** → Telegram account (already wired to `Telegram account` if that credential exists)
   - **Send message** → WhatsApp account
   - **Create sheet** and **Append or update row in sheet** → Google Sheets OAuth2 account
5. Publish / activate the workflow.

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
| `OPENAI_API_KEY` / `OPENAI_MODEL` | Gate + default model for the OpenAI Chat Model sub-node. Also create an **OpenAI** credential in n8n. |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | Gate for the Gemini fallback agent. Also create a **Google Gemini (PaLM)** credential. |
| `N8N_TELEGRAM_ALERTS` | Set `true` to allow n8n Telegram sales alerts |
| `TELEGRAM_CHAT_ID` | Chat id for the official Telegram node (bot token lives in the Telegram credential) |
| `WHATSAPP_PHONE_NUMBER_ID` / `WHATSAPP_TO` | Recipient routing for the official WhatsApp node (access token lives in the WhatsApp credential) |
| `RESEND_API_KEY` / `EMAIL_FROM` | Optional email send after approval (HTTP — Resend has no official n8n node) |
| `GOOGLE_SHEETS_SPREADSHEET_ID` | Spreadsheet for the official Sheets nodes. Empty → skip export |
| `GOOGLE_SHEETS_WORKSHEET` | Tab name (default `Qualified Leads`). Create sheet makes it if missing |

Empty keys → skip that provider/channel and say so in the JSON response.

n8n upserts one qualified lead per intake (match on `id`). The backend `POST /api/exports/google-sheets` is a complementary full snapshot using a service account — it does not replace the official n8n nodes.

## Webhook URLs (after activate)

```
POST http://localhost:5678/webhook/lead-intake
POST http://localhost:5678/webhook/lead-approve
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
