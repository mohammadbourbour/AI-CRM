#!/usr/bin/env python3
"""Build n8n/workflows/lead-qualification.json (n8n 2.x compatible).

Official n8n nodes are used for AI, Telegram, WhatsApp, and Google Sheets. HTTP Request is
kept only for the FastAPI CRM and Resend (no first-party Resend node).
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "workflows" / "lead-qualification.json"

# Credential placeholders. Telegram uses the account already present in this n8n
# instance; OpenAI / Gemini / WhatsApp are mapped in the editor after import.
OPENAI_CRED = {"openAiApi": {"id": "openai-account", "name": "OpenAI account"}}
GEMINI_CRED = {"googlePalmApi": {"id": "google-gemini-account", "name": "Google Gemini(PaLM) Api"}}
TELEGRAM_CRED = {"telegramApi": {"id": "SRDVCdkvP7R2ebhu", "name": "Telegram account"}}
WHATSAPP_CRED = {"whatsAppApi": {"id": "whatsapp-account", "name": "WhatsApp account"}}
SHEETS_CRED = {"googleSheetsOAuth2Api": {"id": "google-sheets-account", "name": "Google Sheets account"}}

SHEET_FIELDS = [
    "id",
    "external_id",
    "name",
    "email",
    "company",
    "source",
    "priority",
    "status",
    "industry",
    "intent",
    "product_fit",
    "recommended_next_action",
    "created_at",
]

AGENT_SYSTEM = (
    "You are a B2B sales qualification assistant. Do not invent contact details "
    "or URLs. Return JSON only with keys industry, intent (low|medium|high), "
    "product_fit (unknown|low|medium|high), priority (cold|warm|hot), "
    "pain_points (array of strings), summary, recommended_next_action."
)

JS_VALIDATE = r"""
const item = $input.first().json;
const body = item.body && typeof item.body === 'object' ? item.body : item;
const errors = [];
const name = typeof body.name === 'string' ? body.name.trim() : '';
const emailRaw = typeof body.email === 'string' ? body.email.trim().toLowerCase() : '';
const company = typeof body.company === 'string' ? body.company.trim() : '';
const message = typeof body.message === 'string' ? body.message.trim() : '';
if (!name) errors.push('name is required');
if (!company) errors.push('company is required');
if (!message) errors.push('message is required');
if (!emailRaw || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(emailRaw)) errors.push('valid email is required');
const known = new Set(['website', 'form', 'webhook', 'referral', 'outbound', 'linkedin', 'unknown']);
let source = typeof body.source === 'string' ? body.source.trim().toLowerCase() : 'unknown';
if (!known.has(source)) source = 'unknown';
const lead = { name, email: emailRaw, company, message, source };
const companySize = body.company_size ? String(body.company_size).trim() : '';
const externalId = body.external_id ? String(body.external_id).trim() : '';
const assignedTo = body.assigned_to ? String(body.assigned_to).trim() : '';
if (companySize) lead.company_size = companySize;
if (externalId) lead.external_id = externalId;
if (assignedTo) lead.assigned_to = assignedTo;
return [{ json: { valid: errors.length === 0, errors, lead, context: { job_title: body.job_title || null } } }];
""".strip()

JS_ENRICH = r"""
const data = $input.first().json;
const lead = data.lead;
const domain = (lead.email || '').includes('@') ? lead.email.split('@')[1] : '';
const title = (data.context && data.context.job_title) || '';
const t = String(title).toLowerCase();
let seniority = 'unknown';
if (/(chief|cto|ceo|cfo|coo|vp|vice president|director|head|founder)/.test(t)) seniority = 'executive';
else if (/(manager|lead|principal|supervisor)/.test(t)) seniority = 'manager';
else if (/(intern|student|junior)/.test(t)) seniority = 'junior';
else if (title) seniority = 'ic';
data.enrichment = {
  email_domain: domain || null,
  guessed_website: domain ? ('https://www.' + domain) : null,
  job_title: title || null,
  seniority,
  enrichment_source: 'deterministic_local',
  enrichment_api: 'disabled',
};
return [{ json: data }];
""".strip()

JS_BUILD_PROMPT = r"""
const data = $input.first().json;
const lead = data.lead;
const enr = data.enrichment || {};
data.llm_user_prompt = [
  'Qualify this B2B sales lead. Return JSON only.',
  'Name: ' + lead.name,
  'Company: ' + lead.company,
  'Company size: ' + (lead.company_size || 'unknown'),
  'Source: ' + lead.source,
  'Job title: ' + (enr.job_title || 'unknown'),
  'Message: ' + lead.message
].join('\n');
return [{ json: data }];
""".strip()

JS_AGENT_USABLE = r"""
const res = $input.first().json;
const output = res.output !== undefined ? res.output : (res.text !== undefined ? res.text : null);
const usable = output !== undefined && output !== null && String(output).trim() !== '' && !res.error;
return [{ json: { ...res, openai_usable: usable, llm_provider: 'openai' } }];
""".strip()

JS_TAG_GEMINI = r"""
const res = $input.first().json;
return [{ json: { ...res, llm_provider: 'gemini' } }];
""".strip()

JS_MARK_SKIPPED = r"""
const enrich = $('Optional Lead Enrichment').first().json;
return [{ json: { ...enrich, llm_skipped: true, llm_provider: 'skipped_unconfigured' } }];
""".strip()

JS_PARSE = r"""
function extractJson(text) {
  if (!text) return null;
  if (typeof text === 'object') return text;
  const trimmed = String(text).trim();
  try { return JSON.parse(trimmed); } catch (e) {}
  const start = trimmed.indexOf('{');
  const end = trimmed.lastIndexOf('}');
  if (start >= 0 && end > start) {
    try { return JSON.parse(trimmed.slice(start, end + 1)); } catch (e) {}
  }
  return null;
}
const input = $input.first().json;
const base = $('Optional Lead Enrichment').first().json;
let provider = input.llm_provider || 'skipped_unconfigured';
let qualification = null;
let parseError = null;
let valid = false;
if (input.llm_skipped || provider === 'skipped_unconfigured') {
  provider = 'skipped_unconfigured';
  parseError = null;
} else {
  let parsed = null;
  if (input.industry && input.intent && input.priority) parsed = input;
  else if (input.output && typeof input.output === 'object') parsed = input.output;
  else parsed = extractJson(input.output !== undefined ? input.output : input.text);
  const required = ['industry', 'intent', 'product_fit', 'priority', 'pain_points', 'summary', 'recommended_next_action'];
  if (!parsed || typeof parsed !== 'object') parseError = 'LLM did not return JSON';
  else {
    const missing = required.filter((k) => parsed[k] === undefined || parsed[k] === null || parsed[k] === '');
    if (missing.length) parseError = 'missing fields: ' + missing.join(',');
    else if (!['low', 'medium', 'high'].includes(parsed.intent)) parseError = 'invalid intent';
    else if (!['unknown', 'low', 'medium', 'high'].includes(parsed.product_fit)) parseError = 'invalid product_fit';
    else if (!['cold', 'warm', 'hot'].includes(parsed.priority)) parseError = 'invalid priority';
    else if (!Array.isArray(parsed.pain_points) || parsed.pain_points.length < 1) parseError = 'pain_points required';
    else { valid = true; qualification = parsed; }
  }
}
return [{ json: {
  ...base,
  ai_prequalify: { provider, valid, qualification, parse_error: parseError }
} }];
""".strip()

JS_INVALID_REVIEW = r"""
const data = $input.first().json;
return [{ json: {
  outcome: 'validation_failed',
  skipped: true,
  failed: false,
  routed: null,
  lead_id: null,
  errors: data.errors || ['invalid payload'],
  review_queue: 'invalid_payload',
  channels: { telegram_sales_alert: 'not_applicable', whatsapp: 'not_applicable', email: 'not_applicable' }
} }];
""".strip()

JS_CRM_FAIL = r"""
const res = $input.first().json;
return [{ json: {
  outcome: 'failed',
  skipped: false,
  failed: true,
  review_queue: 'crm_create_failed',
  errors: [res.message || res.error || res.detail || 'CRM create failed'],
  lead_id: null,
  channels: { telegram_sales_alert: 'not_applicable', whatsapp: 'not_applicable', email: 'not_applicable' }
} }];
""".strip()

JS_QUAL_FAIL = r"""
const created = $('Create Lead in CRM').first().json;
const qualify = $input.first().json;
const pre = $('Parse & Validate LLM JSON').first().json.ai_prequalify;
const detail = qualify.body && qualify.body.detail ? qualify.body.detail : (qualify.detail || 'qualification failed');
return [{ json: {
  outcome: 'qualification_failed',
  skipped: false,
  failed: true,
  review_queue: 'ai_qualification_failed',
  lead_id: created.id,
  external_id: created.external_id,
  status: created.status,
  qualification_error: created.qualification_error || String(detail),
  ai_prequalify: pre,
  errors: [String(detail)],
  channels: { telegram_sales_alert: 'not_applicable', whatsapp: 'not_applicable', email: 'not_applicable' }
} }];
""".strip()

JS_TELEGRAM_PLAN = r"""
const lead = $('Get CRM Lead').first().json;
const alerts = String($env.N8N_TELEGRAM_ALERTS || '').toLowerCase() === 'true';
const chat = $env.TELEGRAM_CHAT_ID;
const enabled = alerts && Boolean(chat);
const text = [
  'HOT lead (n8n sales alert)',
  'CRM id: ' + lead.id,
  'Name: ' + lead.name,
  'Company: ' + lead.company,
  'Priority: ' + lead.priority,
  'Summary: ' + (lead.ai_summary || ''),
  'Next: ' + (lead.recommended_next_action || ''),
  'Customer follow-up is waiting for human approval. Do not treat this as a sent message.'
].join('\n');
return [{ json: {
  telegram_action: enabled ? 'send' : 'skip',
  telegram_reason: enabled ? 'configured' : (alerts ? 'missing TELEGRAM_CHAT_ID' : 'N8N_TELEGRAM_ALERTS is not true'),
  telegram_chat_id: chat || '',
  telegram_text: text
} }];
""".strip()

JS_ASSEMBLE_HOT = r"""
function safe(name) { try { return $(name).first().json; } catch (e) { return {}; } }
const lead = $('Get CRM Lead').first().json;
const draft = safe('Draft Follow-up (HITL)');
const plan = safe('Plan Telegram Sales Alert');
const sent = safe('Send a text message');
const sheetsPlan = safe('Plan Sheets Export');
const upserted = safe('Append or update row in sheet');
let telegramStatus = 'skipped_unconfigured';
if (plan.telegram_action === 'send') {
  telegramStatus = (sent.ok === true || sent.result) ? 'sent' : 'failed';
} else {
  telegramStatus = 'skipped_unconfigured';
}
let sheetsStatus = 'skipped_unconfigured';
if (sheetsPlan.sheets_action === 'send') {
  sheetsStatus = upserted.error ? 'failed' : 'exported';
}
const pre = $('Parse & Validate LLM JSON').first().json.ai_prequalify;
return [{ json: {
  outcome: 'processed',
  skipped: false,
  failed: false,
  routed: 'hot',
  lead_id: lead.id,
  external_id: lead.external_id,
  priority: lead.priority,
  status: lead.status,
  follow_up_status: draft.follow_up_status || lead.follow_up_status,
  human_approval_required: true,
  ai_prequalify: pre,
  channels: {
    telegram_sales_alert: telegramStatus,
    whatsapp: 'awaiting_human_approval',
    email: 'awaiting_human_approval',
    google_sheets: sheetsStatus
  },
  errors: []
} }];
""".strip()

JS_ASSEMBLE_OTHER = r"""
function safe(name) { try { return $(name).first().json; } catch (e) { return {}; } }
const lead = $input.first().json;
const pre = $('Parse & Validate LLM JSON').first().json.ai_prequalify;
const sheetsPlan = safe('Plan Sheets Export');
const upserted = safe('Append or update row in sheet');
let sheetsStatus = 'skipped_unconfigured';
if (sheetsPlan.sheets_action === 'send') {
  sheetsStatus = upserted.error ? 'failed' : 'exported';
}
return [{ json: {
  outcome: 'processed',
  skipped: false,
  failed: false,
  routed: lead.priority || 'unknown',
  lead_id: lead.id,
  external_id: lead.external_id,
  priority: lead.priority,
  status: lead.status,
  follow_up_status: lead.follow_up_status,
  human_approval_required: false,
  ai_prequalify: pre,
  channels: {
    telegram_sales_alert: 'not_applicable',
    whatsapp: 'skipped_not_hot',
    email: 'skipped_not_hot',
    google_sheets: sheetsStatus
  },
  errors: []
} }];
""".strip()

JS_APPROVAL_BLOCKED = r"""
const lead = $input.first().json;
return [{ json: {
  outcome: 'approval_blocked',
  skipped: true,
  failed: false,
  lead_id: lead.id,
  follow_up_status: lead.follow_up_status,
  errors: ['Follow-up cannot be sent until a draft exists and a human approves it'],
  channels: { telegram_sales_alert: 'not_applicable', whatsapp: 'not_sent', email: 'not_sent' }
} }];
""".strip()

JS_PLAN_ADAPTERS = r"""
const approved = $input.first().json;
const lead = $('Load Lead For Approval').first().json;
const waPhone = $env.WHATSAPP_PHONE_NUMBER_ID;
const waTo = $env.WHATSAPP_TO;
const resend = $env.RESEND_API_KEY;
const emailFrom = $env.EMAIL_FROM;
const emailTo = lead.email;
const draft = lead.draft_message || '';
const waEnabled = Boolean(waPhone && waTo);
const emailEnabled = Boolean(resend && emailFrom && emailTo);
return [{ json: {
  approved,
  lead_id: lead.id,
  draft,
  whatsapp_action: waEnabled ? 'send' : 'skip',
  whatsapp_reason: waEnabled ? 'configured' : 'WhatsApp adapter unconfigured (n8n WhatsApp credential + WHATSAPP_PHONE_NUMBER_ID + WHATSAPP_TO)',
  whatsapp_phone_number_id: waPhone || '',
  whatsapp_to: waTo || '',
  email_action: emailEnabled ? 'send' : 'skip',
  email_reason: emailEnabled ? 'configured' : 'Email adapter unconfigured (RESEND_API_KEY, EMAIL_FROM)',
  email_request: emailEnabled ? {
    from: emailFrom,
    to: [emailTo],
    subject: 'Follow-up regarding ' + lead.company,
    text: draft
  } : null
} }];
""".strip()

JS_ASSEMBLE_APPROVE = r"""
function safe(name) { try { return $(name).first().json; } catch (e) { return {}; } }
const plan = $('Plan Optional Delivery Adapters').first().json;
const wa = safe('Send message');
const em = safe('Send Email via Resend (optional)');
let waStatus = plan.whatsapp_action === 'send' ? ((wa.messages || wa.ok || wa.id) ? 'sent' : 'failed') : 'skipped_unconfigured';
let emStatus = plan.email_action === 'send' ? ((em.id || em.ok) ? 'sent' : 'failed') : 'skipped_unconfigured';
if (plan.whatsapp_action === 'send' && wa.error) waStatus = 'failed';
if (plan.email_action === 'send' && em.error) emStatus = 'failed';
return [{ json: {
  outcome: 'approved',
  lead_id: plan.lead_id,
  crm_send_result: plan.approved.send_result || null,
  follow_up_status: plan.approved.follow_up_status,
  channels: {
    backend_mock_send: plan.approved.send_result || 'unknown',
    whatsapp: waStatus,
    email: emStatus,
    telegram_sales_alert: 'not_applicable',
    google_sheets: 'not_applicable'
  },
  notes: [
    'Customer-facing WhatsApp/email run only after explicit human approval.',
    'Unconfigured adapters are skipped, not marked successful.'
  ],
  errors: []
} }];
""".strip()

JS_QUAL_OK = r"""
const res = $input.first().json;
const body = res.body || res;
const code = res.statusCode || (res.error && res.error.httpCode) || 0;
const hasId = body && body.id !== undefined && body.id !== null;
const failedFlag = Boolean(body && body.qualification_error) || Boolean(res.error);
const ok = hasId && !failedFlag && (code === 0 || (code >= 200 && code < 300));
return [{ json: { ...(hasId ? body : { detail: body && body.detail }), _qualify_ok: ok, _qualify_status: code || (ok ? 200 : 503) } }];
""".strip()

JS_PLAN_SHEETS = r"""
const lead = $input.first().json;
const spreadsheetId = String($env.GOOGLE_SHEETS_SPREADSHEET_ID || '').trim();
const worksheet = String($env.GOOGLE_SHEETS_WORKSHEET || 'Qualified Leads').trim() || 'Qualified Leads';
const enabled = Boolean(spreadsheetId);
return [{ json: {
  ...lead,
  sheets_action: enabled ? 'send' : 'skip',
  sheets_reason: enabled ? 'configured' : 'GOOGLE_SHEETS_SPREADSHEET_ID is empty',
  sheets_spreadsheet_id: spreadsheetId,
  sheets_worksheet: worksheet
} }];
""".strip()

JS_RESUME_LEAD = r"""
const lead = $('Get CRM Lead').first().json;
return [{ json: { ...lead } }];
""".strip()


def node(i, name, ntype, version, x, y, parameters, extra=None):
    item = {
        "parameters": parameters,
        "id": f"00000000-0000-4000-8000-{i:012d}",
        "name": name,
        "type": ntype,
        "typeVersion": version,
        "position": [x, y],
    }
    if extra:
        item.update(extra)
    return item


def sticky(i, name, content, x, y, w, h, color):
    return node(
        i,
        name,
        "n8n-nodes-base.stickyNote",
        1,
        x,
        y,
        {"content": content, "width": w, "height": h, "color": color},
    )


def code(i, name, js, x, y):
    return node(i, name, "n8n-nodes-base.code", 2, x, y, {"jsCode": js})


def iff(i, name, left, right, x, y, op="equals"):
    operator = {"type": "string", "operation": op}
    if op == "equals":
        operator = {"type": "string", "operation": "equals"}
    elif op == "notEmpty":
        operator = {"type": "string", "operation": "notEmpty", "singleValue": True}
    elif op == "true":
        operator = {"type": "boolean", "operation": "true", "singleValue": True}
    cond = {
        "id": f"c-{i}",
        "leftValue": left,
        "operator": operator,
    }
    if op == "equals":
        cond["rightValue"] = right
    return node(
        i,
        name,
        "n8n-nodes-base.if",
        2.2,
        x,
        y,
        {
            "conditions": {
                "options": {
                    "caseSensitive": True,
                    "leftValue": "",
                    "typeValidation": "loose",
                    "version": 2,
                },
                "conditions": [cond],
                "combinator": "and",
            },
            "options": {},
        },
    )


def http(i, name, method, url, x, y, headers=None, json_body=None, extra_opts=None, retry=False):
    params = {
        "method": method,
        "url": url,
        "options": extra_opts or {},
    }
    if headers:
        params["sendHeaders"] = True
        params["headerParameters"] = {"parameters": [{"name": k, "value": v} for k, v in headers]}
    if json_body is not None:
        params["sendBody"] = True
        params["specifyBody"] = "json"
        params["jsonBody"] = json_body
    extra = {}
    if retry:
        extra = {
            "retryOnFail": True,
            "maxTries": 3,
            "waitBetweenTries": 1500,
            "onError": "continueRegularOutput",
        }
    return node(i, name, "n8n-nodes-base.httpRequest", 4.2, x, y, params, extra)


def respond(i, name, x, y):
    return node(
        i,
        name,
        "n8n-nodes-base.respondToWebhook",
        1.1,
        x,
        y,
        {"respondWith": "json", "responseBody": "={{ $json }}", "options": {}},
    )


def webhook(i, name, path, x, y, wid):
    return node(
        i,
        name,
        "n8n-nodes-base.webhook",
        2,
        x,
        y,
        {
            "httpMethod": "POST",
            "path": path,
            "responseMode": "responseNode",
            "options": {},
        },
        {"webhookId": wid},
    )


def agent(i, name, x, y):
    return node(
        i,
        name,
        "@n8n/n8n-nodes-langchain.agent",
        3.1,
        x,
        y,
        {
            "promptType": "define",
            "text": "={{ $('Build Qualification Prompt').item.json.llm_user_prompt }}",
            "options": {"systemMessage": AGENT_SYSTEM},
        },
        {
            "retryOnFail": True,
            "maxTries": 2,
            "waitBetweenTries": 1500,
            "onError": "continueRegularOutput",
        },
    )


def openai_chat_model(i, name, x, y):
    return node(
        i,
        name,
        "@n8n/n8n-nodes-langchain.lmChatOpenAi",
        1.2,
        x,
        y,
        {
            "model": {
                "__rl": True,
                "value": "gpt-4o-mini",
                "mode": "list",
                "cachedResultName": "gpt-4o-mini",
            },
            "options": {"temperature": 0},
        },
        {"credentials": OPENAI_CRED},
    )


def gemini_chat_model(i, name, x, y):
    return node(
        i,
        name,
        "@n8n/n8n-nodes-langchain.lmChatGoogleGemini",
        1,
        x,
        y,
        {
            "modelName": "models/gemini-2.0-flash",
            "options": {"temperature": 0},
        },
        {"credentials": GEMINI_CRED},
    )


def telegram_send(i, name, x, y):
    return node(
        i,
        name,
        "n8n-nodes-base.telegram",
        1.2,
        x,
        y,
        {
            "chatId": "={{ $json.telegram_chat_id }}",
            "text": "={{ $json.telegram_text }}",
            "additionalFields": {"appendAttribution": False},
        },
        {
            "webhookId": "9cabb5ed-5a9f-414c-bda8-54e977e5c6b8",
            "credentials": TELEGRAM_CRED,
            "retryOnFail": True,
            "maxTries": 3,
            "waitBetweenTries": 1500,
            "onError": "continueRegularOutput",
        },
    )


def whatsapp_send(i, name, x, y):
    return node(
        i,
        name,
        "n8n-nodes-base.whatsApp",
        1.1,
        x,
        y,
        {
            "operation": "send",
            "phoneNumberId": "={{ $json.whatsapp_phone_number_id }}",
            "recipientPhoneNumber": "={{ $json.whatsapp_to }}",
            "textBody": "={{ $json.draft }}",
            "additionalFields": {},
        },
        {
            "webhookId": "a001fd79-a969-489c-8660-c88e2b81c466",
            "credentials": WHATSAPP_CRED,
            "retryOnFail": True,
            "maxTries": 3,
            "waitBetweenTries": 1500,
            "onError": "continueRegularOutput",
        },
    )


def _sheet_document_id():
    return {
        "__rl": True,
        "mode": "id",
        "value": "={{ $('Plan Sheets Export').item.json.sheets_spreadsheet_id }}",
    }


def _sheet_columns():
    value = {
        field: f"={{{{ $('Plan Sheets Export').item.json.{field} }}}}"
        for field in SHEET_FIELDS
    }
    schema = [
        {
            "id": field,
            "displayName": field,
            "required": False,
            "defaultMatch": field == "id",
            "display": True,
            "type": "string",
            "canBeUsedToMatch": True,
        }
        for field in SHEET_FIELDS
    ]
    return {
        "mappingMode": "defineBelow",
        "value": value,
        "matchingColumns": ["id"],
        "schema": schema,
        "attemptToConvertTypes": False,
        "convertFieldsToString": False,
    }


def sheets_create(i, name, x, y):
    """Official Google Sheets node — create a tab inside the spreadsheet.

    continueOnFail: the tab often already exists after the first lead.
    """
    return node(
        i,
        name,
        "n8n-nodes-base.googleSheets",
        4.7,
        x,
        y,
        {
            "resource": "sheet",
            "operation": "create",
            "documentId": _sheet_document_id(),
            "title": "={{ $('Plan Sheets Export').item.json.sheets_worksheet }}",
            "options": {},
        },
        {
            "credentials": SHEETS_CRED,
            "onError": "continueRegularOutput",
        },
    )


def sheets_append_or_update(i, name, x, y):
    """Official Google Sheets node — upsert the qualified lead row by CRM id."""
    return node(
        i,
        name,
        "n8n-nodes-base.googleSheets",
        4.7,
        x,
        y,
        {
            "resource": "sheet",
            "operation": "appendOrUpdate",
            "documentId": _sheet_document_id(),
            "sheetName": {
                "__rl": True,
                "mode": "name",
                "value": "={{ $('Plan Sheets Export').item.json.sheets_worksheet }}",
            },
            "columns": _sheet_columns(),
            "options": {},
        },
        {
            "credentials": SHEETS_CRED,
            "retryOnFail": True,
            "maxTries": 2,
            "waitBetweenTries": 1500,
            "onError": "continueRegularOutput",
        },
    )


def add_edge(connections, src, dst, idx=0, conn_type="main"):
    bucket = connections.setdefault(src, {})
    outputs = bucket.setdefault(conn_type, [])
    while len(outputs) <= idx:
        outputs.append([])
    outputs[idx].append({"node": dst, "type": conn_type, "index": 0})


def build():
    nodes = [
        sticky(1, "Group: Intake", "## 1. Intake & validation\nReject bad payloads before CRM or LLM calls.", -120, 180, 420, 200, 5),
        sticky(2, "Group: Enrichment", "## 2. Optional enrichment\nLocal domain/seniority only. No fake Clearbit success.", 420, 40, 380, 160, 6),
        sticky(3, "Group: AI qualification", "## 3. AI qualification\nOfficial AI Agent + OpenAI Chat Model, Gemini Chat Model fallback.\nSkipped honestly when keys/credentials are missing.", 860, 0, 820, 180, 6),
        sticky(4, "Group: CRM", "## 4. CRM orchestration\nBackend is source of truth for persist, qualify, priority.\nHTTP Request stays here (no official FastAPI node).", 1760, 40, 560, 180, 4),
        sticky(8, "Group: Sheets", "## 4b. Google Sheets export\nOfficial **Create sheet** then **Append or update row** by CRM `id`.\nEmpty `GOOGLE_SHEETS_SPREADSHEET_ID` skips; tab-exists errors continue.", 3360, 0, 1280, 180, 4),
        sticky(5, "Group: Routing HITL", "## 5. Routing & HITL\nHot: draft only. Official Telegram node for sales alert.\nCustomer WhatsApp waits for `/webhook/lead-approve`.", 4700, 0, 620, 180, 3),
        sticky(6, "Group: Error review", "## Error / review\nInvalid payload, CRM errors, and failed `/qualify` stay on this row.", 240, 620, 640, 140, 1),
        sticky(7, "Group: Approve webhook", "## Human approval webhook\nPOST /webhook/lead-approve `{lead_id}` after a draft exists.\nOfficial WhatsApp node; Resend stays HTTP (no first-party node).", 0, 980, 780, 180, 2),
        webhook(10, "Lead Intake Webhook", "lead-intake", 0, 320, "lead-intake"),
        code(11, "Validate Incoming Lead", JS_VALIDATE, 240, 320),
        iff(12, "Payload Valid?", "={{ $json.valid }}", None, 480, 320, op="true"),
        code(13, "Invalid Payload Review", JS_INVALID_REVIEW, 720, 720),
        respond(14, "Respond — Validation Failed", 980, 720),
        code(15, "Optional Lead Enrichment", JS_ENRICH, 720, 320),
        code(16, "Build Qualification Prompt", JS_BUILD_PROMPT, 960, 320),
        iff(17, "OpenAI Key Present?", "={{ $env.OPENAI_API_KEY }}", None, 1180, 320, op="notEmpty"),
        agent(18, "AI Agent", 1420, 160),
        openai_chat_model(19, "OpenAI Chat Model", 1420, 340),
        code(20, "Inspect OpenAI Response", JS_AGENT_USABLE, 1680, 160),
        iff(21, "OpenAI Response Usable?", "={{ $json.openai_usable }}", None, 1920, 160, op="true"),
        iff(22, "Gemini Key Present?", "={{ $env.GEMINI_API_KEY }}", None, 1180, 500, op="notEmpty"),
        agent(23, "AI Agent — Gemini Fallback", 1420, 500),
        gemini_chat_model(24, "Google Gemini Chat Model", 1420, 680),
        code(25, "Inspect Gemini Response", JS_TAG_GEMINI, 1680, 500),
        code(26, "Mark LLM Skipped", JS_MARK_SKIPPED, 1420, 780),
        code(27, "Parse & Validate LLM JSON", JS_PARSE, 2160, 320),
        http(
            28,
            "Create Lead in CRM",
            "POST",
            "={{ ($env.BACKEND_BASE_URL || 'http://backend:8000') + '/api/webhooks/leads' }}",
            2400,
            320,
            headers=[
                ("X-Webhook-Secret", "={{ $env.WEBHOOK_SECRET }}"),
                ("Content-Type", "application/json"),
            ],
            json_body="={{ $json.lead }}",
            extra_opts={"timeout": 15000},
            retry=True,
        ),
        iff(29, "CRM Create OK?", "={{ Boolean($json.id) }}", None, 2620, 320, op="true"),
        code(30, "CRM Create Failed Review", JS_CRM_FAIL, 2840, 720),
        respond(31, "Respond — CRM Error", 3080, 720),
        http(
            32,
            "Backend Qualify Lead",
            "POST",
            "={{ ($env.BACKEND_BASE_URL || 'http://backend:8000') + '/api/leads/' + $json.id + '/qualify' }}",
            2840,
            320,
            extra_opts={
                "timeout": 45000,
                "response": {"response": {"fullResponse": True, "neverError": True}},
            },
            retry=True,
        ),
        code(33, "Normalize Qualify Response", JS_QUAL_OK, 3060, 320),
        iff(34, "Qualify Succeeded?", "={{ $json._qualify_ok }}", None, 3280, 320, op="true"),
        code(35, "Qualification Failed Review", JS_QUAL_FAIL, 3500, 720),
        respond(36, "Respond — Qualification Review", 3740, 720),
        http(
            37,
            "Get CRM Lead",
            "GET",
            "={{ ($env.BACKEND_BASE_URL || 'http://backend:8000') + '/api/leads/' + $json.id }}",
            3500,
            320,
        ),
        code(63, "Plan Sheets Export", JS_PLAN_SHEETS, 3720, 320),
        iff(64, "Sheets Configured?", "={{ $json.sheets_action }}", "send", 3940, 320),
        sheets_create(65, "Create sheet", 4160, 160),
        sheets_append_or_update(66, "Append or update row in sheet", 4380, 160),
        code(67, "Resume CRM Lead", JS_RESUME_LEAD, 4600, 320),
        iff(38, "Priority Is Hot?", "={{ $json.priority }}", "hot", 4820, 320),
        http(
            39,
            "Draft Follow-up (HITL)",
            "POST",
            "={{ ($env.BACKEND_BASE_URL || 'http://backend:8000') + '/api/leads/' + $json.id + '/followup/draft' }}",
            5040,
            160,
            extra_opts={"timeout": 45000},
            retry=True,
        ),
        code(40, "Plan Telegram Sales Alert", JS_TELEGRAM_PLAN, 5260, 160),
        iff(41, "Send Telegram Alert?", "={{ $json.telegram_action }}", "send", 5480, 160),
        telegram_send(42, "Send a text message", 5700, 80),
        code(43, "Assemble Hot Result", JS_ASSEMBLE_HOT, 5940, 160),
        respond(44, "Respond — Hot Processed", 6180, 160),
        code(45, "Assemble Non-Hot Result", JS_ASSEMBLE_OTHER, 5040, 480),
        respond(46, "Respond — Routed", 5280, 480),
        webhook(50, "Human Approve Webhook", "lead-approve", 0, 1200, "lead-approve"),
        http(
            51,
            "Load Lead For Approval",
            "GET",
            "={{ ($env.BACKEND_BASE_URL || 'http://backend:8000') + '/api/leads/' + ($json.body.lead_id || $json.lead_id) }}",
            240,
            1200,
        ),
        iff(52, "Draft Ready For Send?", "={{ $json.follow_up_status }}", "awaiting_approval", 480, 1200),
        code(53, "Respond Body — Approval Blocked", JS_APPROVAL_BLOCKED, 720, 1400),
        respond(54, "Respond — Approval Blocked", 960, 1400),
        http(
            55,
            "Approve Follow-up in CRM",
            "POST",
            "={{ ($env.BACKEND_BASE_URL || 'http://backend:8000') + '/api/leads/' + $json.id + '/approve-followup' }}",
            720,
            1200,
        ),
        code(56, "Plan Optional Delivery Adapters", JS_PLAN_ADAPTERS, 960, 1200),
        iff(57, "WhatsApp Adapter Enabled?", "={{ $json.whatsapp_action }}", "send", 1200, 1100),
        whatsapp_send(58, "Send message", 1440, 1000),
        iff(59, "Email Adapter Enabled?", "={{ $('Plan Optional Delivery Adapters').item.json.email_action }}", "send", 1200, 1320),
        http(
            60,
            "Send Email via Resend (optional)",
            "POST",
            "https://api.resend.com/emails",
            1440,
            1440,
            headers=[
                ("Authorization", "Bearer {{$env.RESEND_API_KEY}}"),
                ("Content-Type", "application/json"),
            ],
            json_body="={{ $('Plan Optional Delivery Adapters').item.json.email_request }}",
            extra_opts={"timeout": 15000},
            retry=True,
        ),
        code(61, "Assemble Approval Result", JS_ASSEMBLE_APPROVE, 1680, 1200),
        respond(62, "Respond — Approval Complete", 1920, 1200),
    ]

    connections = {}
    edges = [
        ("Lead Intake Webhook", "Validate Incoming Lead"),
        ("Validate Incoming Lead", "Payload Valid?"),
        ("Payload Valid?", "Optional Lead Enrichment", 0),
        ("Payload Valid?", "Invalid Payload Review", 1),
        ("Invalid Payload Review", "Respond — Validation Failed"),
        ("Optional Lead Enrichment", "Build Qualification Prompt"),
        ("Build Qualification Prompt", "OpenAI Key Present?"),
        ("OpenAI Key Present?", "AI Agent", 0),
        ("OpenAI Key Present?", "Gemini Key Present?", 1),
        ("AI Agent", "Inspect OpenAI Response"),
        ("Inspect OpenAI Response", "OpenAI Response Usable?"),
        ("OpenAI Response Usable?", "Parse & Validate LLM JSON", 0),
        ("OpenAI Response Usable?", "Gemini Key Present?", 1),
        ("Gemini Key Present?", "AI Agent — Gemini Fallback", 0),
        ("Gemini Key Present?", "Mark LLM Skipped", 1),
        ("AI Agent — Gemini Fallback", "Inspect Gemini Response"),
        ("Inspect Gemini Response", "Parse & Validate LLM JSON"),
        ("Mark LLM Skipped", "Parse & Validate LLM JSON"),
        ("Parse & Validate LLM JSON", "Create Lead in CRM"),
        ("Create Lead in CRM", "CRM Create OK?"),
        ("CRM Create OK?", "Backend Qualify Lead", 0),
        ("CRM Create OK?", "CRM Create Failed Review", 1),
        ("CRM Create Failed Review", "Respond — CRM Error"),
        ("Backend Qualify Lead", "Normalize Qualify Response"),
        ("Normalize Qualify Response", "Qualify Succeeded?"),
        ("Qualify Succeeded?", "Get CRM Lead", 0),
        ("Qualify Succeeded?", "Qualification Failed Review", 1),
        ("Qualification Failed Review", "Respond — Qualification Review"),
        ("Get CRM Lead", "Plan Sheets Export"),
        ("Plan Sheets Export", "Sheets Configured?"),
        ("Sheets Configured?", "Create sheet", 0),
        ("Sheets Configured?", "Resume CRM Lead", 1),
        ("Create sheet", "Append or update row in sheet"),
        ("Append or update row in sheet", "Resume CRM Lead"),
        ("Resume CRM Lead", "Priority Is Hot?"),
        ("Priority Is Hot?", "Draft Follow-up (HITL)", 0),
        ("Priority Is Hot?", "Assemble Non-Hot Result", 1),
        ("Draft Follow-up (HITL)", "Plan Telegram Sales Alert"),
        ("Plan Telegram Sales Alert", "Send Telegram Alert?"),
        ("Send Telegram Alert?", "Send a text message", 0),
        ("Send Telegram Alert?", "Assemble Hot Result", 1),
        ("Send a text message", "Assemble Hot Result"),
        ("Assemble Hot Result", "Respond — Hot Processed"),
        ("Assemble Non-Hot Result", "Respond — Routed"),
        ("Human Approve Webhook", "Load Lead For Approval"),
        ("Load Lead For Approval", "Draft Ready For Send?"),
        ("Draft Ready For Send?", "Approve Follow-up in CRM", 0),
        ("Draft Ready For Send?", "Respond Body — Approval Blocked", 1),
        ("Respond Body — Approval Blocked", "Respond — Approval Blocked"),
        ("Approve Follow-up in CRM", "Plan Optional Delivery Adapters"),
        ("Plan Optional Delivery Adapters", "WhatsApp Adapter Enabled?"),
        ("WhatsApp Adapter Enabled?", "Send message", 0),
        ("WhatsApp Adapter Enabled?", "Email Adapter Enabled?", 1),
        ("Send message", "Email Adapter Enabled?"),
        ("Email Adapter Enabled?", "Send Email via Resend (optional)", 0),
        ("Email Adapter Enabled?", "Assemble Approval Result", 1),
        ("Send Email via Resend (optional)", "Assemble Approval Result"),
        ("Assemble Approval Result", "Respond — Approval Complete"),
    ]
    for edge in edges:
        src, dst = edge[0], edge[1]
        idx = edge[2] if len(edge) > 2 else 0
        add_edge(connections, src, dst, idx)

    add_edge(connections, "OpenAI Chat Model", "AI Agent", conn_type="ai_languageModel")
    add_edge(
        connections,
        "Google Gemini Chat Model",
        "AI Agent — Gemini Fallback",
        conn_type="ai_languageModel",
    )

    workflow = {
        "name": "Lead Qualification",
        "nodes": nodes,
        "connections": connections,
        "pinData": {},
        "active": False,
        "isArchived": False,
        "id": "a1a1a1a1-b2b2-4c3c-8d4d-e5e5e5e5e5e5",
        "versionId": "a2a2a2a2-b2b2-4c3c-8d4d-e5e5e5e5e5e5",
        "settings": {"executionOrder": "v1"},
        "staticData": None,
        "tags": [],
        "meta": {"templateCredsSetupCompleted": True},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(workflow, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} with {len(nodes)} nodes")


if __name__ == "__main__":
    build()
