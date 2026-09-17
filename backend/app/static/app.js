const pipelineEl = document.getElementById("pipeline");
const timelineEl = document.getElementById("timeline");
const resultEl = document.getElementById("result");
const boardEl = document.getElementById("board");
const healthEl = document.getElementById("health");

let metaStages = [];
let currentLeadId = null;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (response.status === 204) return null;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(body.detail) ? JSON.stringify(body.detail) : body.detail;
    throw new Error(detail || response.statusText);
  }
  return body;
}

function renderHealth(health, meta) {
  const n8nOn = Boolean(meta && meta.n8n_webhook_configured);
  const sheetsOn = Boolean(meta && meta.n8n_sheets_configured) || health.google_sheets === "enabled";
  const chips = [
    ["n8n", n8nOn ? "on" : "off", n8nOn ? "webhook" : "no URL"],
    ["OpenAI", health.openai === "enabled" ? "on" : "off", health.openai],
    ["Telegram", health.telegram === "enabled" ? "on" : "off", health.telegram],
    ["Sheets", sheetsOn ? "on" : "off", sheetsOn ? "id set" : "off"],
  ];
  healthEl.innerHTML = chips
    .map(([label, klass, value]) => `<li class="${klass}">${label}: ${value}</li>`)
    .join("");
}

function renderPipeline(stages) {
  pipelineEl.innerHTML = stages
    .map(
      (stage) => `
      <li class="stage ${stage.status}" data-id="${stage.id}">
        <small>${stage.n8n_node}</small>
        <strong>${stage.label_fa}</strong>
        <div class="state">${stage.label_en} · ${stage.status}</div>
      </li>`
    )
    .join("");
}

function appendTimeline(stage) {
  const item = document.createElement("li");
  item.innerHTML = `<div class="when">${stage.label_en} · ${stage.status}</div>
    <div><b>${stage.label_fa}</b></div>
    <div>${stage.detail || stage.n8n_node}</div>`;
  timelineEl.prepend(item);
}

function hitlButtons(lead) {
  if (!lead || lead.follow_up_status !== "awaiting_approval") return "";
  return `<div class="hitl">
      <button type="button" class="accept" data-decision="accept">قبول پیش‌نویس</button>
      <button type="button" class="reject" data-decision="reject">رد پیش‌نویس</button>
    </div>`;
}

function selectedVia() {
  const picked = document.querySelector("input[name=via]:checked");
  return picked ? picked.value : "n8n";
}

function renderChannels(run) {
  const sheets = run.sheets_status || "—";
  const exec = run.n8n_executions_url
    ? `<p class="telegram"><a href="${run.n8n_executions_url}" target="_blank" rel="noreferrer">باز کردن Executions در n8n</a> · via=<b>${run.via || "crm"}</b> · Sheets: <b>${sheets}</b></p>`
    : `<p class="telegram">via=<b>${run.via || "crm"}</b> · Sheets: <b>${sheets}</b></p>`;
  const preview = run.telegram_preview
    ? `<pre class="draft telegram-preview">${run.telegram_preview.replace(/<[^>]+>/g, "")}</pre>`
    : "";
  const row = run.sheets_row
    ? `<pre class="draft">${JSON.stringify(run.sheets_row, null, 2)}</pre>`
    : "";
  return `${exec}
    <div class="telegram">پیام کانال تلگرام (نتیجه تیم، نه پیام مشتری): <b>${run.telegram_status}</b></div>
    ${preview}
    ${row ? `<div class="telegram">ردیف Google Sheets</div>${row}` : ""}`;
}

function renderResult(run) {
  const lead = run.lead;
  currentLeadId = lead ? lead.id : null;
  if (!lead) {
    resultEl.className = "result";
    const failed = (run.stages || []).find((stage) => stage.status === "failed");
    resultEl.innerHTML = `<span class="badge rejected">REJECTED</span>
      <h3>ورود رد شد — به CRM نرسید</h3>
      <p>${failed ? failed.detail : "payload نامعتبر"}</p>
      <p class="telegram">این همان گیت داده خراب است: کار تکراری ورود دستی و داده ناقص حذف می‌شود.</p>
      ${renderChannels(run)}`;
    return;
  }
  const priority = lead.priority || "n/a";
  resultEl.className = "result";
  resultEl.innerHTML = `
    <span class="badge ${priority}">${String(priority).toUpperCase()}</span>
    <h3>${lead.name} — ${lead.company}</h3>
    <dl>
      <dt>CRM</dt><dd>#${lead.id} · ${lead.status}</dd>
      <dt>ایمیل</dt><dd>${lead.email}</dd>
      <dt>Intent / Fit</dt><dd>${lead.intent || "—"} / ${lead.product_fit || "—"}</dd>
      <dt>خلاصه</dt><dd>${lead.ai_summary || "—"}</dd>
      <dt>اقدام بعدی</dt><dd>${lead.recommended_next_action || "—"}</dd>
      <dt>Follow-up</dt><dd>${lead.follow_up_status}</dd>
    </dl>
    ${lead.draft_message ? `<div class="draft">${lead.draft_message}</div>` : ""}
    ${hitlButtons(lead)}
    ${renderChannels(run)}
  `;
  resultEl.querySelectorAll("[data-decision]").forEach((button) => {
    button.addEventListener("click", () => decideFollowup(button.dataset.decision));
  });
}

function renderBoard(leads) {
  const groups = { hot: [], warm: [], cold: [] };
  for (const lead of leads) {
    if (!lead.priority || !groups[lead.priority]) continue;
    groups[lead.priority].push(lead);
  }
  const unqual = leads.filter((lead) => !lead.priority);
  boardEl.innerHTML = ["hot", "warm", "cold"]
    .map((key) => {
      const cards = groups[key]
        .slice(0, 8)
        .map(
          (lead) =>
            `<div class="card"><b>${lead.company}</b><span>${lead.name} · ${lead.status} · ${lead.follow_up_status}</span></div>`
        )
        .join("");
      return `<div class="column"><h3>${key.toUpperCase()} (${groups[key].length})</h3>${cards || "<span>خالی</span>"}</div>`;
    })
    .join("");
  if (unqual.length) {
    boardEl.insertAdjacentHTML("beforeend", `<p class="lede">${unqual.length} لید هنوز qualify نشده‌اند.</p>`);
  }
}

async function loadBoard() {
  const leads = await fetchJson("/api/leads");
  renderBoard(leads);
}

async function decideFollowup(decision) {
  if (!currentLeadId) return;
  const path = decision === "accept" ? "approve-followup" : "reject-followup";
  try {
    await fetchJson(`/api/leads/${currentLeadId}/${path}`, { method: "POST" });
    const lead = await fetchJson(`/api/leads/${currentLeadId}`);
    resultEl.querySelectorAll(".hitl").forEach((el) => el.remove());
    resultEl.querySelectorAll("dt").forEach((dt) => {
      const dd = dt.nextElementSibling;
      if (!dd) return;
      if (dt.textContent === "CRM") dd.textContent = `#${lead.id} · ${lead.status}`;
      if (dt.textContent === "Follow-up") dd.textContent = lead.follow_up_status;
    });
    const note = document.createElement("div");
    note.className = "telegram";
    note.innerHTML =
      decision === "accept"
        ? `<b>قبول شد.</b> mock_sent · CRM: ${lead.status} — ارسال مشتری فقط بعد از این تأیید معنا دارد.`
        : `<b>رد شد.</b> follow_up=${lead.follow_up_status} · پیش‌نویس برای سابقه ماند، پیام مشتری نرفت.`;
    resultEl.appendChild(note);
    await loadBoard();
  } catch (err) {
    const note = document.createElement("div");
    note.className = "telegram";
    note.textContent = err.message;
    resultEl.appendChild(note);
  }
}

async function runSample(sample) {
  const via = selectedVia();
  const buttons = document.querySelectorAll("button[data-sample]");
  buttons.forEach((btn) => {
    btn.disabled = true;
  });
  timelineEl.innerHTML = "";
  renderPipeline(metaStages.map((stage) => ({ ...stage, status: "pending" })));
  resultEl.className = "result empty";
  resultEl.textContent =
    via === "n8n" ? "در حال ارسال به n8n… Executions را نگاه کنید." : "در حال اجرای مسیر مستقیم CRM…";
  try {
    const run = await fetchJson("/api/demo/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sample, via }),
    });
    const stagesState = metaStages.map((stage) => ({ ...stage, status: "pending" }));
    renderPipeline(stagesState);
    for (const stage of run.stages) {
      renderPipeline(
        stagesState.map((item) => (item.id === stage.id ? { ...stage, status: "running" } : item))
      );
      await sleep(220);
      const index = stagesState.findIndex((item) => item.id === stage.id);
      if (index >= 0) stagesState[index] = stage;
      renderPipeline(stagesState);
      appendTimeline(stage);
    }
    renderResult(run);
    await loadBoard();
  } catch (err) {
    resultEl.className = "result";
    resultEl.textContent = err.message;
  } finally {
    buttons.forEach((btn) => {
      btn.disabled = false;
    });
  }
}

async function boot() {
  const [health, meta] = await Promise.all([fetchJson("/health"), fetchJson("/api/demo/meta")]);
  renderHealth(health, meta);
  metaStages = meta.stages;
  renderPipeline(metaStages);
  await loadBoard();
  document.querySelectorAll("button[data-sample]").forEach((button) => {
    button.addEventListener("click", () => runSample(button.dataset.sample));
  });
}

boot().catch((err) => {
  resultEl.textContent = err.message;
});
