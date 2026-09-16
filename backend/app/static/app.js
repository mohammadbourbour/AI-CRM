const pipelineEl = document.getElementById("pipeline");
const timelineEl = document.getElementById("timeline");
const resultEl = document.getElementById("result");
const boardEl = document.getElementById("board");
const healthEl = document.getElementById("health");

let metaStages = [];

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (response.status === 204) return null;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || response.statusText);
  }
  return body;
}

function renderHealth(health) {
  const chips = [
    ["OpenAI", health.openai === "enabled" ? "on" : "off", health.openai],
    ["Telegram", health.telegram === "enabled" ? "on" : "off", health.telegram],
    ["Sheets", health.google_sheets === "enabled" ? "on" : "off", health.google_sheets],
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

function renderResult(run) {
  const lead = run.lead;
  if (!lead) {
    resultEl.className = "result empty";
    resultEl.textContent = "اجرا بدون لید تمام شد.";
    return;
  }
  const priority = lead.priority || "n/a";
  resultEl.className = "result";
  resultEl.innerHTML = `
    <span class="badge ${priority}">${priority.toUpperCase()}</span>
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
    <div class="telegram">تلگرام کانال: <b>${run.telegram_status}</b></div>
  `;
}

function renderBoard(leads) {
  const groups = { hot: [], warm: [], cold: [] };
  for (const lead of leads) {
    const key = lead.priority && groups[lead.priority] ? lead.priority : "cold";
    if (!lead.priority) continue;
    groups[key].push(lead);
  }
  const unqual = leads.filter((lead) => !lead.priority);
  boardEl.innerHTML = ["hot", "warm", "cold"]
    .map((key) => {
      const cards = groups[key]
        .slice(0, 8)
        .map(
          (lead) => `<div class="card"><b>${lead.company}</b><span>${lead.name} · ${lead.status}</span></div>`
        )
        .join("");
      return `<div class="column"><h3>${key.toUpperCase()} (${groups[key].length})</h3>${cards || "<span>خالی</span>"}</div>`;
    })
    .join("");
  if (unqual.length) {
    boardEl.insertAdjacentHTML(
      "beforeend",
      `<p class="lede">${unqual.length} لید هنوز qualify نشده‌اند.</p>`
    );
  }
}

async function loadBoard() {
  const leads = await fetchJson("/api/leads");
  renderBoard(leads);
}

async function runSample(sample) {
  const buttons = document.querySelectorAll("button[data-sample]");
  buttons.forEach((btn) => {
    btn.disabled = true;
  });
  timelineEl.innerHTML = "";
  renderPipeline(metaStages.map((stage) => ({ ...stage, status: "pending" })));
  resultEl.className = "result empty";
  resultEl.textContent = "در حال اجرای مسیر واقعی CRM…";
  try {
    const run = await fetchJson("/api/demo/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sample }),
    });
    const stagesState = metaStages.map((stage) => ({ ...stage, status: "pending" }));
    renderPipeline(stagesState);
    for (const stage of run.stages) {
      renderPipeline(
        stagesState.map((item) =>
          item.id === stage.id ? { ...stage, status: "running" } : item
        )
      );
      await sleep(280);
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
  renderHealth(health);
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
