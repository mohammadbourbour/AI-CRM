# Design decisions

Portfolio implementation demonstrating an AI-assisted sales and CRM automation workflow. Not a production CRM.

## Mock providers by default

`OPENAI_API_KEY` empty → `MockLLMProvider` (keyword heuristics). Logs state this is not production inference.

Telegram credentials empty → notify is disabled. The app does not crash and does not pretend a message was delivered.

## Backend Telegram on qualify

Telegram for hot leads is still invoked from `POST /api/leads/{id}/qualify` after deterministic priority is `hot` (backend unchanged). n8n intake does not send customer messages. n8n Telegram sales alerts are opt-in via `N8N_TELEGRAM_ALERTS`.

## Webhook shared-secret (minimal security)

`POST /api/webhooks/leads` requires `X-Webhook-Secret` matching `WEBHOOK_SECRET`. Missing or wrong values return 401.

This is a **deliberate minimal-security trade-off**: it stops anonymous lead injection on a local demo port. It is **not** production-grade auth (no rotation, no per-client credentials, no signatures, no mTLS). Direct `POST /api/leads` is intentionally left open for local API exploration.

## Insert-first idempotency

Webhook duplicates are handled by inserting first. If SQLite raises `IntegrityError` on unique `external_id`, the session is rolled back, the existing row is loaded, and the API returns that lead with 200. A pre-check-then-insert would race under concurrent requests.

## Qualification errors are retryable

Failed `/qualify` sets `qualification_error` and leaves `status` unchanged (typically `new`). HTTP 503. A later `/qualify` can succeed and clear the error.

## Strict structured output plus one retry

When `OPENAI_MODEL` supports `response_format=json_schema` with `strict: true` (for example `gpt-4o-mini`), that mode is used. Otherwise `json_object`. Pydantic validation always runs. On validation failure the provider retries once with the error text in the prompt, then fails closed with 503.

## n8n optional channels

n8n can optionally call official Telegram and WhatsApp nodes, or Resend over HTTP, after explicit configuration. Empty credentials skip the adapter and return `skipped_unconfigured`. The workflow does not mark those sends as successful.

Default `N8N_TELEGRAM_ALERTS=false` so n8n does not send Telegram unless you opt in. Backend Telegram on `/qualify` is unchanged.

Customer WhatsApp/email run only from the `lead-approve` webhook after a CRM draft exists.

## n8n LLM fallback

OpenAI is the primary n8n LLM via the official **AI Agent** + **OpenAI Chat Model**. Gemini runs only if OpenAI is missing or unusable, via a second **AI Agent** + **Google Gemini Chat Model**. Env keys gate those branches; n8n credentials actually authenticate the nodes. Parse failures do not invent a qualification record.

HTTP Request remains only for the FastAPI CRM and Resend. There is no official Resend node.

## Human approval before send

AI may write `draft_message`. The backend will not mark follow-up `sent` until `POST /api/leads/{id}/approve-followup` (or the n8n `lead-approve` webhook that calls that endpoint). Backend send is a **mock** (`mock_sent`). Real WhatsApp/email happen only if those n8n adapters are configured, after the same approval.

## Documented gaps that stay open

- **No pagination** on `GET /api/leads`. The list is the full table ordered by `created_at` desc. Fine for a demo dataset; not fine for production volume.
- **Logs mask PII.** Webhook and qualification logs use `mask_email` (`j***@domain.com`). Raw email/phone is not written to those log lines.

## Other constraints

- SQLite, single process.
- No frontend.
- Priority is never taken from the LLM as the stored value.
- LLM output cannot execute tools or fetch arbitrary URLs.
