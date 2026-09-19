# Design decisions

## Mock providers by default

`GROQ_API_KEY` empty → `MockLLMProvider` (keyword heuristics). Logs state this is not production inference.

Telegram credentials empty → notify is disabled. The app does not crash and does not pretend a message was delivered.

After a successful `/qualify` with `notify=true`, the backend posts the qualification result for hot and warm leads. n8n intake uses `notify=false` and sends the sales alert from the Telegram node instead.

## Backend Telegram on follow-up

Approve and reject post the draft and decision to Telegram from FastAPI. Qualification alerts on the n8n path come from n8n, not from `/qualify`.

## Webhook shared-secret (minimal security)

`POST /api/webhooks/leads` requires `X-Webhook-Secret` matching `WEBHOOK_SECRET`. Missing or wrong values return 401.

This is a **minimal** shared-secret check for `POST /api/webhooks/leads`. Missing or wrong values return 401. Direct `POST /api/leads` is unauthenticated and should not be exposed on a public network without additional controls.

## Insert-first idempotency

Webhook duplicates are handled by inserting first. If SQLite raises `IntegrityError` on unique `external_id`, the session is rolled back, the existing row is loaded, and the API returns that lead with 200. A pre-check-then-insert would race under concurrent requests.

## Qualification errors are retryable

Failed `/qualify` sets `qualification_error` and leaves `status` unchanged (typically `new`). HTTP 503. A later `/qualify` can succeed and clear the error.

## Strict structured output plus one retry

Groq uses OpenAI-compatible Chat Completions with structured JSON (`openai/gpt-oss-20b` by default). Pydantic validation always runs. On validation failure the provider retries once with the error text in the prompt, then fails closed with 503.

## n8n channels

n8n sends Telegram sales alerts when `TELEGRAM_CHAT_ID` is set, and upserts Google Sheets when `GOOGLE_SHEETS_SPREADSHEET_ID` is set. Empty credentials skip the adapter and return `skipped_unconfigured`.

Google Sheets runs on intake after a successful `/qualify`: header row then **Append or update row** matched on CRM `id`. Backend `POST /api/exports/google-sheets` is a complementary full-worksheet snapshot using a service account.

## n8n LLM

The n8n pre-qualify step uses the official **AI Agent** + **Groq Chat Model**. `GROQ_API_KEY` gates the branch; a Groq credential in n8n authenticates the node. Parse failures do not invent a qualification record.

HTTP Request remains only for the FastAPI CRM. Google Sheets uses the official node.

## Human approval before send

AI may write `draft_message`. The backend will not mark follow-up `sent` until `POST /api/leads/{id}/approve-followup`. Human **reject** (`POST /api/leads/{id}/reject-followup`) sets `skipped`, keeps the draft for audit, and does not contact the customer. The decision is posted to Telegram. CRM send status is `mock_sent`.

## Documented gaps

- **No pagination** on `GET /api/leads`.
- **Logs mask PII.** Webhook and qualification logs use `mask_email` (`j***@domain.com`).

## Other constraints

- SQLite, single process.
- Priority is never taken from the LLM as the stored value.
- LLM output cannot execute tools or fetch arbitrary URLs.
