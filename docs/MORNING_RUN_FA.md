# چک‌لیست صبح — اجرای زنده n8n + داشبورد

این همان مسیری است که برای مصاحبه رز باید دست‌تان باشد. گوگل‌شیت و تلگرام را **با حساب خودتان** وصل می‌کنید؛ از این محیط ابری نمی‌شود وارد جیمیل شما شد.

مخزن: https://github.com/mohammadbourbour/AI-CRM  
PR: https://github.com/mohammadbourbour/AI-CRM/pull/1

## Merge روی لوکال (برای تست)

در ریشه کلون:

```powershell
git fetch origin
git checkout main
git pull origin main
git merge origin/cursor/demo-dashboard-telegram-7431
```

اگر GitHub را Merge کردید، فقط `git checkout main` و `git pull origin main` کافی است. بعد از merge، از بخش ۰ ادامه دهید.

---

## ۰. یک‌بار قبل از شروع (اگر قبلاً نزده‌اید)

PowerShell در ریشه پروژه:

```powershell
copy .env.example .env
docker compose up --build
```

صبر کنید تا این دو سبز شوند:

| سرویس | آدرس |
|--------|------|
| داشبورد | http://localhost:8000 |
| n8n | http://localhost:5678 |

اگر پورت ۵۶۷۸ اشغال بود، در `.env` بگذارید: `N8N_PORT_HOST=5679`

---

## ۱. n8n را روشن و Publish کنید (اجباری)

1. مرورگر: http://localhost:5678
2. **اولین بار:** ایمیل و رمز owner بسازید (محلی است، مال گوگل نیست).
3. اگر کانواس خالی است: **Workflows → Import from File** → فایل  
   `n8n/workflows/lead-qualification.json`
4. روی گردش **Lead Qualification** دکمه **Publish** را بزنید (در n8n 2.x تا Publish نشود، webhook کار نمی‌کند).
5. از منوی چپ **Executions** را باز بگذارید (اسپلیت‌اسکرین کنار داشبورد).

اختیاری، اگر API لاگین جواب داد:

```powershell
python scripts/bootstrap_n8n.py
```

این اسکریپت Publish نمی‌کند؛ Publish را خودتان می‌زنید.

---

## ۲. سایت → انتخاب سناریو → ارسال به n8n

1. http://localhost:8000
2. مسیر اجرا: **ارسال به n8n (برای مصاحبه)** باید انتخاب باشد.
3. یکی را بزنید:

| دکمه | باید در n8n ببینید | باید در داشبورد ببینید |
|------|---------------------|-------------------------|
| رد اعتبارسنجی | Validate fail، CRM نوشته نمی‌شود | REJECTED |
| Cold | Qualify → Sheets (اگر وصل) → بدون draft | COLD، follow-up = not_started |
| Warm | همین، اولویت warm | WARM |
| Hot | Draft HITL | پیش‌نویس + قبول/رد |

4. بلافاصله به تب n8n → Executions بروید. اجرای سبز یعنی گردش تمام شد. روی همان execution کلیک کنید تا هر گره را ببینید.

اگر داشبورد خطای `webhook is not registered` داد: Publish را نزده‌اید.

اگر `n8n is not running` داد: `docker compose up` را دوباره بزنید.

---

## ۳. نتیجه را کجا ببینید

| جا | چه چیزی |
|----|---------|
| **داشبورد** | امتیاز، خلاصه، پیش‌نویس، تخته CRM، متن پیام تلگرام، ردیف شیت |
| **n8n Executions** | گره به گره |
| **تلگرام** | فقط اگر توکن و chat id در `.env` باشد |
| **Google Sheets** | فقط اگر شناسه شیت + credential گوگل در n8n باشد |

تا وقتی تلگرام/شیت وصل نشده، داشبورد همان متن و همان ردیف را نشان می‌دهد و وضعیت را `skipped_unconfigured` می‌نویسد — موفقیت جعلی نیست.

---

## ۴. تلگرام (۵ دقیقه، با گوشی خودتان)

1. در تلگرام به [@BotFather](https://t.me/BotFather) بروید → `/newbot` → توکن را کپی کنید.
2. یک کانال بسازید، ربات را **Admin** کنید.
3. در `.env`:

```
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=@your_channel
```

اگر کانال خصوصی است، `TELEGRAM_CHAT_ID` معمولاً `-100…` است.

4. `N8N_TELEGRAM_ALERTS` را `false` بگذارید تا پیام دو بار نرود. بک‌اند بعد از `/qualify` نتیجه را به کانال می‌فرستد (نه متن مشتری).
5. `docker compose up -d --force-recreate`

یک سناریوی Cold/Warm/Hot بفرستید؛ پیام باید در کانال و در داشبورد بیاید.

---

## ۵. Google Sheets (۱۰ دقیقه، با جیمیل خودتان)

از اینجا **نمی‌شود** وارد حساب گوگل شما شد. صبح خودتان:

1. https://sheets.google.com → Blank spreadsheet → اسم: `Qualified Leads`
2. از URL کپی کنید:  
   `https://docs.google.com/spreadsheets/d/` **`این_شناسه`** `/edit`
3. در `.env`:

```
GOOGLE_SHEETS_SPREADSHEET_ID=این_شناسه
GOOGLE_SHEETS_WORKSHEET=Qualified Leads
```

4. `docker compose up -d --force-recreate`
5. n8n → **Credentials** → Add → **Google Sheets OAuth2 API** → Sign in with Google (همان جیمیل).
6. گردش Lead Qualification را باز کنید:
   - گره **Create sheet** → credential گوگل
   - گره **Append or update row in sheet** → همان credential
7. دوباره **Publish**
8. از داشبورد یک Warm یا Hot بفرستید. در شیت باید یک ردیف با `id` همان لید CRM بیاید.

اگر شیت خالی ماند ولی داشبورد `sheets_status=skipped_unconfigured` نوشت: شناسه شیت در `.env` نرفته یا n8n را recreate نکرده‌اید.  
اگر execution روی گره Sheets قرمز شد: credential به گره وصل نشده یا شیت با آن جیمیل share نشده.

---

## ۶. قبول / رد پیش‌نویس داغ

بعد از Hot، در داشبورد:

- **رد پیش‌نویس** → `skipped`، پیام مشتری نمی‌رود
- **قبول پیش‌نویس** → `mock_sent`، وضعیت `contacted`

این مرحله روی CRM است. برای دیدن intake، همان execution مربوط به webhook کافی است.

---

## اگر چیزی کار نکرد

```powershell
curl.exe -s http://localhost:8000/health
curl.exe -s http://localhost:5678/healthz
python scripts/morning_check.py
```

Workflow باید Published باشد. داشبورد باید مسیر **ارسال به n8n** را داشته باشد.
