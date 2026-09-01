const TYPES = ["keyboard", "website", "app", "file", "system"];
const TYPE_LABEL = {
  keyboard: "Keyboard",
  website: "Website",
  app: "App",
  file: "File",
  system: "System",
};
const KEYBOARD_ACTIONS = [
  ["enter", "Enter"],
  ["backspace", "Backspace"],
  ["delete_word", "Delete last word"],
  ["delete_sentence", "Delete last sentence"],
  ["scratch", "Scratch that"],
];
const SYSTEM_ACTIONS = [
  ["mute", "Mute"],
  ["unmute", "Unmute"],
  ["volume_up", "Volume up"],
  ["volume_down", "Volume down"],
  ["play_pause", "Play / pause"],
  ["next", "Next track"],
  ["previous", "Previous track"],
  ["lock", "Lock screen"],
  ["sleep", "Sleep Mac"],
  ["display_sleep", "Sleep display"],
  ["screenshot", "Screenshot"],
  ["screenshot_selection", "Screenshot selection"],
];

let library = { commands: [], routines: [] };
let editorMode = null;
let editorIndex = -1;

const $ = (sel) => document.querySelector(sel);

function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => {
    el.hidden = true;
  }, 2600);
}

async function api(path, options) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function commandMeta(cmd) {
  if (cmd.type === "website") return cmd.url || "";
  if (cmd.type === "app") return cmd.app || "";
  if (cmd.type === "file") return cmd.path || "";
  if (cmd.type === "keyboard" || cmd.type === "system") return cmd.action || "";
  return "";
}

function renderStats(stats) {
  $("#stat-wpm").textContent = stats.average_wpm ? stats.average_wpm.toFixed(1) : "—";
  $("#stat-commands").textContent = String(stats.command_runs || 0);
  $("#stat-routines").textContent = String(stats.routine_runs || 0);
  $("#stat-words").textContent = String(stats.dictation_words || 0);
  const list = $("#activity");
  const items = stats.activity || [];
  if (!items.length) {
    list.innerHTML = `<li class="empty">Nothing yet. Dictate or run a command.</li>`;
    return;
  }
  list.innerHTML = items
    .map(
      (item) =>
        `<li><span>${formatTime(item.at)}</span><span class="kind">${item.kind}</span><span class="label">${escapeHtml(item.label || "")}</span></li>`
    )
    .join("");
}

function renderCommands() {
  const root = $("#command-groups");
  if (!library.commands.length) {
    root.innerHTML = `<p class="empty">No commands yet.</p>`;
    return;
  }
  root.innerHTML = TYPES.map((type) => {
    const items = library.commands.filter((c) => c.type === type);
    if (!items.length) return "";
    const rows = items
      .map((cmd, _i) => {
        const index = library.commands.indexOf(cmd);
        const phrases = (cmd.phrases || [])
          .map((p) => `<span class="pill">${escapeHtml(p)}</span>`)
          .join("");
        return `<div class="row" data-edit-command="${index}">
          <div>
            <div class="name">${escapeHtml(cmd.name)}</div>
            <div class="phrases">${phrases}</div>
          </div>
          <div class="meta">${escapeHtml(commandMeta(cmd))}</div>
        </div>`;
      })
      .join("");
    return `<div class="group"><h3>${TYPE_LABEL[type]}</h3>${rows}</div>`;
  }).join("");
  root.querySelectorAll("[data-edit-command]").forEach((el) => {
    el.addEventListener("click", () => openCommandEditor(Number(el.dataset.editCommand)));
  });
}

function renderRoutines() {
  const root = $("#routine-list");
  if (!library.routines.length) {
    root.innerHTML = `<p class="empty">No routines. Add one, then say “routine” and its name.</p>`;
    return;
  }
  root.innerHTML = library.routines
    .map((rtn, index) => {
      const steps = (rtn.steps || [])
        .map((step) => {
          const cmd = library.commands.find((c) => c.id === step.command_id);
          const delay = step.delay_ms ? ` · ${step.delay_ms} ms` : "";
          return `<span class="pill">${escapeHtml((cmd && cmd.name) || "Missing")}${delay}</span>`;
        })
        .join("");
      const aliases = [rtn.name, ...(rtn.phrases || [])]
        .filter(Boolean)
        .map((p) => `<span class="pill">routine ${escapeHtml(p)}</span>`)
        .join("");
      return `<div class="row" data-edit-routine="${index}">
        <div>
          <div class="name">${escapeHtml(rtn.name)}</div>
          <div class="phrases">${aliases}</div>
          <div class="phrases" style="margin-top:8px">${steps}</div>
        </div>
        <div class="meta">${(rtn.steps || []).length} steps</div>
      </div>`;
    })
    .join("");
  root.querySelectorAll("[data-edit-routine]").forEach((el) => {
    el.addEventListener("click", () => openRoutineEditor(Number(el.dataset.editRoutine)));
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function options(pairs, selected) {
  return pairs
    .map(([value, label]) => `<option value="${value}" ${value === selected ? "selected" : ""}>${label}</option>`)
    .join("");
}

function openCommandEditor(index) {
  editorMode = "command";
  editorIndex = index;
  const cmd =
    index >= 0
      ? { ...library.commands[index] }
      : { type: "keyboard", name: "", phrases: [], action: "enter", url: "", app: "", path: "" };
  $("#editor-title").textContent = index >= 0 ? "Edit command" : "New command";
  $("#editor-delete").classList.toggle("hidden", index < 0);
  $("#editor-body").innerHTML = `
    <label>Name<input name="name" required value="${escapeHtml(cmd.name || "")}" /></label>
    <label>Type
      <select name="type">${options(TYPES.map((t) => [t, TYPE_LABEL[t]]), cmd.type)}</select>
    </label>
    <label>Phrases <small>(comma-separated; exact match)</small>
      <input name="phrases" value="${escapeHtml((cmd.phrases || []).join(", "))}" />
    </label>
    <div id="type-fields"></div>
  `;
  const typeSelect = $("#editor-body [name=type]");
  const renderFields = () => {
    const type = typeSelect.value;
    const box = $("#type-fields");
    if (type === "keyboard") {
      box.innerHTML = `<label>Action<select name="action">${options(KEYBOARD_ACTIONS, cmd.action || "enter")}</select></label>`;
    } else if (type === "website") {
      box.innerHTML = `<label>URL<input name="url" placeholder="https://" value="${escapeHtml(cmd.url || "")}" /></label>`;
    } else if (type === "app") {
      box.innerHTML = `<label>App name<input name="app" placeholder="Safari" value="${escapeHtml(cmd.app || "")}" /></label>`;
    } else if (type === "file") {
      box.innerHTML = `<label>Path
        <span style="display:flex;gap:8px">
          <input name="path" style="flex:1" value="${escapeHtml(cmd.path || "")}" />
          <button type="button" id="pick-path">Browse</button>
        </span>
      </label>`;
      $("#pick-path").addEventListener("click", async () => {
        try {
          const result = await api("/api/pick-path", { method: "POST" });
          if (result.path) $("[name=path]").value = result.path;
        } catch (err) {
          toast(err.message);
        }
      });
    } else {
      box.innerHTML = `<label>Action<select name="action">${options(SYSTEM_ACTIONS, cmd.action || "mute")}</select></label>`;
    }
  };
  typeSelect.addEventListener("change", renderFields);
  renderFields();
  $("#editor").showModal();
}

function openRoutineEditor(index) {
  editorMode = "routine";
  editorIndex = index;
  const rtn =
    index >= 0
      ? JSON.parse(JSON.stringify(library.routines[index]))
      : { name: "", phrases: [], steps: [{ command_id: library.commands[0]?.id || "", delay_ms: 0 }] };
  $("#editor-title").textContent = index >= 0 ? "Edit routine" : "New routine";
  $("#editor-delete").classList.toggle("hidden", index < 0);
  const cmdOptions = library.commands.map((c) => [c.id, `${c.name} (${TYPE_LABEL[c.type]})`]);
  const stepHtml = (step) => `
    <div class="step">
      <select name="command_id">${options(cmdOptions, step.command_id)}</select>
      <input name="delay_ms" type="number" min="0" step="50" value="${Number(step.delay_ms || 0)}" title="Delay before this step (ms)" />
      <button type="button" class="up">Up</button>
      <button type="button" class="remove">Remove</button>
    </div>`;
  $("#editor-body").innerHTML = `
    <label>Name<input name="name" required value="${escapeHtml(rtn.name || "")}" /></label>
    <label>Extra aliases <small>(comma-separated; you still say “routine …”)</small>
      <input name="phrases" value="${escapeHtml((rtn.phrases || []).join(", "))}" />
    </label>
    <div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <span style="color:var(--muted);font-size:13px">Steps (delay is milliseconds before the step)</span>
        <button type="button" id="add-step">Add step</button>
      </div>
      <div id="steps">${(rtn.steps || []).map(stepHtml).join("")}</div>
    </div>
  `;
  const stepsBox = $("#steps");
  const bindSteps = () => {
    stepsBox.querySelectorAll(".remove").forEach((btn) => {
      btn.onclick = () => {
        btn.closest(".step").remove();
      };
    });
    stepsBox.querySelectorAll(".up").forEach((btn) => {
      btn.onclick = () => {
        const row = btn.closest(".step");
        if (row.previousElementSibling) stepsBox.insertBefore(row, row.previousElementSibling);
      };
    });
  };
  bindSteps();
  $("#add-step").onclick = () => {
    stepsBox.insertAdjacentHTML("beforeend", stepHtml({ command_id: cmdOptions[0]?.[0] || "", delay_ms: 0 }));
    bindSteps();
  };
  $("#editor").showModal();
}

function parsePhrases(raw) {
  return raw
    .split(",")
    .map((p) => p.trim())
    .filter(Boolean);
}

async function saveEditor(event) {
  event.preventDefault();
  const form = $("#editor-form");
  const body = $("#editor-body");
  if (editorMode === "command") {
    const type = body.querySelector("[name=type]").value;
    const next = {
      id: editorIndex >= 0 ? library.commands[editorIndex].id : undefined,
      type,
      name: body.querySelector("[name=name]").value.trim(),
      phrases: parsePhrases(body.querySelector("[name=phrases]").value),
    };
    if (type === "website") next.url = body.querySelector("[name=url]").value.trim();
    if (type === "app") next.app = body.querySelector("[name=app]").value.trim();
    if (type === "file") next.path = body.querySelector("[name=path]").value.trim();
    if (type === "keyboard" || type === "system") next.action = body.querySelector("[name=action]").value;
    const commands = library.commands.slice();
    if (editorIndex >= 0) commands[editorIndex] = next;
    else commands.push(next);
    await persist({ ...library, commands });
  } else {
    const steps = [...body.querySelectorAll(".step")].map((row) => ({
      command_id: row.querySelector("[name=command_id]").value,
      delay_ms: Number(row.querySelector("[name=delay_ms]").value || 0),
    }));
    const next = {
      id: editorIndex >= 0 ? library.routines[editorIndex].id : undefined,
      name: body.querySelector("[name=name]").value.trim(),
      phrases: parsePhrases(body.querySelector("[name=phrases]").value),
      steps,
    };
    const routines = library.routines.slice();
    if (editorIndex >= 0) routines[editorIndex] = next;
    else routines.push(next);
    await persist({ ...library, routines });
  }
  $("#editor").close();
}

async function deleteCurrent() {
  if (editorMode === "command" && editorIndex >= 0) {
    const id = library.commands[editorIndex].id;
    const commands = library.commands.filter((_, i) => i !== editorIndex);
    const routines = library.routines.map((rtn) => ({
      ...rtn,
      steps: (rtn.steps || []).filter((s) => s.command_id !== id),
    }));
    await persist({ commands, routines });
  } else if (editorMode === "routine" && editorIndex >= 0) {
    const routines = library.routines.filter((_, i) => i !== editorIndex);
    await persist({ ...library, routines });
  }
  $("#editor").close();
}

async function persist(next) {
  library = await api("/api/library", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(next),
  });
  renderCommands();
  renderRoutines();
  toast("Saved");
}

function showView(name) {
  document.querySelectorAll(".view").forEach((el) => el.classList.add("hidden"));
  $(`#view-${name}`).classList.remove("hidden");
  document.querySelectorAll("nav button").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === name);
  });
}

async function boot() {
  document.querySelectorAll("nav button").forEach((btn) => {
    btn.addEventListener("click", () => showView(btn.dataset.view));
  });
  $("#add-command").addEventListener("click", () => openCommandEditor(-1));
  $("#add-routine").addEventListener("click", () => openRoutineEditor(-1));
  $("#editor-cancel").addEventListener("click", () => $("#editor").close());
  $("#editor-delete").addEventListener("click", () => deleteCurrent());
  $("#editor-form").addEventListener("submit", (event) => {
    saveEditor(event).catch((err) => toast(err.message));
  });
  try {
    const [lib, stats] = await Promise.all([api("/api/library"), api("/api/stats")]);
    library = lib;
    renderCommands();
    renderRoutines();
    renderStats(stats);
  } catch (err) {
    toast(err.message);
  }
}

boot();
