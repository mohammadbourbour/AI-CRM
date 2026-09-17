# راهنمای کار سیستم (نسخه جدید)

این سند توضیح می‌دهد **الان** پلتفرم چطور کار می‌کند: n8n + FastAPI + CRM + AI + human-in-the-loop.

این یک **پروژه پورتفولیو** است، نه CRM پروداکشن.

---

## ۱. اجزای سیستم

| جزء | نقش |
|-----|-----|
| **n8n** | orchestration: validation، enrichment، LLM (Groq)، فراخوانی API، routing، کانال‌های اختیاری |
| **FastAPI** | CRM، قوانین priority، qualify، draft، approve، mock send |
| **SQLite** | ذخیره لیدها |
| **Mock LLM** | وقتی `GROQ_API_KEY` خالی است (heuristic — نه مدل واقعی) |

---

## ۲. آدرس‌های مهم (روی ماشین شما)

| سرویس | آدرس |
|--------|------|
| Backend API / داشبورد | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |
| Health | http://localhost:8000/health |
| n8n UI | http://localhost:5679 (اگر 5678 اشغال بود) |

---

## ۳. بالا آوردن از صفر

```powershell
cd path\to\this-repo
copy .env.example .env
$env:N8N_PORT_HOST='5679'
docker compose down
docker compose up --build -d
```

صبر کنید تا health سبز شود:

```powershell
curl.exe -s http://localhost:8000/health
```

انتظار: `"groq":"mock"` و `"telegram":"disabled"` و `"google_sheets":"disabled"` (بدون credential طبیعی است).

### فعال‌سازی workflow در n8n (یک بار)

1. برو به http://localhost:5679  
2. **Workflows → Import from File** → `n8n/workflows/lead-qualification.json`  
3. workflow **Lead Qualification** را باز کن  
4. سوئیچ **Active** (بالا سمت راست) را روشن کن  

> import از CLI ممکن است workflow را بیاورد ولی در n8n 2.x برای webhook باید از UI یک بار **Publish/Active** بزنی.

---

## ۴. مسیر A — ورود لید از n8n (مسیر اصلی دمو)

```
لید → webhook n8n
    → Validate (ایمیل/نام/پیام)
    → Enrichment (دامنه ایمیل، seniority — محلی)
    → AI Agent + Groq Chat Model (اگر key و credential باشد) → وگرنه skip
    → Parse JSON (اعتبارسنجی ساختار)
    → POST /api/webhooks/leads (با X-Webhook-Secret)
    → POST /api/leads/{id}/qualify  ← منبع حقیقت priority
    → GET /api/leads/{id}
    → Google Sheets: Create sheet + upsert by id (اگر spreadsheet id و credential باشد)
    → اگر hot: draft follow-up + (اختیاری) Telegram sales alert
    → پاسخ JSON با outcome و وضعیت کانال‌ها
```

### تست یک لید hot

```powershell
curl.exe -s -X POST http://localhost:5679/webhook/lead-intake `
  -H "Content-Type: application/json" `
  --data-binary "@examples/lead_hot.json"
```

در پاسخ ببین:

- `"outcome": "processed"`
- `"priority": "hot"`
- `"follow_up_status": "awaiting_approval"`
- `"human_approval_required": true`
- `"channels.telegram_sales_alert": "skipped_unconfigured"` (پیش‌فرض)

### approve انسانی (قبل از هر پیام به مشتری)

```powershell
curl.exe -s -X POST http://localhost:5679/webhook/lead-approve `
  -H "Content-Type: application/json" `
  -d "{\"lead_id\": 1}"
```

- CRM → `follow_up_status: sent` و `send_result: mock_sent`
- WhatsApp/Email فقط اگر در `.env` تنظیم شده باشند؛ وگرنه `skipped_unconfigured`

---

## ۵. مسیر B — مستقیم API (بدون n8n)

برای debug یا وقتی n8n هنوز Active نشده:

```powershell
# 1) ثبت لید
curl.exe -s -X POST http://localhost:8000/api/webhooks/leads `
  -H "Content-Type: application/json" `
  -H "X-Webhook-Secret: dev-webhook-secret-change-me" `
  --data-binary "@examples/lead_hot.json"

# 2) qualify
curl.exe -s -X POST http://localhost:8000/api/leads/1/qualify

# 3) draft
curl.exe -s -X POST http://localhost:8000/api/leads/1/followup/draft

# 4) approve  (یا reject: /api/leads/1/reject-followup)
curl.exe -s -X POST http://localhost:8000/api/leads/1/approve-followup
```

---

## ۶. دیتاست ۱۰۰+ لید ساختگی

```powershell
python scripts/generate_dataset.py
python scripts/run_batch_demo.py --n8n-url http://localhost:5679/webhook/lead-intake
```

- **110** لید معتبر در `examples/dataset/leads.json` و `leads.csv`
- **128** آیتم batch (duplicate + malformed برای تست خطا)
- **بدون** برچسب priority از قبل — classification در runtime ساخته می‌شود

خلاصه اجرا: `examples/dataset/last_run_summary.json`

---

## ۷. AI در n8n vs بک‌اند

| لایه | چه می‌کند |
|------|-----------|
| n8n AI Agent (Groq) | pre-qualify برای audit در پاسخ workflow (`ai_prequalify`) |
| Backend `/qualify` | **منبع حقیقت** برای priority ذخیره‌شده در CRM |

اگر هیچ key نباشد:

- n8n: `llm_provider: skipped_unconfigured`
- backend: MockLLM (keyword) — صادقانه در log نوشته می‌شود

---

## ۸. کانال‌های اعلان (صادقانه)

| کانال | کی | پیش‌فرض |
|--------|-----|---------|
| Telegram backend | داخل `/qualify` برای hot | خاموش (بدون token) |
| Telegram n8n | بعد از draft hot | خاموش (`N8N_TELEGRAM_ALERTS=false`) |
| WhatsApp | بعد از approve | خاموش |
| Email (Resend) | بعد از approve | خاموش |

هیچ کانالی بدون credential **sent** جعلی برنمی‌گرداند.

---

## ۹. خطاها و review

| وضعیت | معنی |
|--------|------|
| `validation_failed` | payload بد — CRM write نشده |
| `qualification_failed` | `/qualify` خطا — لید retryپذیر |
| `approval_blocked` | approve بدون draft |
| `skipped_unconfigured` | adapter تنظیم نشده |

---

## ۱۰. تست خودکار

```powershell
cd backend
python -m pytest -v
```

باید **45 passed** ببینی.

---

## ۱۱. متغیرهای محیطی مهم (`.env`)

```env
WEBHOOK_SECRET=dev-webhook-secret-change-me
GROQ_API_KEY=            # خالی = mock
N8N_TELEGRAM_ALERTS=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
WHATSAPP_TOKEN=
RESEND_API_KEY=
```

---

## ۱۲. جریان ذهنی برای recruiter

1. لید می‌آید → validate  
2. AI (یا mock) qualify می‌کند  
3. CRM ذخیره + priority deterministic  
4. hot → draft + (اختیاری) alert تیم فروش  
5. انسان approve می‌کند  
6. فقط بعد approve → mock send + (اختیاری) WhatsApp/email  

**هیچ پیام AI بدون approve به مشتری نمی‌رود.**
