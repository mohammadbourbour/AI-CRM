# Architecture

Inbound lead qualification and CRM automation. n8n orchestrates the workflow; FastAPI is the source of truth for persistence, priority, and follow-up state.

## Diagram

```mermaid
flowchart TD
    LeadSource[LeadSource] --> n8n[n8n_Webhook]
    n8n --> ValidateN8n[Validate_and_enrich]
    ValidateN8n --> Groq[AI_Agent_Groq]
    Groq -->|ok| ParseJSON[Parse_structured_JSON]
    Groq -->|fail_or_skip| ParseJSON
    ParseJSON --> WebhookAPI["POST /api/webhooks/leads"]
    WebhookAPI --> AuthCheck{X-Webhook-Secret}
    AuthCheck -->|401| Reject[Reject]
    AuthCheck -->|ok| Normalize[LeadNormalization]
    Normalize --> InsertLead[Insert_Lead]
    InsertLead -->|IntegrityError| ExistingLead[Return_existing_200]
    InsertLead -->|ok| NewLead[Return_new_lead]
    n8n --> QualifyAPI["POST /api/leads/id/qualify?notify=false"]
    QualifyAPI --> LLM[LLM_Provider]
    LLM --> Validate[Pydantic_Validation]
    Validate -->|fail| RetryOnce[Retry_once_with_error]
    RetryOnce -->|fail| QualError[Set_qualification_error_503]
    Validate -->|ok| PriorityRules[Deterministic_Priority]
    RetryOnce -->|ok| PriorityRules
    PriorityRules --> CRM[(SQLite_CRM)]
    n8n --> SheetsPlan{Sheets_id_set?}
    SheetsPlan -->|yes| EnsureHeaders[Ensure_sheet_headers]
    EnsureHeaders --> UpsertRow[Append_or_update_row]
    SheetsPlan -->|no| SkipSheets[skipped_unconfigured]
    UpsertRow --> PriorityIF{n8n_IF_hot}
    SkipSheets --> PriorityIF
    PriorityIF -->|yes| FollowupDraft["POST /api/leads/id/followup/draft"]
    PriorityIF -->|no| SkipDraft[Skip_draft]
    FollowupDraft --> AwaitingApproval[awaiting_approval]
    n8n --> Telegram[Telegram_hot_or_warm]
    AwaitingApproval --> HumanApprove["Dashboard approve or reject"]
    HumanApprove --> TelegramDecision[Telegram_followup_decision]
```

## Responsibilities

| Layer | Owns | Does not own |
|-------|------|----------------|
| n8n | Webhook intake, payload validation, local enrichment, AI Agent pre-qualify, CRM HTTP orchestration, Google Sheets upsert, Telegram sales alert | Deterministic CRM priority, SQLite persistence |
| FastAPI | Validation, CRM, priority, HITL flag, Telegram on follow-up decisions | Canvas orchestration |
| LLM | Intent, industry, pain points, summary, draft text | Database writes, sending messages, arbitrary tools |
| SQLite | Lead records | Business rules |

## Notification paths

n8n posts a sales-team Telegram alert for **hot** and **warm** leads when `TELEGRAM_CHAT_ID` is set. Cold leads are skipped. Intake calls `POST /api/leads/{id}/qualify?notify=false` so the backend does not send a second qualification message.

Dashboard **Approve** / **Reject** call FastAPI. The backend updates CRM and posts the decision (including the draft) to Telegram.

After a successful qualify, n8n upserts the lead into Google Sheets when `GOOGLE_SHEETS_SPREADSHEET_ID` is set. Empty id skips with `channels.google_sheets = skipped_unconfigured`. FastAPI `POST /api/exports/google-sheets` can replace the worksheet with a full qualified-lead snapshot (service account) — CRM remains the source of truth.

n8n never auto-sends follow-up copy on intake. Hot routing calls `POST /api/leads/{id}/followup/draft` only to store the CRM draft.

## AI vs deterministic

**Deterministic**

- Payload validation and normalization
- Webhook shared-secret check
- Insert-first idempotency
- Priority thresholds
- CRM persistence and status transitions
- Human approval gate
- Mock send after approval

**AI**

- Industry / intent / product-fit classification
- Pain-point extraction
- Summary and recommended next action
- Follow-up draft text

## n8n orchestration vs backend qualification

n8n can call Groq to produce structured JSON **before** CRM writes. That output is validated in n8n and stored on the workflow response as `ai_prequalify`. The backend `/qualify` call remains the CRM source of truth for persisted priority.

If `GROQ_API_KEY` is absent, n8n skips the Groq node (`skipped_unconfigured`) and still persists + qualifies via the backend mock/Groq provider.

If backend `/qualify` returns 503, n8n takes the **Qualification Failed Review** path: the lead stays retryable, no draft, no customer send.

## Status state machine

Lead `status` allowed transitions:

```
new  --successful /qualify-->  qualified
qualified  --approve-followup or PATCH-->  contacted | lost
contacted  --PATCH-->  meeting | proposal | lost
meeting  --PATCH-->  proposal | lost
proposal  --PATCH-->  won | lost
won, lost  (terminal)
```

Rules:

- `new → qualified` happens only on a **successful** `/qualify`. PATCH cannot make that jump.
- Failed `/qualify` returns **503**, sets `qualification_error`, and **does not change** `status`. The lead stays retryable.
- Successful re-qualify of an already-qualified (or later) lead updates AI fields and priority but keeps the current `status`.
- Failed `/followup/draft` returns 503 and leaves `follow_up_status` unchanged.

Follow-up `follow_up_status`:

```
not_started → awaiting_approval → approved → sent
                              ↘ skipped (reject-followup or PATCH)
```

`draft_ready` is in the enum for completeness; the draft endpoint writes `awaiting_approval` directly.

Approve and reject happen from the dashboard (or `POST /api/leads/{id}/approve-followup` / `reject-followup`). Reject keeps the draft for audit, sets `skipped`, and never contacts the customer. The approved draft is posted to Telegram for the sales team. CRM follow-up status becomes `sent` (`mock_sent`).

## Providers

If `GROQ_API_KEY` is empty, qualification uses `MockLLMProvider` (keyword heuristics). That is **not** production inference.

If Telegram credentials are empty, notify is skipped and logged as disabled. Qualification still succeeds.
