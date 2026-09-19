const pipelineEl = document.getElementById("pipeline");
const timelineEl = document.getElementById("timeline");
const resultEl = document.getElementById("result");
const boardEl = document.getElementById("board");
const healthEl = document.getElementById("health");
const hitlQueueEl = document.getElementById("hitl-queue");

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

function stageLabel(stage) {
  return stage.label_en || stage.label_fa || stage.id;
}

function renderHealth(health, meta) {
  const n8nOn = Boolean(meta && meta.n8n_webhook_configured);
  const sheetsOn = Boolean(meta && meta.n8n_sheets_configured) || health.google_sheets === "enabled";
  const chips = [
    ["n8n", n8nOn ? "on" : "off", n8nOn ? "connected" : "offline"],
    ["Groq", health.groq === "enabled" ? "on" : "off", health.groq],
    ["Telegram", health.telegram === "enabled" ? "on" : "off", health.telegram],
    ["Sheets", sheetsOn ? "on" : "off", sheetsOn ? "connected" : "offline"],
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
        <small>${escHtml(stage.n8n_node)}</small>
        <strong>${escHtml(stageLabel(stage))}</strong>
        <div class="state">${escHtml(stage.status)}</div>
      </li>`
    )
    .join("");
}

function appendTimeline(stage) {
  const item = document.createElement("li");
  item.innerHTML = `<div class="when">${escHtml(stageLabel(stage))} · ${escHtml(stage.status)}</div>
    <div>${escHtml(stage.detail || stage.n8n_node)}</div>`;
  timelineEl.prepend(item);
}

function escHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]
  );
}

function hitlButtons(lead) {
  if (!lead || lead.follow_up_status !== "awaiting_approval") return "";
  return `<div class="hitl">
      <button type="button" class="accept" data-decision="accept">Approve</button>
      <button type="button" class="reject" data-decision="reject">Reject</button>
    </div>`;
}

function renderChannels(run) {
  const sheets = run.sheets_status || "—";
  const exec = run.n8n_executions_url
    ? `<p class="telegram"><a href="${run.n8n_executions_url}" target="_blank" rel="noreferrer">n8n executions</a> · Sheets: <b>${escHtml(sheets)}</b></p>`
    : `<p class="telegram">Sheets: <b>${escHtml(sheets)}</b></p>`;
  const preview = run.telegram_preview
    ? `<pre class="draft telegram-preview">${escHtml(run.telegram_preview.replace(/<[^>]+>/g, ""))}</pre>`
    : "";
  const row = run.sheets_row
    ? `<pre class="draft">${escHtml(JSON.stringify(run.sheets_row, null, 2))}</pre>`
    : "";
  return `${exec}
    <div class="telegram">Sales channel (Telegram): <b>${escHtml(run.telegram_status)}</b></div>
    ${preview}
    ${row ? `<div class="telegram">Google Sheets row</div>${row}` : ""}`;
}

function renderResult(run) {
  const lead = run.lead;
  currentLeadId = lead ? lead.id : null;
  if (!lead) {
    resultEl.className = "result";
    const failed = (run.stages || []).find((stage) => stage.status === "failed");
    resultEl.innerHTML = `<span class="badge rejected">REJECTED</span>
      <h3>Lead was not written to CRM</h3>
      <p>${escHtml(failed ? failed.detail : "Invalid payload")}</p>
      ${renderChannels(run)}`;
    return;
  }
  const priority = lead.priority || "n/a";
  resultEl.className = "result";
  resultEl.innerHTML = `
    <span class="badge ${escHtml(priority)}">${escHtml(String(priority).toUpperCase())}</span>
    <h3>${escHtml(lead.name)} — ${escHtml(lead.company)}</h3>
    <dl>
      <dt>CRM</dt><dd>#${lead.id} · ${escHtml(lead.status)}</dd>
      <dt>Email</dt><dd>${escHtml(lead.email)}</dd>
      <dt>Intent / fit</dt><dd>${escHtml(lead.intent || "—")} / ${escHtml(lead.product_fit || "—")}</dd>
      <dt>Summary</dt><dd>${escHtml(lead.ai_summary || "—")}</dd>
      <dt>Next action</dt><dd>${escHtml(lead.recommended_next_action || "—")}</dd>
      <dt>Follow-up</dt><dd>${escHtml(lead.follow_up_status)}</dd>
    </dl>
    ${lead.draft_message ? `<div class="draft">${escHtml(lead.draft_message)}</div>` : ""}
    ${hitlButtons(lead)}
    ${renderChannels(run)}
  `;
  resultEl.querySelectorAll("[data-decision]").forEach((button) => {
    button.addEventListener("click", () => decideFollowup(lead.id, button.dataset.decision));
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
            `<div class="card"><b>${escHtml(lead.company)}</b><span>${escHtml(lead.name)} · ${escHtml(lead.status)} · ${escHtml(lead.follow_up_status)}</span></div>`
        )
        .join("");
      return `<div class="column"><h3>${key.toUpperCase()} (${groups[key].length})</h3>${cards || "<span>None</span>"}</div>`;
    })
    .join("");
  if (unqual.length) {
    boardEl.insertAdjacentHTML(
      "beforeend",
      `<p class="lede">${unqual.length} lead(s) are not qualified yet.</p>`
    );
  }
}

async function loadBoard() {
  const leads = await fetchJson("/api/leads");
  renderBoard(leads);
  renderHitlQueue(leads);
}

function renderHitlQueue(leads) {
  const pending = (leads || []).filter((lead) => lead.follow_up_status === "awaiting_approval");
  if (!pending.length) {
    hitlQueueEl.className = "hitl-queue empty";
    hitlQueueEl.textContent = "No drafts waiting for approval.";
    return;
  }
  hitlQueueEl.className = "hitl-queue";
  hitlQueueEl.innerHTML = pending
    .map(
      (lead) => `<article class="hitl-card">
        <h3>${escHtml(lead.name)} — ${escHtml(lead.company)}</h3>
        <div class="meta">CRM #${lead.id} · ${escHtml(lead.priority)} · ${escHtml(lead.status)}</div>
        <div class="draft">${escHtml(lead.draft_message || "")}</div>
        <div class="hitl">
          <button type="button" class="accept" data-decision="accept" data-lead-id="${lead.id}">Approve &amp; post to Telegram</button>
          <button type="button" class="reject" data-decision="reject" data-lead-id="${lead.id}">Reject</button>
        </div>
      </article>`
    )
    .join("");
  hitlQueueEl.querySelectorAll("[data-decision]").forEach((button) => {
    button.addEventListener("click", () =>
      decideFollowup(Number(button.dataset.leadId), button.dataset.decision)
    );
  });
}

async function decideFollowup(leadId, decision) {
  const path = decision === "accept" ? "approve-followup" : "reject-followup";
  try {
    await fetchJson(`/api/leads/${leadId}/${path}`, { method: "POST" });
    const lead = await fetchJson(`/api/leads/${leadId}`);
    if (currentLeadId === leadId) {
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
          ? `<b>Approved.</b> Posted to Telegram · CRM: ${escHtml(lead.status)} · follow-up: ${escHtml(lead.follow_up_status)}`
          : `<b>Rejected.</b> Customer was not contacted · follow-up: ${escHtml(lead.follow_up_status)}`;
      resultEl.appendChild(note);
    }
    await loadBoard();
  } catch (err) {
    const note = document.createElement("div");
    note.className = "telegram";
    note.textContent = err.message;
    (hitlQueueEl || resultEl).appendChild(note);
  }
}

async function runSample(sample) {
  const buttons = document.querySelectorAll("button[data-sample]");
  buttons.forEach((btn) => {
    btn.disabled = true;
  });
  timelineEl.innerHTML = "";
  renderPipeline(metaStages.map((stage) => ({ ...stage, status: "pending" })));
  resultEl.className = "result empty";
  resultEl.textContent = "Sending to n8n…";
  try {
    const run = await fetchJson("/api/demo/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sample, via: "n8n" }),
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
