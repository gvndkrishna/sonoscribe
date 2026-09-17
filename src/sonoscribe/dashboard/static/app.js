const TYPES = ["keyboard", "website", "app", "file", "system", "script", "text"];
const TYPE_LABEL = {
  keyboard: "Keyboard",
  website: "Website",
  app: "App",
  file: "File",
  system: "System",
  script: "Script",
  text: "Text",
};
const TYPE_SKU = {
  keyboard: "kb",
  website: "web",
  app: "app",
  file: "fil",
  system: "sys",
  script: "scr",
  text: "txt",
};

function token(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function kindColors() {
  return {
    dictate: token("--signal-a", "#8a7a4a"),
    command: token("--signal-b", "#7a5344"),
    routine: token("--signal-c", "#3f5c56"),
  };
}

function typeColors() {
  return {
    keyboard: token("--type-keyboard", "#111111"),
    website: token("--type-website", "#3f5c56"),
    app: token("--type-app", "#7a5344"),
    file: token("--type-file", "#8a7a4a"),
    system: token("--type-system", "#4a5c6b"),
    script: token("--type-script", "#6b4548"),
    text: token("--type-text", "#5c4a6b"),
  };
}

function chartInk() {
  return {
    ink: token("--ink", "#1d1d1f"),
    muted: token("--muted", "#6e6e73"),
    body: token("--ink-soft", "#3a3a3c"),
    hairline: token("--hairline", "#d8d8de"),
    accent: token("--accent", "#8a7a4a"),
  };
}
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

let library = { commands: [], routines: [], variables: [] };
let editorMode = null;
let editorIndex = -1;
let recordedKeys = [];
let recording = false;
let nativeKeyCapture = false;
let recordPoll = 0;
let commandQuery = "";
let commandFilter = "all";
let voiceQuery = "";
let activityItems = [];
let activityQuery = "";
const STATS_MS = 5000;
const LOCK_TIMEOUT_LABEL = {
  300: "5 minutes",
  600: "10 minutes",
  900: "15 minutes",
  1800: "30 minutes",
  2700: "45 minutes",
  3600: "60 minutes",
};
const SYNC_INTERVAL_LABEL = {
  0: "manual",
  300: "5 minutes",
  900: "15 minutes",
  1800: "30 minutes",
  3600: "60 minutes",
};
let lockIdleTimer = 0;
let lastLockActivity = 0;
let appBooted = false;
let autoRefreshStarted = false;
let lockPrompt = null;
let lockDrafting = false;
let lockChangingPin = false;
const OVERVIEW_ANIM_MS = 5000;
const CLOUD_MS = 2 * 60 * 1000;
const ACCENTS = ["blue", "purple", "amber", "teal", "gray"];
const PROVIDER_LABEL = { aws: "Amazon S3", gcs: "Google Cloud", azure: "Azure Blob" };
let settings = {
  theme: "light",
  accent: "amber",
  timezone: "local",
  reduce_motion: false,
  private_mode: false,
  lock: { enabled: false, method: "", timeout_sec: 900, unlocked: true, secrets: true, confirmed: false, timeouts: [300, 600, 900, 1800, 2700, 3600] },
  keychain_scope: "local",
  username: "",
  device: { id: "", name: "" },
  devices: [],
  timezones: [],
  accents: ACCENTS,
  model: "large-v3-turbo",
  models: [],
};
let modelState = {
  model: "large-v3-turbo",
  active: "large-v3-turbo",
  status: "ready",
  error: "",
  models: [],
};
let modelPoll = 0;
let modelAddOpen = false;
let lastModelTest = "";
let pendingPrivateKey = "";
let revealedKey = "";
let savedKeyConfirm = false;
let importOpen = false;
let syncEditing = false;
let syncEnableAfterSave = false;
let syncValidateError = "";
let syncSaveGen = 0;
let syncWizard = "";
let statsDevice = "";
let lastStats = null;
let lastOverviewAnimAt = 0;
let overviewFillTimer = 0;
let meterRaf = 0;
let chartOrderKey = null;
let chartBusy = false;
let chartSaveTimer = 0;
let chartResizeRaf = 0;
let editorApps = [];
let editorLaunchApp = null;
let installedApps = [];
let installedAppsAt = 0;

const $ = (sel) => document.querySelector(sel);

let toastGen = 0;

function overlayDialog() {
  if ($("#lock-gate")?.open) return $("#lock-gate");
  if ($("#settings")?.open) return $("#settings");
  if ($("#editor")?.open) return $("#editor");
  return null;
}

function placeToast(el) {
  const dialog = overlayDialog();
  el.classList.toggle("in-overlay", Boolean(dialog));
  el.style.top = "";
  el.style.left = "";
  if (!dialog) return;
  const box = dialog.getBoundingClientRect();
  el.style.top = `${Math.max(16, box.top + 16)}px`;
  el.style.left = `${box.left + box.width / 2}px`;
}

function showToastLayer(el) {
  if (typeof el.showPopover === "function") {
    try {
      if (!el.matches(":popover-open")) el.showPopover();
      return;
    } catch (_err) {
      /* older engines fall through */
    }
  }
  const host = overlayDialog() || document.body;
  if (el.parentElement !== host) host.appendChild(el);
  el.hidden = false;
}

function hideToastLayer(el) {
  if (typeof el.hidePopover === "function") {
    try {
      if (el.matches(":popover-open")) el.hidePopover();
    } catch (_err) {
      el.hidden = true;
    }
  } else {
    el.hidden = true;
  }
  if (el.parentElement && el.parentElement !== document.body) document.body.appendChild(el);
}

function hideToast() {
  const el = $("#toast");
  if (!el) return;
  const gen = toastGen;
  clearTimeout(toast._t);
  const finish = () => {
    if (gen !== toastGen) return;
    hideToastLayer(el);
    el.classList.remove("is-on", "is-out", "is-error", "in-overlay");
    el.style.top = "";
    el.style.left = "";
  };
  if (motionReduced() || !el.classList.contains("is-on")) {
    finish();
    return;
  }
  el.classList.remove("is-on");
  el.classList.add("is-out");
  const done = (event) => {
    if (event && event.target !== el) return;
    el.removeEventListener("animationend", done);
    finish();
  };
  el.addEventListener("animationend", done);
  toast._t = setTimeout(done, 220);
}

function toast(message, kind) {
  const el = $("#toast");
  if (!el) return;
  toastGen += 1;
  const copy = el.querySelector(".glass-copy") || el;
  const kicker = $("#toast-kicker");
  copy.textContent = message;
  if (kicker) kicker.textContent = kind === "error" ? "error" : "notice";
  el.classList.toggle("is-error", kind === "error");
  el.classList.remove("is-out");
  placeToast(el);
  showToastLayer(el);
  el.classList.remove("is-on");
  void el.offsetWidth;
  el.classList.add("is-on");
  clearTimeout(toast._t);
  toast._t = setTimeout(hideToast, 3400);
}

async function api(path, options = {}) {
  const { _skipConfirm, ...fetchOpts } = options;
  const res = await fetch(path, fetchOpts);
  let data = await res.json().catch(() => ({}));
  if (res.status === 401 && data.code === "locked") {
    applyLock({ ...(settings.lock || {}), enabled: true, unlocked: false, secrets: false, confirmed: false });
    ensureUnlock();
    throw Object.assign(new Error(data.error || "Locked."), { code: "locked" });
  }
  if (res.status === 401 && data.code === "confirm" && !_skipConfirm) {
    const ok = await ensureLockConfirm();
    if (!ok) throw Object.assign(new Error(data.error || "Confirm required."), { code: "confirm" });
    return api(path, { ...options, _skipConfirm: true });
  }
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function formatTime(iso) {
  if (!iso) return "";
  const opts = { hour: "2-digit", minute: "2-digit" };
  if (settings.timezone && settings.timezone !== "local") opts.timeZone = settings.timezone;
  return new Date(iso).toLocaleTimeString([], opts);
}

function motionReduced() {
  return document.documentElement.dataset.reduceMotion === "true";
}

function applyAppearance(prefs) {
  document.documentElement.dataset.theme = prefs.theme || "light";
  document.documentElement.dataset.accent = prefs.accent || "amber";
  const reduce =
    Boolean(prefs.reduce_motion) ||
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.documentElement.dataset.reduceMotion = reduce ? "true" : "false";
}

function settingsOpen() {
  return Boolean($("#settings") && $("#settings").open);
}

function mergeSettings(data) {
  settings = {
    ...settings,
    theme: data.theme || settings.theme,
    accent: data.accent || settings.accent,
    timezone: data.timezone || settings.timezone,
    reduce_motion: data.reduce_motion != null ? Boolean(data.reduce_motion) : settings.reduce_motion,
    private_mode: data.private_mode != null ? Boolean(data.private_mode) : settings.private_mode,
    lock: data.lock ? { ...settings.lock, ...data.lock } : settings.lock,
    keychain_scope: data.keychain_scope || settings.keychain_scope,
    username: data.username ?? settings.username,
    device: data.device || settings.device,
    devices: data.devices || settings.devices,
    timezones: data.timezones || settings.timezones,
    accents: data.accents || settings.accents,
    model: data.model || settings.model,
    models: data.models || settings.models,
    sync: data.sync || settings.sync,
    sync_intervals: data.sync_intervals || settings.sync_intervals,
    providers: data.providers || settings.providers,
    has_private_key: data.has_private_key,
    fingerprint: data.fingerprint || "",
    icloud_keychain: data.icloud_keychain,
    charts: Array.isArray(data.charts) ? data.charts : settings.charts,
  };
  applyAppearance(settings);
  applySettingsAttention(settings.sync);
  updateSyncNav();
}

function applySettingsAttention(sync) {
  const on = Boolean((sync || settings.sync || {}).last_error);
  document.querySelectorAll(".settings-mark").forEach((el) => {
    el.classList.toggle("hidden", !on);
  });
  $("#open-settings")?.classList.toggle("has-notice", on);
}

function lockBlocks() {
  return Boolean(settings.lock?.enabled && settings.lock?.unlocked === false);
}

function applyLock(data, { keepGate = false } = {}) {
  if (!data) return;
  settings.lock = {
    ...(settings.lock || {}),
    enabled: Boolean(data.enabled),
    method: data.method || "",
    timeout_sec: Number(data.timeout_sec) || 900,
    timeouts: data.timeouts || settings.lock.timeouts,
    unlocked: data.unlocked !== false,
    secrets: Boolean(data.secrets),
    confirmed: Boolean(data.confirmed),
  };
  if (data.unlocked === false && data.enabled) {
    settings.lock.unlocked = false;
  }
  if (!settings.lock.enabled) {
    settings.lock.unlocked = true;
    settings.lock.secrets = true;
  }
  renderSecretButtons();
  renderLockFields();
  if (lockBlocks()) clearTimeout(lockIdleTimer);
  else if (!keepGate) {
    hideLockGate();
    armLockIdle();
  }
}

function renderSecretButtons() {
  const on = Boolean(settings.lock?.enabled);
  const revealed = Boolean(settings.lock?.secrets);
  ["reveal-commands", "reveal-routines", "reveal-voice"].forEach((id) => {
    const btn = document.getElementById(id);
    if (!btn) return;
    btn.classList.toggle("hidden", !on);
    btn.setAttribute("aria-pressed", revealed ? "true" : "false");
  });
}

function lockTimeoutOptions() {
  const timeouts = settings.lock?.timeouts || Object.keys(LOCK_TIMEOUT_LABEL).map(Number);
  return timeouts.map((sec) => [String(sec), LOCK_TIMEOUT_LABEL[sec] || `${sec / 60} minutes`]);
}

function lockSaveVisible() {
  return Boolean(lockDrafting || lockChangingPin);
}

function lockNowVisible() {
  return Boolean(settings.lock?.enabled && !lockChangingPin);
}

function syncReady() {
  return Boolean(settings.lock?.enabled && String(settings.username || "").trim());
}

function updateSyncNav() {
  const btn = document.querySelector('[data-settings-pane="sync"]');
  if (!btn) return;
  const ready = syncReady();
  btn.setAttribute("aria-disabled", ready ? "false" : "true");
}

function showSettings(pane) {
  let target = pane || "personalization";
  if (target === "sync" && !syncReady()) {
    toast("Lock and username required.");
    target = "account";
  }
  document.querySelectorAll("[data-settings-pane]").forEach((el) => {
    el.classList.toggle("active", el.dataset.settingsPane === target);
  });
  document.querySelectorAll(".settings-pane").forEach((el) => {
    el.classList.toggle("hidden", el.id !== `pane-${target}`);
  });
  syncModelTest(target === "model");
}

function clearLockPinFields() {
  ["lock-pin", "lock-pin-again", "lock-pin-old", "lock-pin-new", "lock-pin-confirm"].forEach((id) => {
    const box = document.getElementById(id);
    if (box) box.value = "";
  });
}

function renderLockFields() {
  const lock = settings.lock || {};
  if (lock.enabled) lockDrafting = false;
  else lockChangingPin = false;
  const on = Boolean(lock.enabled || lockDrafting);
  const drafting = Boolean(lockDrafting);
  const changing = Boolean(lockChangingPin);
  const sw = $("#dashboard-lock");
  if (sw) sw.setAttribute("aria-pressed", on ? "true" : "false");
  $("#lock-fields")?.classList.toggle("hidden", !on);
  $("#lock-pin-fields")?.classList.toggle("hidden", !drafting);
  $("#lock-change-fields")?.classList.toggle("hidden", !changing);
  $("#lock-timeout")?.closest("label")?.classList.toggle("hidden", changing);
  $("#lock-save")?.classList.toggle("hidden", !(drafting || changing));
  $("#lock-cancel-change")?.classList.toggle("hidden", !changing);
  $("#lock-now")?.classList.toggle("hidden", !lockNowVisible());
  $("#lock-change")?.classList.toggle("hidden", !lockNowVisible());
  const timeout = $("#lock-timeout");
  if (timeout && timeout !== document.activeElement) {
    const current = String(lock.timeout_sec || 900);
    if (!timeout.options.length) {
      timeout.innerHTML = lockTimeoutOptions()
        .map(([value, label]) => `<option value="${value}">${label}</option>`)
        .join("");
    }
    timeout.value = current;
  }
  updateSyncNav();
}

function setLockScroll(on) {
  document.documentElement.classList.toggle("is-locked", Boolean(on));
}

function setPageFreeze(on) {
  const html = document.documentElement;
  if (on) {
    html.dataset.scrollY = String(window.scrollY);
    html.classList.add("is-frozen");
    return;
  }
  const y = Number(html.dataset.scrollY || 0);
  html.classList.remove("is-frozen");
  delete html.dataset.scrollY;
  window.scrollTo(0, y);
}

function overlayBlocksPageScroll(event) {
  if (document.documentElement.classList.contains("is-locked")) {
    event.preventDefault();
    return;
  }
  if (!document.documentElement.classList.contains("is-frozen")) return;
  if (event.target.closest("dialog[open] .settings-pane")) return;
  event.preventDefault();
}

function showLockGate(mode) {
  const gate = $("#lock-gate");
  if (!gate) return;
  const unlock = mode === "unlock";
  gate.classList.toggle("lock-full", unlock);
  setLockScroll(unlock);
  $("#lock-kicker").textContent = unlock ? "locked" : "confirm";
  $("#lock-title").textContent = unlock ? "sonoscribe" : "confirm";
  $("#lock-hint").textContent = "Enter your 4-digit PIN";
  $("#lock-pin-submit").textContent = unlock ? "unlock" : "confirm";
  $("#lock-cancel")?.classList.toggle("hidden", unlock);
  $("#lock-mark")?.classList.remove("is-unlock");
  const pin = $("#lock-gate-pin");
  if (pin) pin.value = "";
  if (!gate.open) gate.showModal();
  pin?.focus();
}

function hideLockGate() {
  const gate = $("#lock-gate");
  if (gate?.open && !lockBlocks()) gate.close();
  if (!lockBlocks()) {
    gate?.classList.remove("lock-full");
    setLockScroll(false);
  }
}

function armLockIdle() {
  clearTimeout(lockIdleTimer);
  const lock = settings.lock;
  if (!lock?.enabled || lock.unlocked === false) return;
  lockIdleTimer = setTimeout(() => {
    lockNow().catch(() => {});
  }, (Number(lock.timeout_sec) || 900) * 1000);
}

function noteLockActivity() {
  if (!settings.lock?.enabled || lockBlocks()) return;
  armLockIdle();
  const now = Date.now();
  if (now - lastLockActivity < 15000) return;
  lastLockActivity = now;
  api("/api/lock/activity", { method: "POST" }).catch(() => {});
}

async function lockNow() {
  try {
    const data = await api("/api/lock/lock", { method: "POST" });
    applyLock({ ...data, unlocked: false, secrets: false, confirmed: false, enabled: true });
  } catch {
    applyLock({ ...(settings.lock || {}), unlocked: false, secrets: false, confirmed: false, enabled: true });
  }
  await ensureUnlock();
}

function ensureUnlock() {
  if (!lockBlocks()) return Promise.resolve(true);
  if (lockPrompt) return lockPrompt;
  lockPrompt = promptLock("unlock").finally(() => {
    lockPrompt = null;
  });
  return lockPrompt;
}

function ensureLockConfirm() {
  if (settings.lock?.confirmed) return Promise.resolve(true);
  if (lockPrompt) return lockPrompt;
  lockPrompt = promptLock("confirm").finally(() => {
    lockPrompt = null;
  });
  return lockPrompt;
}

function promptLock(mode) {
  return new Promise((resolve) => {
    const gate = $("#lock-gate");
    const finish = (ok) => {
      gate?.removeEventListener("cancel", onCancel);
      $("#lock-pin-submit")?.removeEventListener("click", onPin);
      $("#lock-cancel")?.removeEventListener("click", onCancelClick);
      $("#lock-gate-pin")?.removeEventListener("keydown", onKey);
      if (mode === "confirm" && !lockBlocks()) hideLockGate();
      resolve(ok);
    };
    const onCancel = (event) => {
      if (mode === "unlock") event.preventDefault();
      else finish(false);
    };
    const onCancelClick = () => finish(false);
    const submitPin = async () => {
      const pin = $("#lock-gate-pin")?.value || "";
      try {
        const path = mode === "unlock" ? "/api/lock/unlock" : "/api/lock/confirm";
        const data = await api(path, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pin }),
          _skipConfirm: true,
        });
        applyLock(data, { keepGate: mode === "unlock" });
        if (mode === "unlock") await afterUnlock();
        finish(true);
      } catch (err) {
        toast(err.message, "error");
        const box = $("#lock-gate-pin");
        if (box) {
          box.value = "";
          box.focus();
        }
      }
    };
    const onPin = () => submitPin();
    const onKey = (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        submitPin();
      }
    };
    showLockGate(mode);
    gate?.addEventListener("cancel", onCancel);
    $("#lock-pin-submit")?.addEventListener("click", onPin);
    $("#lock-cancel")?.addEventListener("click", onCancelClick);
    $("#lock-gate-pin")?.addEventListener("keydown", onKey);
  });
}

function playUnlockMark() {
  return new Promise((resolve) => {
    const mark = $("#lock-mark");
    const shackle = mark?.querySelector(".lock-shackle");
    if (!shackle || motionReduced()) {
      resolve();
      return;
    }
    mark.classList.remove("is-unlock");
    void mark.offsetWidth;
    let settled = false;
    const done = () => {
      if (settled) return;
      settled = true;
      shackle.removeEventListener("animationend", onEnd);
      resolve();
    };
    const onEnd = (event) => {
      if (event.target !== shackle) return;
      if (event.animationName && event.animationName !== "lock-open") return;
      done();
    };
    shackle.addEventListener("animationend", onEnd);
    mark.classList.add("is-unlock");
    window.setTimeout(done, 720);
  });
}

async function afterUnlock() {
  await playUnlockMark();
  hideLockGate();
  armLockIdle();
  if (appBooted) {
    try {
      await refresh({ pull: true });
      renderAccount();
    } catch (err) {
      toast(err.message);
    }
  }
}

async function toggleSecrets() {
  if (!settings.lock?.enabled) return;
  const reveal = !settings.lock.secrets;
  try {
    const data = await api("/api/lock/secrets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reveal }),
    });
    applyLock(data);
    const lib = await api("/api/library");
    library = lib;
    renderCommands();
    renderRoutines();
    renderVoice();
  } catch (err) {
    toast(err.message, "error");
  }
}

function bindLockUi() {
  const gate = $("#lock-gate");
  gate?.addEventListener("cancel", (event) => {
    if (lockBlocks()) event.preventDefault();
  });
  const stopOverlayScroll = (event) => overlayBlocksPageScroll(event);
  document.addEventListener("wheel", stopOverlayScroll, { passive: false });
  document.addEventListener("touchmove", stopOverlayScroll, { passive: false });
  ["pointerdown", "keydown", "click"].forEach((name) => {
    document.addEventListener(name, noteLockActivity, { passive: true });
  });
  $("#reveal-commands")?.addEventListener("click", () => toggleSecrets());
  $("#reveal-routines")?.addEventListener("click", () => toggleSecrets());
  $("#reveal-voice")?.addEventListener("click", () => toggleSecrets());
}

function commandMeta(cmd) {
  if (cmd.type === "website") return cmd.url || "";
  if (cmd.type === "app") {
    const label = cmd.app && !looksLikeBundleId(cmd.app) ? cmd.app : "";
    return label || cmd.bundle_id || cmd.app || "";
  }
  if (cmd.type === "file") return cmd.path || "";
  if (cmd.type === "script") return cmd.path || (cmd.runtime === "applescript" ? "AppleScript" : "Bash");
  if (cmd.type === "keyboard") {
    if (cmd.keys && cmd.keys.length) return cmd.keys.map((step) => step.label).filter(Boolean).join(" ");
    return cmd.action || "";
  }
  if (cmd.type === "system") return cmd.action || "";
  if (cmd.type === "text") return cmd.text || "{*}";
  return "";
}

function commandMatches(cmd) {
  if (commandFilter !== "all" && cmd.type !== commandFilter) return false;
  const q = commandQuery.trim().toLowerCase();
  if (!q) return true;
  const hay = [
    cmd.name,
    cmd.type,
    TYPE_LABEL[cmd.type],
    commandMeta(cmd),
    ...(cmd.phrases || []),
    ...(cmd.apps || []).flatMap((app) => [app.name, app.bundle_id]),
  ]
    .join(" ")
    .toLowerCase();
  return hay.includes(q);
}

function meterCells(stats) {
  const cells = [
    { el: $("#stat-wpm"), value: Number(stats.average_wpm) || 0, digits: 1, empty: "—" },
    { el: $("#stat-commands"), value: Number(stats.command_runs) || 0, digits: 0 },
    { el: $("#stat-routines"), value: Number(stats.routine_runs) || 0, digits: 0 },
    { el: $("#stat-words"), value: Number(stats.dictation_words) || 0, digits: 0 },
  ];
  const devicesWrap = $("#stat-devices-wrap");
  if (devicesWrap && !devicesWrap.classList.contains("hidden")) {
    const devices = stats.devices || settings.devices || [];
    cells.push({ el: $("#stat-devices"), value: devices.length, digits: 0 });
  }
  return cells;
}

function syncActive(stats) {
  return Boolean((settings.sync && settings.sync.enabled) || (stats && stats.stats_synced));
}

function renderMeterMeta(stats) {
  const on = syncActive(stats);
  $("#stat-devices-wrap")?.classList.toggle("hidden", !on);
  const scope = $("#instrument-scope");
  if (scope) scope.textContent = on ? "sync" : "local";
}

function writeMeterValues(stats, progress) {
  meterCells(stats).forEach((cell) => {
    if (!cell.el) return;
    if (cell.empty && !cell.value) {
      cell.el.textContent = cell.empty;
      return;
    }
    const n = cell.value * progress;
    cell.el.textContent = cell.digits ? n.toFixed(cell.digits) : String(Math.round(n));
  });
}

function setMeterValues(stats, animate) {
  if (!stats) return;
  if (meterRaf) {
    cancelAnimationFrame(meterRaf);
    meterRaf = 0;
  }
  if (!animate || motionReduced()) {
    writeMeterValues(stats, 1);
    return;
  }
  const start = performance.now();
  const dur = 720;
  const step = (now) => {
    const t = Math.min(1, (now - start) / dur);
    writeMeterValues(stats, 1 - (1 - t) ** 3);
    if (t < 1) meterRaf = requestAnimationFrame(step);
    else meterRaf = 0;
  };
  writeMeterValues(stats, 0);
  meterRaf = requestAnimationFrame(step);
}

function clearOverviewFill() {
  $("#view-overview")?.classList.remove("is-filling");
  if (overviewFillTimer) {
    clearTimeout(overviewFillTimer);
    overviewFillTimer = 0;
  }
  if (meterRaf) {
    cancelAnimationFrame(meterRaf);
    meterRaf = 0;
  }
}

function playOverviewMotion({ force = false } = {}) {
  const view = $("#view-overview");
  if (!view || view.classList.contains("hidden")) return;
  if (motionReduced()) {
    clearOverviewFill();
    if (lastStats) setMeterValues(lastStats, false);
    return;
  }
  if (!force && lastOverviewAnimAt && Date.now() - lastOverviewAnimAt < OVERVIEW_ANIM_MS) return;
  lastOverviewAnimAt = Date.now();
  if (lastStats) setMeterValues(lastStats, true);
  view.classList.remove("is-filling");
  void view.offsetWidth;
  view.classList.add("is-filling");
  if (overviewFillTimer) clearTimeout(overviewFillTimer);
  overviewFillTimer = setTimeout(() => {
    view.classList.remove("is-filling");
    overviewFillTimer = 0;
  }, 1400);
}

function renderStats(stats) {
  lastStats = stats;
  renderMeterMeta(stats);
  setMeterValues(stats, false);
  activityItems = (stats.activity || []).slice(0, 30);
  renderActivity();
  renderChartGrid();
  renderCharts(stats);
  renderStatsDevice(stats);
}

function renderStatsDevice(stats) {
  const wrap = $("#stats-device-wrap");
  const select = $("#stats-device");
  if (!wrap || !select) return;
  const devices = stats.devices || [];
  if (!stats.stats_synced) {
    wrap.classList.add("hidden");
    const unit = document.querySelector("#view-overview .unit");
    if (unit) unit.textContent = "01 / this mac";
    return;
  }
  wrap.classList.remove("hidden");
  const current = stats.device_id || statsDevice || settings.device?.id || "";
  select.innerHTML = devices
    .map((item) => {
      const label = item.this ? `${item.name} (this Mac)` : item.name;
      return `<option value="${escapeHtml(item.id)}"${item.id === current ? " selected" : ""}>${escapeHtml(label)}</option>`;
    })
    .join("");
    statsDevice = current;
  const unit = document.querySelector("#view-overview .unit");
  const selected = devices.find((item) => item.id === current);
  if (unit) {
    unit.textContent = selected ? `01 / ${selected.name}` : "01 / this mac";
  }
}

function statsUrl() {
  return statsDevice ? `/api/stats?device=${encodeURIComponent(statsDevice)}` : "/api/stats";
}

function deviceLabel(item) {
  const ids = item.devices || [];
  if (!ids.length) return "";
  const thisId = settings.device?.id;
  if (ids.length === 1 && ids[0] === thisId) return "this Mac only";
  const names = ids.map((id) => {
    const found = (settings.devices || []).find((device) => device.id === id);
    return found ? found.name : "device";
  });
  return names.join(", ");
}

function activityMatches(item) {
  const q = activityQuery.trim().toLowerCase();
  if (!q) return true;
  const when = item.at ? new Date(item.at).toLocaleString() : "";
  return [item.kind, item.label, formatTime(item.at), when]
    .join(" ")
    .toLowerCase()
    .includes(q);
}

function renderActivity() {
  const list = $("#activity");
  const items = activityItems.filter(activityMatches);
  if (!activityItems.length) {
    list.innerHTML = `<li class="empty">nothing yet. dictate or run a command.</li>`;
    return;
  }
  if (!items.length) {
    list.innerHTML = `<li class="empty">no activity matches that search.</li>`;
    return;
  }
  list.innerHTML = items
    .map(
      (item) =>
        `<li><span>${formatTime(item.at)}</span><span class="kind kind-${escapeHtml(item.kind)}">${item.kind}</span><span class="label">${escapeHtml(item.label || "")}</span></li>`
    )
    .join("");
}

const CHART_CATALOG = [
  { id: "mix", title: "activity mix" },
  { id: "versus", title: "commands vs dictation" },
  { id: "types", title: "command types" },
  { id: "models", title: "models" },
  { id: "model-wpm", title: "wpm by model" },
  { id: "daily", title: "last 14 days" },
  { id: "top", title: "top commands" },
  { id: "routines", title: "top routines" },
  { id: "routine-split", title: "commands vs routines" },
  { id: "hourly", title: "time of day" },
  { id: "library", title: "library mix" },
];
const GRID_COLS = 24;
const ROW_H = 8;
const MIN_W = 3;
const MAX_W = 24;
const MIN_H = 20;
const MAX_H = 80;
const DEFAULT_W = 8;
const DEFAULT_H = 34;

function defaultCharts() {
  const out = [];
  let x = 0;
  let y = 0;
  CHART_CATALOG.forEach((item) => {
    const w = item.id === "library" ? 16 : DEFAULT_W;
    if (x + w > GRID_COLS) {
      x = 0;
      y += DEFAULT_H;
    }
    out.push({ id: item.id, x, y, w, h: DEFAULT_H });
    x += w;
    if (x >= GRID_COLS) {
      x = 0;
      y += DEFAULT_H;
    }
  });
  return out;
}

function chartsOverlap(a, b) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

function placeChart(existing, w, h) {
  const maxY = existing.reduce((sum, item) => Math.max(sum, item.y + item.h), 0);
  for (let y = 0; y <= maxY; y += 1) {
    for (let x = 0; x <= GRID_COLS - w; x += 1) {
      const cand = { x, y, w, h };
      if (!existing.some((item) => chartsOverlap(cand, item))) return { x, y };
    }
  }
  return { x: 0, y: maxY };
}

function packCharts(layout, pinnedId) {
  const items = layout.map((item) => clampChart(item));
  const pinned = pinnedId ? items.find((item) => item.id === pinnedId) : null;
  const packed = [];
  if (pinned) packed.push({ ...pinned });
  items
    .filter((item) => !pinned || item.id !== pinnedId)
    .sort((a, b) => a.y - b.y || a.x - b.x)
    .forEach((item) => {
      packed.push(settleChart(item, packed));
    });
  return packed;
}

function chartFits(item, occupied) {
  if (item.x < 0 || item.y < 0 || item.x + item.w > GRID_COLS) return false;
  return !occupied.some((other) => other.id !== item.id && chartsOverlap(item, other));
}

function settleChart(item, occupied) {
  let { id, x, y, w, h } = item;
  if (!chartFits({ id, x, y, w, h }, occupied)) {
    const spot = placeChart(occupied, w, h);
    x = spot.x;
    y = spot.y;
  }
  let moved = true;
  while (moved) {
    moved = false;
    if (y > 0 && chartFits({ id, x, y: y - 1, w, h }, occupied)) {
      y -= 1;
      moved = true;
    } else if (x > 0 && chartFits({ id, x: x - 1, y, w, h }, occupied)) {
      x -= 1;
      moved = true;
    }
  }
  return { id, x, y, w, h };
}

function clampChart(item) {
  const w = Math.min(MAX_W, Math.max(MIN_W, Number(item.w) || DEFAULT_W));
  const h = Math.min(MAX_H, Math.max(MIN_H, Number(item.h) || DEFAULT_H));
  const x = Math.min(GRID_COLS - w, Math.max(0, Number(item.x) || 0));
  const y = Math.max(0, Number(item.y) || 0);
  return { id: item.id, x, y, w, h };
}

function chartSizeFromLegacy(item) {
  let w;
  let h;
  if (item.w != null) w = Number(item.w) || DEFAULT_W;
  else {
    const cols = Math.min(3, Math.max(1, Number(item.cols) || 1));
    w = { 1: 8, 2: 16, 3: 24 }[cols];
  }
  if (item.h != null) h = Number(item.h) || DEFAULT_H;
  else if (item.height != null) {
    const px = Math.min(560, Math.max(160, Number(item.height) || 220));
    h = Math.round(px / ROW_H);
  } else h = DEFAULT_H;
  return {
    w: Math.min(MAX_W, Math.max(MIN_W, w)),
    h: Math.min(MAX_H, Math.max(MIN_H, h)),
  };
}

function chartLayout() {
  const raw = settings.charts;
  if (!Array.isArray(raw)) return defaultCharts();
  const known = new Set(CHART_CATALOG.map((item) => item.id));
  const seen = new Set();
  const positioned = [];
  const pending = [];
  for (const item of raw) {
    const id = item && item.id;
    if (!known.has(id) || seen.has(id)) continue;
    seen.add(id);
    const size = chartSizeFromLegacy(item);
    if ("x" in item && "y" in item) {
      positioned.push(clampChart({ id, ...size, x: item.x, y: item.y }));
    } else {
      pending.push({ id, ...size });
    }
  }
  const out = positioned.slice();
  pending.forEach((item) => {
    const spot = placeChart(out, item.w, item.h);
    out.push({ id: item.id, ...spot, w: item.w, h: item.h });
  });
  return out;
}

function hiddenCharts() {
  const shown = new Set(chartLayout().map((item) => item.id));
  return CHART_CATALOG.filter((item) => !shown.has(item.id));
}

function chartCardHtml(item) {
  const meta = CHART_CATALOG.find((row) => row.id === item.id);
  const title = meta ? meta.title : item.id;
  return `<article class="chart-card" data-chart="${item.id}">
    <header class="chart-head">
      <h2>${title}</h2>
      <button type="button" class="chart-remove" data-remove-chart="${item.id}" aria-label="Remove ${title}">×</button>
    </header>
    <div id="chart-${item.id}" class="chart-body"></div>
    <button type="button" class="chart-resize chart-resize-e" data-resize-chart="${item.id}" data-resize-axis="x" aria-label="Resize ${title} width"></button>
    <button type="button" class="chart-resize chart-resize-s" data-resize-chart="${item.id}" data-resize-axis="y" aria-label="Resize ${title} height"></button>
    <button type="button" class="chart-resize chart-resize-se" data-resize-chart="${item.id}" data-resize-axis="xy" aria-label="Resize ${title}"></button>
  </article>`;
}

function applyChartSizes(layout) {
  const grid = $("#chart-grid");
  if (!grid) return;
  const maxY = layout.reduce((sum, item) => Math.max(sum, item.y + item.h), 0);
  grid.style.height = layout.length ? `${Math.max(maxY * ROW_H, 140)}px` : "";
  layout.forEach((item) => {
    const card = grid.querySelector(`.chart-card[data-chart="${item.id}"]`);
    if (!card) return;
    card.style.left = `calc(${(item.x / GRID_COLS) * 100}% - 1px)`;
    card.style.width = `calc(${(item.w / GRID_COLS) * 100}% + 1px)`;
    card.style.top = `${item.y * ROW_H - 1}px`;
    card.style.height = `${item.h * ROW_H + 1}px`;
  });
}

function renderAddChartMenu() {
  const btn = $("#add-chart");
  const menu = $("#chart-add-menu");
  if (!btn || !menu) return;
  const hidden = hiddenCharts();
  btn.disabled = hidden.length === 0;
  const items = $("#chart-add-items") || menu;
  items.innerHTML = hidden
    .map((item) => `<button type="button" role="menuitem" data-add-chart="${item.id}">${item.title}</button>`)
    .join("");
}

function renderChartGrid() {
  const grid = $("#chart-grid");
  if (!grid || chartBusy) return;
  const layout = chartLayout();
  const orderKey = layout.map((item) => item.id).join("|");
  if (orderKey !== chartOrderKey) {
    chartOrderKey = orderKey;
    grid.classList.toggle("is-empty", layout.length === 0);
    grid.innerHTML = layout.length
      ? layout.map((item) => chartCardHtml(item)).join("")
      : `<div class="chart-empty-grid">no graphs. add one to start.</div>`;
  }
  applyChartSizes(layout);
  renderAddChartMenu();
}

function persistChartLayout(layout, { rebuild = true } = {}) {
  settings.charts = layout;
  if (rebuild) renderChartGrid();
  else applyChartSizes(layout);
  renderAddChartMenu();
  if (rebuild && lastStats) renderCharts(lastStats);
  clearTimeout(chartSaveTimer);
  const save = () => {
    api("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ charts: chartLayout() }),
    })
      .then((data) => mergeSettings(data))
      .catch((err) => toast(err.message, "error"));
  };
  if (rebuild) save();
  else chartSaveTimer = setTimeout(save, 280);
}

function addChart(id) {
  const layout = chartLayout();
  if (layout.some((item) => item.id === id)) return;
  const w = id === "library" ? 16 : DEFAULT_W;
  const spot = placeChart(layout, w, DEFAULT_H);
  persistChartLayout([...layout, { id, ...spot, w, h: DEFAULT_H }]);
}

function removeChart(id) {
  persistChartLayout(packCharts(chartLayout().filter((item) => item.id !== id)));
}

function patchChart(id, patch, { persist = false, pack = false } = {}) {
  let layout = chartLayout().map((item) => (item.id === id ? clampChart({ ...item, ...patch }) : item));
  if (pack) layout = packCharts(layout, id);
  settings.charts = layout;
  applyChartSizes(layout);
  if (persist) persistChartLayout(layout, { rebuild: false });
  return layout;
}

function edgeScroll(clientY) {
  const edge = 72;
  const view = window.innerHeight;
  let dy = 0;
  if (clientY < edge) dy = -Math.max(6, Math.round((edge - clientY) * 0.4));
  else if (clientY > view - edge) dy = Math.max(6, Math.round((clientY - (view - edge)) * 0.4));
  if (!dy) return false;
  const top = window.scrollY;
  const max = Math.max(0, document.documentElement.scrollHeight - view);
  const next = Math.min(max, Math.max(0, top + dy));
  if (next === top) return false;
  window.scrollTo(0, next);
  return true;
}

function gridMetrics() {
  const grid = $("#chart-grid");
  const width = grid ? grid.clientWidth : 1;
  return { colW: width / GRID_COLS, rowH: ROW_H };
}

function startChartMove(event, id) {
  event.preventDefault();
  const item = chartLayout().find((row) => row.id === id);
  const card = document.querySelector(`.chart-card[data-chart="${id}"]`);
  if (!item || !card) return;
  chartBusy = true;
  const { colW, rowH } = gridMetrics();
  const originX = event.clientX;
  const originY = event.clientY;
  const startScroll = window.scrollY;
  const startX = item.x;
  const startY = item.y;
  let lastX = event.clientX;
  let lastY = event.clientY;
  let raf = 0;
  card.classList.add("is-dragging");
  card.setPointerCapture?.(event.pointerId);
  const apply = () => {
    const x = startX + Math.round((lastX - originX) / colW);
    const y = startY + Math.round((lastY - originY + window.scrollY - startScroll) / rowH);
    patchChart(id, { x, y }, { pack: true });
  };
  const tick = () => {
    raf = requestAnimationFrame(tick);
    if (edgeScroll(lastY)) apply();
  };
  const onMove = (ev) => {
    lastX = ev.clientX;
    lastY = ev.clientY;
    apply();
  };
  const onUp = () => {
    cancelAnimationFrame(raf);
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
    card.classList.remove("is-dragging");
    chartBusy = false;
    persistChartLayout(packCharts(chartLayout(), id), { rebuild: false });
  };
  window.addEventListener("pointermove", onMove);
  window.addEventListener("pointerup", onUp);
  raf = requestAnimationFrame(tick);
}

function startChartResize(event, id, axis) {
  event.preventDefault();
  event.stopPropagation();
  const item = chartLayout().find((row) => row.id === id);
  const card = document.querySelector(`.chart-card[data-chart="${id}"]`);
  if (!item || !card) return;
  chartBusy = true;
  const { colW, rowH } = gridMetrics();
  const originX = event.clientX;
  const originY = event.clientY;
  const startW = item.w;
  const startH = item.h;
  card.classList.add("is-resizing");
  const onMove = (ev) => {
    const patch = {};
    if (axis.includes("x")) {
      patch.w = Math.min(GRID_COLS - item.x, Math.max(MIN_W, startW + Math.round((ev.clientX - originX) / colW)));
    }
    if (axis.includes("y")) {
      patch.h = Math.min(MAX_H, Math.max(MIN_H, startH + Math.round((ev.clientY - originY) / rowH)));
    }
    patchChart(id, patch, { pack: true });
    if (!lastStats) return;
    cancelAnimationFrame(chartResizeRaf);
    chartResizeRaf = requestAnimationFrame(() => renderCharts(lastStats));
  };
  const onUp = () => {
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
    card.classList.remove("is-resizing");
    chartBusy = false;
    persistChartLayout(packCharts(chartLayout(), id), { rebuild: false });
    if (lastStats) renderCharts(lastStats);
  };
  window.addEventListener("pointermove", onMove);
  window.addEventListener("pointerup", onUp);
}

function bindCharts() {
  const grid = $("#chart-grid");
  if (!grid) return;
  grid.addEventListener("click", (event) => {
    const remove = event.target.closest("[data-remove-chart]");
    if (!remove) return;
    event.preventDefault();
    removeChart(remove.dataset.removeChart);
  });
  grid.addEventListener("pointerdown", (event) => {
    if (event.button != null && event.button !== 0) return;
    const resize = event.target.closest("[data-resize-chart]");
    if (resize) {
      startChartResize(event, resize.dataset.resizeChart, resize.dataset.resizeAxis || "xy");
      return;
    }
    if (event.target.closest(".chart-remove")) return;
    const head = event.target.closest(".chart-head");
    if (!head) return;
    const card = head.closest(".chart-card");
    if (card) startChartMove(event, card.dataset.chart);
  });
  $("#add-chart")?.addEventListener("click", (event) => {
    event.stopPropagation();
    const hidden = hiddenCharts();
    if (!hidden.length) return;
    $("#chart-add-menu")?.classList.toggle("hidden");
  });
  $("#chart-add-menu")?.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-add-chart]");
    if (!btn) return;
    addChart(btn.dataset.addChart);
    $("#chart-add-menu").classList.add("hidden");
  });
  document.addEventListener("click", (event) => {
    if (event.target.closest(".chart-add-wrap")) return;
    $("#chart-add-menu")?.classList.add("hidden");
  });
}

function renderCharts(stats) {
  if (!stats) return;
  const charts = stats.charts || {};
  renderMix($("#chart-mix"), charts.by_kind || {});
  renderVersus($("#chart-versus"), charts.versus || charts.by_kind || {});
  renderTypeSplit($("#chart-types"), charts.by_command_type || {});
  renderByModel($("#chart-models"), charts.by_model || []);
  renderWpmByModel($("#chart-model-wpm"), charts.wpm_by_model || []);
  renderDaily($("#chart-daily"), charts.daily || []);
  renderTop($("#chart-top"), charts.top_commands || [], "run a command to see the leaders");
  renderTop($("#chart-routines"), charts.top_routines || [], "run a routine to see the leaders");
  renderRoutineSplit($("#chart-routine-split"), charts.versus_routines || {});
  renderHourly($("#chart-hourly"), charts.hourly || []);
  renderLibrary($("#chart-library"));
  renderUsage(charts.usage || []);
}

function usageLevel(count) {
  if (!count) return 0;
  if (count < 2) return 1;
  if (count < 4) return 2;
  if (count < 7) return 3;
  return 4;
}

function usageMonthLabel(week, prev) {
  if (!week.length) return "";
  const firstOfMonth = week.find((item) => String(item.day).endsWith("-01"));
  if (!firstOfMonth && prev) return "";
  const day = firstOfMonth ? firstOfMonth.day : week[0].day;
  return new Date(`${day}T12:00:00`).toLocaleDateString([], { month: "short" }).toLowerCase();
}

function renderUsage(days) {
  const grid = $("#usage-grid");
  const months = $("#usage-months");
  const summary = $("#usage-summary");
  if (!grid) return;
  const rows = days.length ? days : [];
  const used = rows.filter((item) => item.count).length;
  if (summary) {
    summary.textContent = used ? `${used} day${used === 1 ? "" : "s"}` : "no use yet";
  }
  grid.setAttribute("aria-label", used ? `Model use, ${used} days` : "Model use");
  if (!rows.length) {
    grid.innerHTML = "";
    if (months) months.innerHTML = "";
    return;
  }
  const weeks = [];
  for (let i = 0; i < rows.length; i += 7) weeks.push(rows.slice(i, i + 7));
  if (months) {
    months.innerHTML = weeks
      .map((week, index) => `<span>${usageMonthLabel(week, weeks[index - 1])}</span>`)
      .join("");
  }
  grid.innerHTML = weeks
    .map((week, weekIndex) =>
      week
        .map((item) => {
          const level = usageLevel(item.count);
          const when = new Date(`${item.day}T12:00:00`).toLocaleDateString([], {
            month: "short",
            day: "numeric",
          });
          const tip = item.count
            ? `${when}: ${item.count} use${item.count === 1 ? "" : "s"}`
            : `${when}: no use`;
          return `<span class="usage-cell" data-level="${level}" style="--d:${weekIndex * 18}" data-tip="${escapeHtml(tip)}"></span>`;
        })
        .join("")
    )
    .join("");
  bindHovers(grid);
}

function emptyChart(message) {
  return `<div class="chart-empty">${message}</div>`;
}

function showTip(event, text) {
  const tip = $("#chart-tip");
  const copy = tip.querySelector(".glass-copy") || tip;
  copy.textContent = text;
  tip.hidden = false;
  tip.style.left = `${event.clientX + 12}px`;
  tip.style.top = `${event.clientY + 12}px`;
}

function hideTip() {
  $("#chart-tip").hidden = true;
}

function bindHovers(root) {
  root.querySelectorAll("[data-tip]").forEach((el) => {
    el.addEventListener("mousemove", (event) => showTip(event, el.dataset.tip));
    el.addEventListener("mouseleave", hideTip);
  });
}

function renderMix(el, byKind) {
  if (!el) return;
  const colors = kindColors();
  const ink = chartInk();
  const segments = [
    { label: "dictate", value: byKind.dictate || 0, color: colors.dictate },
    { label: "commands", value: byKind.command || 0, color: colors.command },
    { label: "routines", value: byKind.routine || 0, color: colors.routine },
  ];
  const total = segments.reduce((sum, item) => sum + item.value, 0);
  if (!total) {
    el.innerHTML = emptyChart("no activity yet");
    return;
  }
  const cx = 80;
  const cy = 78;
  const r = 46;
  const sw = 10;
  let angle = -Math.PI / 2;
  const present = segments.filter((item) => item.value > 0);
  const arcs =
    present.length === 1
      ? `<circle class="fill-arc" pathLength="1" cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${present[0].color}" stroke-width="${sw}" data-tip="${present[0].label}: ${present[0].value}"></circle>`
      : present
          .map((item, index) => {
            const slice = (item.value / total) * Math.PI * 2;
            const start = angle;
            angle += slice;
            const large = slice > Math.PI ? 1 : 0;
            const x1 = cx + r * Math.cos(start);
            const y1 = cy + r * Math.sin(start);
            const x2 = cx + r * Math.cos(angle);
            const y2 = cy + r * Math.sin(angle);
            return `<path class="fill-arc" pathLength="1" style="--d:${index * 90}" d="M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}" fill="none" stroke="${item.color}" stroke-width="${sw}" stroke-linecap="butt" data-tip="${item.label}: ${item.value}"></path>`;
          })
          .join("");
  el.innerHTML = `<svg viewBox="0 0 160 160" role="img" aria-label="Activity mix">
    ${arcs}
    <text x="${cx}" y="76" text-anchor="middle" fill="${ink.ink}" font-size="20" font-weight="300">${total}</text>
    <text x="${cx}" y="94" text-anchor="middle" fill="${ink.muted}" font-size="10">events</text>
  </svg>
  <div class="legend">${present
    .map((item) => `<span><i style="background:${item.color}"></i>${item.label} ${item.value}</span>`)
    .join("")}</div>`;
  bindHovers(el);
}

function renderVersus(el, versus) {
  if (!el) return;
  const ink = chartInk();
  const colors = kindColors();
  const rows = [
    { label: "dictation", value: versus.dictate || 0, color: colors.dictate },
    { label: "commands", value: versus.command || 0, color: colors.command },
  ];
  const max = Math.max(...rows.map((row) => row.value), 0);
  if (!max) {
    el.innerHTML = emptyChart("no dictation or commands yet");
    return;
  }
  el.innerHTML = `<svg viewBox="0 0 320 ${rows.length * 44 + 8}" role="img" aria-label="Commands vs dictation">
    ${rows
      .map((row, index) => {
        const y = 10 + index * 44;
        const w = Math.max(8, (row.value / max) * 200);
        return `<text x="0" y="${y + 14}" fill="${ink.body}" font-size="12">${row.label}</text>
          <rect class="fill-h" style="--d:${index * 80}" x="96" y="${y + 8}" width="${w}" height="6" fill="${row.color}" data-tip="${row.label}: ${row.value}"></rect>
          <text x="${108 + w}" y="${y + 14}" fill="${ink.muted}" font-size="12">${row.value}</text>`;
      })
      .join("")}
  </svg>`;
  bindHovers(el);
}

function renderTypeSplit(el, byType) {
  if (!el) return;
  const colors = typeColors();
  const ink = chartInk();
  const rows = TYPES.map((type) => ({
    type,
    label: TYPE_LABEL[type].toLowerCase(),
    value: byType[type] || 0,
    color: colors[type],
  })).filter((item) => item.value);
  const total = rows.reduce((sum, item) => sum + item.value, 0);
  if (!total) {
    el.innerHTML = emptyChart("run commands to see type split");
    return;
  }
  const cx = 80;
  const cy = 78;
  const r = 46;
  const sw = 10;
  let angle = -Math.PI / 2;
  const arcs =
    rows.length === 1
      ? `<circle class="fill-arc" pathLength="1" cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${rows[0].color}" stroke-width="${sw}" data-tip="${rows[0].label}: ${rows[0].value}"></circle>`
      : rows
          .map((item, index) => {
            const slice = (item.value / total) * Math.PI * 2;
            const start = angle;
            angle += slice;
            const large = slice > Math.PI ? 1 : 0;
            const x1 = cx + r * Math.cos(start);
            const y1 = cy + r * Math.sin(start);
            const x2 = cx + r * Math.cos(angle);
            const y2 = cy + r * Math.sin(angle);
            return `<path class="fill-arc" pathLength="1" style="--d:${index * 90}" d="M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}" fill="none" stroke="${item.color}" stroke-width="${sw}" data-tip="${item.label}: ${item.value}"></path>`;
          })
          .join("");
  el.innerHTML = `<svg viewBox="0 0 160 160" role="img" aria-label="Command types">
    ${arcs}
    <text x="${cx}" y="76" text-anchor="middle" fill="${ink.ink}" font-size="20" font-weight="300">${total}</text>
    <text x="${cx}" y="94" text-anchor="middle" fill="${ink.muted}" font-size="10">runs</text>
  </svg>
  <div class="legend">${rows
    .map((item) => `<span><i style="background:${item.color}"></i>${item.label} ${item.value}</span>`)
    .join("")}</div>`;
  bindHovers(el);
}

function renderDaily(el, days) {
  if (!el) return;
  const colors = kindColors();
  const ink = chartInk();
  const max = Math.max(
    1,
    ...days.map((day) => (day.dictate || 0) + (day.command || 0) + (day.routine || 0))
  );
  if (!days.some((day) => (day.dictate || 0) + (day.command || 0) + (day.routine || 0))) {
    el.innerHTML = emptyChart("no activity in the last 14 days");
    return;
  }
  const width = 320;
  const height = 150;
  const gap = 3;
  const bar = (width - 28) / days.length - gap;
  const stacks = days
    .map((day, index) => {
      const x = 18 + index * (bar + gap);
      let y = height - 22;
      const kinds = [
        ["dictate", day.dictate || 0],
        ["command", day.command || 0],
        ["routine", day.routine || 0],
      ];
      const parts = kinds
        .map(([kind, value]) => {
          if (!value) return "";
          const h = Math.max(2, (value / max) * 104);
          y -= h;
          return `<rect class="fill-v" style="--d:${index * 32}" x="${x}" y="${y}" width="${bar}" height="${h}" fill="${colors[kind]}" data-tip="${day.day}: ${kind} ${value}"></rect>`;
        })
        .join("");
      const label = new Date(`${day.day}T12:00:00`).toLocaleDateString([], { weekday: "narrow" });
      return `${parts}<text x="${x + bar / 2}" y="${height - 6}" text-anchor="middle" fill="${ink.muted}" font-size="9">${label}</text>`;
    })
    .join("");
  el.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Last 14 days">${stacks}</svg>
    <div class="legend">
      <span><i style="background:${colors.dictate}"></i>dictate</span>
      <span><i style="background:${colors.command}"></i>commands</span>
      <span><i style="background:${colors.routine}"></i>routines</span>
    </div>`;
  bindHovers(el);
}

function renderTop(el, rows, emptyMessage) {
  const ink = chartInk();
  if (!el) return;
  if (!rows.length) {
    el.innerHTML = emptyChart(emptyMessage || "run a command to see the leaders");
    return;
  }
  const max = Math.max(...rows.map((row) => row.count), 1);
  el.innerHTML = `<svg viewBox="0 0 320 ${rows.length * 28 + 8}" role="img" aria-label="Top commands">
    ${rows
      .map((row, index) => {
        const y = 8 + index * 28;
        const w = Math.max(8, (row.count / max) * 170);
        return `<text x="0" y="${y + 12}" fill="${ink.body}" font-size="11">${escapeHtml(row.label)}</text>
          <rect class="fill-h" style="--d:${index * 70}" x="120" y="${y + 6}" width="${w}" height="4" fill="${ink.accent}" data-tip="${escapeHtml(row.label)}: ${row.count}"></rect>
          <text x="${128 + w}" y="${y + 12}" fill="${ink.muted}" font-size="11">${row.count}</text>`;
      })
      .join("")}
  </svg>`;
  bindHovers(el);
}

function renderHourly(el, hours) {
  if (!el) return;
  const ink = chartInk();
  const values = hours.length === 24 ? hours : Array(24).fill(0);
  const max = Math.max(...values, 0);
  if (!max) {
    el.innerHTML = emptyChart("no timed activity yet");
    return;
  }
  const bars = values
    .map((value, hour) => {
      if (!value) return "";
      const h = Math.max(4, (value / max) * 110);
      const x = 12 + hour * 12.4;
      const y = 128 - h;
      const label = `${String(hour).padStart(2, "0")}:00`;
      return `<rect class="fill-v" style="--d:${hour * 16}" x="${x}" y="${y}" width="8" height="${h}" fill="${ink.accent}" data-tip="${label}: ${value}"></rect>`;
    })
    .join("");
  el.innerHTML = `<svg viewBox="0 0 320 150" role="img" aria-label="Time of day">
    <line x1="12" y1="128" x2="308" y2="128" stroke="${ink.hairline}" stroke-width="1" />
    ${bars}
    <text x="12" y="146" fill="${ink.muted}" font-size="9">00</text>
    <text x="154" y="146" fill="${ink.muted}" font-size="9">12</text>
    <text x="298" y="146" fill="${ink.muted}" font-size="9">23</text>
  </svg>`;
  bindHovers(el);
}

function signalColor(index) {
  const keys = ["--signal-a", "--signal-b", "--signal-c", "--signal-d"];
  const fallbacks = ["#8a7a4a", "#7a5344", "#3f5c56", "#4a5c6b"];
  return token(keys[index % keys.length], fallbacks[index % fallbacks.length]);
}

function renderByModel(el, rows) {
  if (!el) return;
  const items = (rows || []).filter((row) => row.count);
  if (!items.length) {
    el.innerHTML = emptyChart("no model data yet");
    return;
  }
  const ink = chartInk();
  const segments = items.map((row, index) => ({
    label: row.label || row.id || "model",
    value: row.count || 0,
    color: signalColor(index),
  }));
  const total = segments.reduce((sum, item) => sum + item.value, 0);
  const cx = 80;
  const cy = 78;
  const r = 46;
  const sw = 10;
  let angle = -Math.PI / 2;
  const arcs =
    segments.length === 1
      ? `<circle class="fill-arc" pathLength="1" cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${segments[0].color}" stroke-width="${sw}" data-tip="${escapeHtml(segments[0].label)}: ${segments[0].value}"></circle>`
      : segments
          .map((item, index) => {
            const slice = (item.value / total) * Math.PI * 2;
            const start = angle;
            angle += slice;
            const large = slice > Math.PI ? 1 : 0;
            const x1 = cx + r * Math.cos(start);
            const y1 = cy + r * Math.sin(start);
            const x2 = cx + r * Math.cos(angle);
            const y2 = cy + r * Math.sin(angle);
            return `<path class="fill-arc" pathLength="1" style="--d:${index * 90}" d="M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}" fill="none" stroke="${item.color}" stroke-width="${sw}" stroke-linecap="butt" data-tip="${escapeHtml(item.label)}: ${item.value}"></path>`;
          })
          .join("");
  el.innerHTML = `<svg viewBox="0 0 160 160" role="img" aria-label="Models">
    ${arcs}
    <text x="${cx}" y="76" text-anchor="middle" fill="${ink.ink}" font-size="20" font-weight="300">${total}</text>
    <text x="${cx}" y="94" text-anchor="middle" fill="${ink.muted}" font-size="10">events</text>
  </svg>
  <div class="legend">${segments
    .map((item) => `<span><i style="background:${item.color}"></i>${escapeHtml(item.label)} ${item.value}</span>`)
    .join("")}</div>`;
  bindHovers(el);
}

function renderWpmByModel(el, rows) {
  if (!el) return;
  const ink = chartInk();
  if (!rows.length) {
    el.innerHTML = emptyChart("dictate to compare models");
    return;
  }
  const max = Math.max(...rows.map((row) => row.wpm || 0), 0);
  if (!max) {
    el.innerHTML = emptyChart("dictate to compare models");
    return;
  }
  el.innerHTML = `<svg viewBox="0 0 320 ${rows.length * 44 + 8}" role="img" aria-label="WPM by model">
    ${rows
      .map((row, index) => {
        const y = 10 + index * 44;
        const w = Math.max(8, (row.wpm / max) * 200);
        const label = row.label || row.id || "model";
        return `<text x="0" y="${y + 14}" fill="${ink.body}" font-size="12">${escapeHtml(label)}</text>
          <rect class="fill-h" style="--d:${index * 80}" x="96" y="${y + 8}" width="${w}" height="6" fill="${signalColor(index)}" data-tip="${escapeHtml(label)}: ${row.wpm} wpm"></rect>
          <text x="${108 + w}" y="${y + 14}" fill="${ink.muted}" font-size="12">${row.wpm}</text>`;
      })
      .join("")}
  </svg>`;
  bindHovers(el);
}

function renderRoutineSplit(el, versus) {
  if (!el) return;
  const ink = chartInk();
  const colors = kindColors();
  const rows = [
    { label: "commands", value: versus.command || 0, color: colors.command },
    { label: "routines", value: versus.routine || 0, color: colors.routine },
  ];
  const max = Math.max(...rows.map((row) => row.value), 0);
  if (!max) {
    el.innerHTML = emptyChart("run a command or routine");
    return;
  }
  el.innerHTML = `<svg viewBox="0 0 320 ${rows.length * 44 + 8}" role="img" aria-label="Commands vs routines">
    ${rows
      .map((row, index) => {
        const y = 10 + index * 44;
        const w = Math.max(8, (row.value / max) * 200);
        return `<text x="0" y="${y + 14}" fill="${ink.body}" font-size="12">${row.label}</text>
          <rect class="fill-h" style="--d:${index * 80}" x="96" y="${y + 8}" width="${w}" height="6" fill="${row.color}" data-tip="${row.label}: ${row.value}"></rect>
          <text x="${108 + w}" y="${y + 14}" fill="${ink.muted}" font-size="12">${row.value}</text>`;
      })
      .join("")}
  </svg>`;
  bindHovers(el);
}

function renderLibrary(el) {
  if (!el) return;
  const colors = typeColors();
  const counts = TYPES.map((type) => ({
    type,
    label: TYPE_LABEL[type].toLowerCase(),
    value: library.commands.filter((cmd) => cmd.type === type).length,
    color: colors[type],
  }));
  const total = counts.reduce((sum, item) => sum + item.value, 0);
  if (!total) {
    el.innerHTML = emptyChart("add a command to see the mix");
    return;
  }
  let x = 0;
  const width = 640;
  const parts = counts
    .filter((item) => item.value)
    .map((item) => {
      const w = Math.max(18, (item.value / total) * width);
      const node = `<rect x="${x}" y="28" width="${w - 2}" height="8" fill="${item.color}" data-tip="${item.label}: ${item.value}"></rect>`;
      x += w;
      return node;
    })
    .join("");
  el.innerHTML = `<svg viewBox="0 0 ${width} 86" role="img" aria-label="Library mix"><g class="fill-h">${parts}</g></svg>
    <div class="legend">${counts
      .map((item) => `<span><i style="background:${item.color}"></i>${item.label} ${item.value}</span>`)
      .join("")}</div>`;
  bindHovers(el);
}

function renderCommands() {
  const root = $("#command-groups");
  const visible = library.commands.filter(commandMatches);
  if (!library.commands.length) {
    root.innerHTML = `<p class="empty">No commands.</p>`;
    return;
  }
  if (!visible.length) {
    root.innerHTML = `<p class="empty">No matches.</p>`;
    return;
  }
  root.innerHTML = TYPES.map((type) => {
    const items = visible.filter((cmd) => cmd.type === type);
    if (!items.length) return "";
    const rows = items
      .map((cmd, typeIndex) => {
        const index = library.commands.indexOf(cmd);
        const sku = `${TYPE_SKU[type]}–${String(typeIndex + 1).padStart(2, "0")}`;
        const phrases = (cmd.phrases || [])
          .map((p) => `<span class="pill">${escapeHtml(p)}</span>`)
          .join("");
        const extra = deviceLabel(cmd);
        const appIcons = appIconsHtml(cmd.apps);
        return `<div class="row${cmd.secret ? " is-secret" : ""}" data-edit-command="${index}" data-type="${type}">
          <span class="sku">${sku}</span>
          <div>
            <div class="name">${escapeHtml(cmd.name)}${appIcons}</div>
            <div class="phrases">${phrases}${extra ? `<span class="pill">${escapeHtml(extra)}</span>` : ""}</div>
          </div>
          <div class="meta">${escapeHtml(commandMeta(cmd))}</div>
        </div>`;
      })
      .join("");
    return `<div class="group"><h3>${TYPE_LABEL[type].toLowerCase()}</h3>${rows}</div>`;
  }).join("");
  root.querySelectorAll("[data-edit-command]").forEach((el) => {
    el.addEventListener("click", () => openCommandEditor(Number(el.dataset.editCommand)));
  });
}

function isSlotTemplate(value) {
  return /\{[a-z0-9_*]+\}/i.test(String(value || ""));
}

function renderVoice() {
  const root = $("#voice-list");
  if (!root) return;
  const items = library.variables || [];
  const visible = items.filter((item) => {
    const q = voiceQuery.trim().toLowerCase();
    if (!q) return true;
    return `${item.name || ""} ${item.value || ""}`.toLowerCase().includes(q);
  });
  if (!items.length) {
    root.innerHTML = `<p class="empty">no vocab.</p>`;
    return;
  }
  if (!visible.length) {
    root.innerHTML = `<p class="empty">No matches.</p>`;
    return;
  }
  root.innerHTML = visible
    .map((item) => {
      const index = items.indexOf(item);
      return `<div class="row${item.secret ? " is-secret" : ""}" data-edit-voice="${index}">
        <span class="sku">vo–${String(index + 1).padStart(2, "0")}</span>
        <div>
          <div class="name">{${escapeHtml(item.name || "")}}</div>
          <div class="phrases"><span class="pill">${escapeHtml(item.value || "")}</span></div>
        </div>
      </div>`;
    })
    .join("");
  root.querySelectorAll("[data-edit-voice]").forEach((el) => {
    el.addEventListener("click", () => openVoiceEditor(Number(el.dataset.editVoice)));
  });
}

function openVoiceEditor(index) {
  editorMode = "variable";
  editorIndex = index;
  const item =
    index >= 0
      ? { ...(library.variables || [])[index] }
      : { name: "", value: "" };
  $("#editor-title").textContent = index >= 0 ? "edit vocab" : "new vocab";
  $("#editor-delete").classList.toggle("hidden", index < 0);
  $("#editor-body").innerHTML = `
    <div class="form-stack">
      ${field("Name", `<input name="name" required placeholder="hello" value="${escapeHtml(item.name || "")}" autocomplete="off" />`)}
      ${field("Says", `<textarea name="value" rows="4" placeholder="Greetings guys">${escapeHtml(item.value || "")}</textarea>`)}
      ${secretSwitchHtml(item.secret)}
    </div>
  `;
  bindSecretSwitch();
  $("#editor").showModal();
}

function renderRoutines() {
  const root = $("#routine-list");
  if (!library.routines.length) {
    root.innerHTML = `<p class="empty">No routines.</p>`;
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
      const extra = deviceLabel(rtn);
      return `<div class="row${rtn.secret ? " is-secret" : ""}" data-edit-routine="${index}">
        <span class="sku">rt–${String(index + 1).padStart(2, "0")}</span>
        <div>
          <div class="name">${escapeHtml(rtn.name)}</div>
          <div class="phrases">${aliases}${extra ? `<span class="pill">${escapeHtml(extra)}</span>` : ""}</div>
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
    .map(([value, label]) => `<option value="${escapeHtml(value)}" ${value === selected ? "selected" : ""}>${escapeHtml(label)}</option>`)
    .join("");
}

const CODE_TO_VK = {
  KeyA: 0x00, KeyS: 0x01, KeyD: 0x02, KeyF: 0x03, KeyH: 0x04, KeyG: 0x05, KeyZ: 0x06,
  KeyX: 0x07, KeyC: 0x08, KeyV: 0x09, KeyB: 0x0b, KeyQ: 0x0c, KeyW: 0x0d, KeyE: 0x0e,
  KeyR: 0x0f, KeyY: 0x10, KeyT: 0x11, Digit1: 0x12, Digit2: 0x13, Digit3: 0x14,
  Digit4: 0x15, Digit6: 0x16, Digit5: 0x17, Equal: 0x18, Digit9: 0x19, Digit7: 0x1a,
  Minus: 0x1b, Digit8: 0x1c, Digit0: 0x1d, BracketRight: 0x1e, KeyO: 0x1f, KeyU: 0x20,
  BracketLeft: 0x21, KeyI: 0x22, KeyP: 0x23, Enter: 0x24, KeyL: 0x25, KeyJ: 0x26,
  Quote: 0x27, KeyK: 0x28, Semicolon: 0x29, Backslash: 0x2a, Comma: 0x2b, Slash: 0x2c,
  KeyN: 0x2d, KeyM: 0x2e, Period: 0x2f, Tab: 0x30, Space: 0x31, Backquote: 0x32,
  Backspace: 0x33, Escape: 0x35, NumpadDecimal: 0x41, NumpadMultiply: 0x43,
  NumpadAdd: 0x45, NumpadDivide: 0x4b, NumpadEnter: 0x4c, NumpadSubtract: 0x4e,
  NumpadEqual: 0x51, Numpad0: 0x52, Numpad1: 0x53, Numpad2: 0x54, Numpad3: 0x55,
  Numpad4: 0x56, Numpad5: 0x57, Numpad6: 0x58, Numpad7: 0x59, Numpad8: 0x5b,
  Numpad9: 0x5c, F5: 0x60, F6: 0x61, F7: 0x62, F3: 0x63, F8: 0x64, F9: 0x65,
  F11: 0x67, F13: 0x69, F16: 0x6a, F14: 0x6b, F10: 0x6d, F12: 0x6f, F15: 0x71,
  Help: 0x72, Insert: 0x72, Home: 0x73, PageUp: 0x74, Delete: 0x75, F4: 0x76,
  End: 0x77, F2: 0x78, PageDown: 0x79, F1: 0x7a, ArrowLeft: 0x7b, ArrowRight: 0x7c,
  ArrowDown: 0x7d, ArrowUp: 0x7e,
};

function field(label, control, help) {
  return `<div class="field">
    <span class="field-label">${label}</span>
    <div class="field-control">${control}</div>
    ${help ? `<p class="field-help">${help}</p>` : ""}
  </div>`;
}

function chordLabel(event) {
  const bits = [];
  if (event.ctrlKey) bits.push("⌃");
  if (event.altKey) bits.push("⌥");
  if (event.shiftKey) bits.push("⇧");
  if (event.metaKey) bits.push("⌘");
  const name = event.code.startsWith("Key")
    ? event.code.slice(3)
    : event.code.startsWith("Digit")
      ? event.code.slice(5)
      : event.key.length === 1
        ? event.key.toUpperCase()
        : event.key;
  bits.push(name);
  return bits.join("");
}

function setRecordButton(active) {
  const btn = $("#record-keys");
  if (!btn) return;
  btn.classList.toggle("is-recording", active);
  btn.setAttribute("aria-pressed", active ? "true" : "false");
  btn.innerHTML = `<span class="rec-dot" aria-hidden="true"></span>${active ? "Stop" : "Record"}`;
}

function stopRecording() {
  recording = false;
  if (recordPoll) {
    clearInterval(recordPoll);
    recordPoll = 0;
  }
  document.removeEventListener("keydown", onRecordKey, true);
  if (nativeKeyCapture) {
    nativeKeyCapture = false;
    fetch("/api/keys/record/stop", { method: "POST" }).catch(() => {});
  }
  const box = $("#keys-box");
  if (box) box.classList.remove("listening");
  setRecordButton(false);
}

function renderKeyChips() {
  const chips = $("#key-chips");
  if (!chips) return;
  chips.innerHTML = recordedKeys.length
    ? recordedKeys.map((step) => `<span class="pill">${escapeHtml(step.label)}</span>`).join("")
    : `<span class="muted">No keys yet</span>`;
}

function onRecordKey(event) {
  if (!recording) return;
  if (event.key === "Escape" && !event.metaKey && !event.ctrlKey && !event.altKey && !event.shiftKey) {
    event.preventDefault();
    event.stopPropagation();
    stopRecording();
    return;
  }
  if (["Meta", "Shift", "Control", "Alt", "MetaLeft", "MetaRight"].includes(event.key)) return;
  event.preventDefault();
  event.stopPropagation();
  const vk = CODE_TO_VK[event.code];
  if (vk === undefined) {
    toast(`Key ${event.code} is not supported`);
    return;
  }
  const mods = [];
  if (event.ctrlKey) mods.push("control");
  if (event.altKey) mods.push("option");
  if (event.shiftKey) mods.push("shift");
  if (event.metaKey) mods.push("command");
  recordedKeys.push({ vk, mods, label: chordLabel(event) });
  renderKeyChips();
}

async function pollNativeKeys() {
  if (!recording || !nativeKeyCapture) return;
  try {
    const data = await api("/api/keys/record/events");
    const keys = data.keys || [];
    if (keys.length) {
      recordedKeys.push(...keys);
      renderKeyChips();
    }
    if (data.stopped) stopRecording();
  } catch (_err) {
    /* keep the button armed; the next tick retries */
  }
}

function bindKeyRecorder() {
  const record = $("#record-keys");
  const clear = $("#clear-keys");
  if (!record) return;
  record.addEventListener("click", () => {
    if (recording) {
      stopRecording();
      return;
    }
    recording = true;
    nativeKeyCapture = false;
    setRecordButton(true);
    $("#keys-box").classList.add("listening");
    api("/api/keys/record/start", { method: "POST" })
      .then((data) => {
        if (!recording) return;
        nativeKeyCapture = Boolean(data.native);
        if (nativeKeyCapture) {
          recordPoll = window.setInterval(pollNativeKeys, 50);
          return;
        }
        document.addEventListener("keydown", onRecordKey, true);
      })
      .catch(() => {
        if (!recording) return;
        document.addEventListener("keydown", onRecordKey, true);
      });
  });
  if (clear) {
    clear.addEventListener("click", () => {
      recordedKeys = [];
      renderKeyChips();
    });
  }
}

function browsePath(selector) {
  return async () => {
    try {
      const result = await api("/api/pick-path", { method: "POST" });
      if (result.path) $(selector).value = result.path;
    } catch (err) {
      toast(err.message);
    }
  };
}

function looksLikeBundleId(value) {
  return /^[A-Za-z][A-Za-z0-9-]*(\.[A-Za-z0-9][A-Za-z0-9-]*)+$/.test(String(value || "").trim());
}

function appName(app) {
  return String((app && (app.name || app.bundle_id)) || "app").trim() || "app";
}

function appKey(app) {
  const bundleId = String((app && app.bundle_id) || "").trim();
  const name = String((app && app.name) || bundleId).trim();
  return bundleId.toLowerCase() || (name ? `name:${name.toLowerCase()}` : "");
}

function normalizeApp(app) {
  if (!app) return null;
  const bundleId = String(app.bundle_id || "").trim();
  let name = String(app.name || "").trim();
  if (looksLikeBundleId(name) && !bundleId) return { bundle_id: name, name };
  if (looksLikeBundleId(name)) name = "";
  if (!bundleId && !name) return null;
  return { bundle_id: bundleId, name: name || bundleId };
}

function appIconHtml(app) {
  const name = appName(app);
  const initials = name.slice(0, 2);
  const id = (app && app.bundle_id) || "";
  const img = id
    ? `<img class="app-icon-img" src="/api/apps/icon?id=${encodeURIComponent(id)}" alt="${escapeHtml(name)}" onerror="this.hidden=true;const n=this.nextElementSibling;if(n)n.hidden=false" />`
    : "";
  return `<span class="app-icon has-tip" data-name="${escapeHtml(name)}" aria-label="${escapeHtml(name)}">${img}<b ${id ? "hidden" : ""}>${escapeHtml(initials)}</b></span>`;
}

function appIconsHtml(apps) {
  const items = Array.isArray(apps) ? apps.filter((app) => app && (app.bundle_id || app.name)) : [];
  if (!items.length) return "";
  const shown = items.slice(0, 3);
  const extra = items.length - shown.length;
  const allNames = items.map(appName).join(", ");
  return `<span class="app-icons">${shown.map(appIconHtml).join("")}${
    extra > 0
      ? `<span class="app-icon-more has-tip" data-name="${escapeHtml(allNames)}" aria-label="${escapeHtml(allNames)}">+${extra}</span>`
      : ""
  }</span>`;
}

async function loadInstalledApps() {
  if (installedApps.length && Date.now() - installedAppsAt < 60000) return installedApps;
  try {
    const data = await api("/api/apps");
    installedApps = data.apps || [];
    installedAppsAt = Date.now();
  } catch (_err) {
    installedApps = [];
  }
  return installedApps;
}

function worksInHtml(assigned) {
  editorApps = Array.isArray(assigned)
    ? assigned.map(normalizeApp).filter(Boolean)
    : [];
  return field(
    "Works in",
    `<div id="works-in">
      <div class="works-in-search">
        <div class="field-row">
          <input id="works-in-query" type="search" placeholder="${editorApps.length ? "add an app" : "all apps"}" autocomplete="off" />
          <button type="button" class="ghost" id="pick-works-in">Browse</button>
        </div>
        <div id="works-in-suggest" class="works-in-suggest hidden"></div>
      </div>
      <div id="works-in-chips" class="works-in-chips"></div>
    </div>`
  );
}

function launchAppHtml(initial) {
  const seed = isSlotTemplate(initial) ? initial : "";
  return field(
    "App",
    `<div id="launch-app">
      <div id="launch-app-chip" class="works-in-chips"></div>
      <div class="works-in-search">
        <div class="field-row">
          <input id="launch-app-query" type="search" placeholder="search apps or {1}" value="${escapeHtml(seed)}" autocomplete="off" />
          <button type="button" class="ghost" id="pick-app">Browse</button>
        </div>
        <div id="launch-app-suggest" class="works-in-suggest hidden"></div>
      </div>
    </div>`
  );
}

function renderWorksInChips() {
  const box = $("#works-in-chips");
  const query = $("#works-in-query");
  if (query) query.placeholder = editorApps.length ? "add an app" : "all apps";
  if (!box) return;
  if (!editorApps.length) {
    box.innerHTML = "";
    return;
  }
  box.innerHTML = editorApps
    .map((app, index) => {
      const name = appName(app);
      return `<button type="button" class="app-chip has-tip" data-remove-app="${index}" data-name="${escapeHtml(name)}" aria-label="Remove ${escapeHtml(name)}">${appIconHtml(app)}<span aria-hidden="true">×</span></button>`;
    })
    .join("");
}

function renderLaunchAppChip() {
  const box = $("#launch-app-chip");
  if (!box) return;
  if (!editorLaunchApp) {
    box.innerHTML = "";
    return;
  }
  const name = appName(editorLaunchApp);
  box.innerHTML = `<button type="button" class="app-chip has-tip" data-clear-launch data-name="${escapeHtml(name)}" aria-label="Clear ${escapeHtml(name)}">${appIconHtml(editorLaunchApp)}<em>${escapeHtml(name)}</em><span aria-hidden="true">×</span></button>`;
}

function addWorksInApp(app) {
  const next = normalizeApp(app);
  if (!next) return;
  const key = appKey(next);
  if (editorApps.some((item) => appKey(item) === key)) return;
  if (editorApps.length >= 12) {
    toast("12 apps max.", "error");
    return;
  }
  editorApps.push(next);
  renderWorksInChips();
}

function setLaunchApp(app) {
  editorLaunchApp = normalizeApp(app);
  renderLaunchAppChip();
}

function hideSuggestBox(suggest) {
  if (!suggest) return;
  suggest.classList.add("hidden");
  suggest.innerHTML = "";
}

function bindAppTypeahead(query, suggest, excludeKeys, onPick, allowTyped) {
  if (!query || !suggest) return;
  const hide = () => hideSuggestBox(suggest);
  const show = async () => {
    const q = query.value.trim().toLowerCase();
    if (!q) {
      hide();
      return;
    }
    const apps = await loadInstalledApps();
    const assigned = new Set(excludeKeys());
    const hits = apps
      .filter((app) => {
        if (assigned.has(appKey(app))) return false;
        return `${app.name || ""} ${app.bundle_id || ""}`.toLowerCase().includes(q);
      })
      .slice(0, 8);
    if (!hits.length) {
      hide();
      return;
    }
    suggest.innerHTML = hits
      .map(
        (app, index) =>
          `<button type="button" class="works-in-option" data-suggest="${index}">${appIconHtml(app)}<span>${escapeHtml(appName(app))}</span></button>`
      )
      .join("");
    suggest.classList.remove("hidden");
    suggest.querySelectorAll("[data-suggest]").forEach((btn) => {
      btn.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        onPick(hits[Number(btn.dataset.suggest)]);
        query.value = "";
        hide();
      });
    });
  };
  query.addEventListener("input", () => {
    show().catch(() => {});
  });
  query.addEventListener("focus", () => {
    show().catch(() => {});
  });
  query.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      hide();
      return;
    }
    if (event.key !== "Enter") return;
    event.preventDefault();
    const first = suggest.querySelector("[data-suggest]");
    if (first) {
      first.click();
      return;
    }
    const typed = query.value.trim();
    if (allowTyped && typed) {
      onPick({ bundle_id: looksLikeBundleId(typed) ? typed : "", name: typed });
      query.value = "";
      hide();
    }
  });
}

async function resolveAppName(app) {
  const next = normalizeApp(app);
  if (!next) return null;
  if (next.name && !looksLikeBundleId(next.name)) return next;
  if (!next.bundle_id) return next;
  const apps = await loadInstalledApps();
  const hit = apps.find((item) => item.bundle_id === next.bundle_id);
  if (hit && hit.name) return { bundle_id: next.bundle_id, name: hit.name };
  return next;
}

function bindWorksInPicker() {
  const query = $("#works-in-query");
  const suggest = $("#works-in-suggest");
  if (!query) return;
  renderWorksInChips();
  loadInstalledApps().catch(() => {});
  $("#works-in-chips")?.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-remove-app]");
    if (!btn) return;
    event.preventDefault();
    editorApps.splice(Number(btn.dataset.removeApp), 1);
    renderWorksInChips();
  });
  $("#pick-works-in")?.addEventListener("click", async () => {
    try {
      const result = await api("/api/pick-app", { method: "POST" });
      if (result && (result.bundle_id || result.name)) addWorksInApp(result);
    } catch (err) {
      toast(err.message, "error");
    }
  });
  bindAppTypeahead(
    query,
    suggest,
    () => editorApps.map(appKey),
    (app) => addWorksInApp(app),
    false
  );
}

function bindLaunchAppPicker() {
  const query = $("#launch-app-query");
  const suggest = $("#launch-app-suggest");
  if (!query) return;
  renderLaunchAppChip();
  loadInstalledApps()
    .then(async () => {
      if (!editorLaunchApp) return;
      editorLaunchApp = await resolveAppName(editorLaunchApp);
      renderLaunchAppChip();
    })
    .catch(() => {});
  $("#launch-app-chip")?.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-clear-launch]");
    if (!btn) return;
    event.preventDefault();
    editorLaunchApp = null;
    renderLaunchAppChip();
  });
  $("#pick-app")?.addEventListener("click", async () => {
    try {
      const result = await api("/api/pick-app", { method: "POST" });
      if (result && (result.bundle_id || result.name)) setLaunchApp(result);
    } catch (err) {
      toast(err.message, "error");
    }
  });
  bindAppTypeahead(
    query,
    suggest,
    () => (editorLaunchApp ? [appKey(editorLaunchApp)] : []),
    (app) => setLaunchApp(app),
    true
  );
}

function readAppsAssignment() {
  return editorApps.map((app) => ({ bundle_id: app.bundle_id || "", name: app.name || "" }));
}

function devicePickerHtml(assigned) {
  const devices = settings.devices || [];
  const ids = Array.isArray(assigned) ? assigned.filter(Boolean) : [];
  const thisId = settings.device?.id;
  let selected = "";
  if (ids.length === 1) selected = ids[0];
  else if (ids.length > 1) {
    selected = devices.find((device) => ids.includes(device.id))?.id || "";
  }
  const optionsHtml = [
    `<option value="" ${selected ? "" : "selected"}>All devices</option>`,
    ...devices.map((device) => {
      const label = device.id === thisId ? `${device.name} (this Mac)` : device.name;
      return `<option value="${escapeHtml(device.id)}" ${device.id === selected ? "selected" : ""}>${escapeHtml(label)}</option>`;
    }),
  ].join("");
  return field("Devices", `<select id="device-select">${optionsHtml}</select>`);
}

function readDeviceAssignment() {
  const select = $("#device-select");
  if (!select || !select.value) return [];
  return [select.value];
}

function isoNow() {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}

function openCommandEditor(index) {
  stopRecording();
  editorMode = "command";
  editorIndex = index;
  const cmd =
    index >= 0
      ? { ...library.commands[index] }
      : { type: "keyboard", name: "", phrases: [], keys: [], url: "", app: "", path: "", body: "", runtime: "bash", text: "" };
  recordedKeys = Array.isArray(cmd.keys) ? cmd.keys.map((step) => ({ ...step })) : [];
  editorLaunchApp = isSlotTemplate(cmd.app || cmd.bundle_id)
    ? null
    : normalizeApp({
        bundle_id: cmd.bundle_id || (looksLikeBundleId(cmd.app) ? cmd.app : ""),
        name: cmd.app || cmd.bundle_id || "",
      });
  $("#editor-title").textContent = index >= 0 ? "edit command" : "new command";
  $("#editor-delete").classList.toggle("hidden", index < 0);
  $("#editor-body").innerHTML = `
    <div class="form-stack">
      ${field("Name", `<input name="name" required placeholder="Save" value="${escapeHtml(cmd.name || "")}" />`)}
      ${field(
        "Say",
        `<input name="phrases" placeholder="open {1}, insert {hello}" value="${escapeHtml((cmd.phrases || []).join(", "))}" />`
      )}
      ${field(
        "Type",
        `<div class="type-picks" id="type-picks">${TYPES.map(
          (type) =>
            `<button type="button" data-type="${type}" class="${type === (cmd.type || "keyboard") ? "active" : ""}">${TYPE_LABEL[type]}</button>`
        ).join("")}</div><input type="hidden" name="type" value="${escapeHtml(cmd.type || "keyboard")}" />`
      )}
      <div id="type-fields"></div>
      ${worksInHtml(cmd.apps)}
      ${devicePickerHtml(cmd.devices)}
      ${secretSwitchHtml(cmd.secret)}
    </div>
  `;
  const typeInput = $("#editor-body [name=type]");
  const renderFields = () => {
    stopRecording();
    const type = typeInput.value;
    const box = $("#type-fields");
    if (type === "keyboard") {
      box.innerHTML = field(
        "Keys",
        `<div id="keys-box" class="keys-box">
          <div id="key-chips"></div>
          <div class="field-row">
            <button type="button" class="ghost record-btn" id="record-keys" aria-pressed="false"><span class="rec-dot" aria-hidden="true"></span>Record</button>
            <button type="button" class="ghost" id="clear-keys">Clear</button>
          </div>
        </div>`
      );
      renderKeyChips();
      bindKeyRecorder();
    } else if (type === "website") {
      box.innerHTML = field("URL", `<input name="url" placeholder="https://" value="${escapeHtml(cmd.url || "")}" />`);
    } else if (type === "app") {
      box.innerHTML = launchAppHtml(cmd.app || cmd.bundle_id || "");
      bindLaunchAppPicker();
    } else if (type === "file") {
      box.innerHTML = field(
        "Path",
        `<span class="field-row">
          <input name="path" value="${escapeHtml(cmd.path || "")}" />
          <button type="button" class="ghost" id="pick-path">Browse</button>
        </span>`
      );
      $("#pick-path").addEventListener("click", browsePath("[name=path]"));
    } else if (type === "script") {
      const runtime = cmd.runtime || "bash";
      box.innerHTML = `
        ${field(
          "Kind",
          `<div class="type-picks" id="runtime-picks">
            <button type="button" data-runtime="bash" class="${runtime === "bash" ? "active" : ""}">Bash</button>
            <button type="button" data-runtime="applescript" class="${runtime === "applescript" ? "active" : ""}">AppleScript</button>
          </div>
          <input type="hidden" name="runtime" value="${escapeHtml(runtime)}" />`
        )}
        ${field(
          "Script",
          `<textarea name="body" rows="8" placeholder="Script">${escapeHtml(cmd.body || "")}</textarea>
           <span class="field-row" style="margin-top:8px">
             <input name="path" placeholder="File" value="${escapeHtml(cmd.path || "")}" />
             <button type="button" class="ghost" id="pick-script">Browse</button>
           </span>`
        )}
      `;
      $("#runtime-picks").addEventListener("click", (event) => {
        const btn = event.target.closest("[data-runtime]");
        if (!btn) return;
        $("[name=runtime]").value = btn.dataset.runtime;
        $("#runtime-picks").querySelectorAll("button").forEach((el) => el.classList.toggle("active", el === btn));
      });
      $("#pick-script").addEventListener("click", async () => {
        try {
          const result = await api("/api/pick-path", { method: "POST" });
          if (!result.path) return;
          $("[name=path]").value = result.path;
          const lower = result.path.toLowerCase();
          const runtimeValue = lower.endsWith(".applescript") || lower.endsWith(".scpt") ? "applescript" : "bash";
          $("[name=runtime]").value = runtimeValue;
          $("#runtime-picks").querySelectorAll("button").forEach((el) => {
            el.classList.toggle("active", el.dataset.runtime === runtimeValue);
          });
        } catch (err) {
          toast(err.message);
        }
      });
    } else if (type === "text") {
      box.innerHTML = field(
        "Text",
        `<textarea name="text" rows="4" placeholder="{*}">${escapeHtml(cmd.text || "")}</textarea>`
      );
    } else {
      box.innerHTML = field(
        "Action",
        `<select name="action">${options(SYSTEM_ACTIONS, cmd.action || "mute")}</select>`
      );
    }
  };
  $("#type-picks").addEventListener("click", (event) => {
    const btn = event.target.closest("[data-type]");
    if (!btn) return;
    typeInput.value = btn.dataset.type;
    $("#type-picks").querySelectorAll("button").forEach((el) => el.classList.toggle("active", el === btn));
    renderFields();
  });
  renderFields();
  bindWorksInPicker();
  bindSecretSwitch();
  $("#editor").showModal();
}

function openRoutineEditor(index) {
  editorMode = "routine";
  editorIndex = index;
  const rtn =
    index >= 0
      ? JSON.parse(JSON.stringify(library.routines[index]))
      : { name: "", phrases: [], steps: [{ command_id: library.commands[0]?.id || "", delay_ms: 0 }] };
  $("#editor-title").textContent = index >= 0 ? "edit routine" : "new routine";
  $("#editor-delete").classList.toggle("hidden", index < 0);
  const cmdOptions = library.commands.map((c) => [c.id, `${c.name} (${TYPE_LABEL[c.type]})`]);
  const stepHtml = (step) => `
    <div class="step">
      <select name="command_id">${options(cmdOptions, step.command_id)}</select>
      <input name="delay_ms" type="number" min="0" step="50" value="${Number(step.delay_ms || 0)}" title="Delay (ms)" />
      <button type="button" class="up">Up</button>
      <button type="button" class="remove">Remove</button>
    </div>`;
  $("#editor-body").innerHTML = `
    <label>Name<input name="name" required value="${escapeHtml(rtn.name || "")}" /></label>
    <label>Aliases
      <input name="phrases" value="${escapeHtml((rtn.phrases || []).join(", "))}" placeholder="optional" />
    </label>
    <div class="field">
      <span class="field-label">steps</span>
      <div class="field-control">
        <button type="button" class="icon-btn icon-plus" id="add-step" aria-label="Add step">+</button>
        <div id="steps">${(rtn.steps || []).map(stepHtml).join("")}</div>
      </div>
    </div>
    ${devicePickerHtml(rtn.devices)}
    ${secretSwitchHtml(rtn.secret)}
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
  bindSecretSwitch();
  $("#editor").showModal();
}

function secretSwitchHtml(on) {
  const enabled = Boolean(settings.lock?.enabled);
  const pressed = Boolean(on) && enabled;
  return `<div class="motion-switch">
      <button type="button" class="switch" id="item-secret" aria-pressed="${pressed ? "true" : "false"}" ${enabled ? "" : "disabled"} aria-label="Secret"><i></i></button>
      <span>secret</span>
    </div>`;
}

function bindSecretSwitch() {
  $("#item-secret")?.addEventListener("click", (event) => {
    const btn = event.currentTarget;
    if (btn.disabled) return;
    const next = btn.getAttribute("aria-pressed") !== "true";
    btn.setAttribute("aria-pressed", next ? "true" : "false");
  });
}

function readSecretFlag() {
  return $("#item-secret")?.getAttribute("aria-pressed") === "true";
}

function parsePhrases(raw) {
  return raw
    .split(",")
    .map((p) => p.trim())
    .filter(Boolean);
}

async function saveEditor(event) {
  event.preventDefault();
  const body = $("#editor-body");
  if (editorMode === "command") {
    const type = body.querySelector("[name=type]").value;
    const next = {
      id: editorIndex >= 0 ? library.commands[editorIndex].id : undefined,
      type,
      name: body.querySelector("[name=name]").value.trim(),
      phrases: parsePhrases(body.querySelector("[name=phrases]").value),
      devices: readDeviceAssignment(),
      apps: readAppsAssignment(),
      updated_at: isoNow(),
    };
    if (readSecretFlag()) {
      if (!settings.lock?.enabled) {
        toast("Set a lock first.");
        return;
      }
      next.secret = true;
    }
    if (type === "website") next.url = body.querySelector("[name=url]").value.trim();
    if (type === "app") {
      const typed = ($("#launch-app-query") && $("#launch-app-query").value.trim()) || "";
      if (isSlotTemplate(typed)) {
        next.app = typed;
      } else if (editorLaunchApp && (editorLaunchApp.bundle_id || editorLaunchApp.name)) {
        next.app = editorLaunchApp.name || "";
        if (editorLaunchApp.bundle_id) next.bundle_id = editorLaunchApp.bundle_id;
      } else if (typed) {
        next.app = typed;
      } else {
        toast("Choose an app.", "error");
        return;
      }
    }
    if (type === "file") next.path = body.querySelector("[name=path]").value.trim();
    if (type === "system") next.action = body.querySelector("[name=action]").value;
    if (type === "keyboard") {
      if (recordedKeys.length) next.keys = recordedKeys;
      else if (editorIndex >= 0 && library.commands[editorIndex].action) {
        next.action = library.commands[editorIndex].action;
      }
    }
    if (type === "script") {
      next.runtime = body.querySelector("[name=runtime]").value;
      next.body = body.querySelector("[name=body]").value;
      next.path = body.querySelector("[name=path]").value.trim();
    }
    if (type === "text") next.text = body.querySelector("[name=text]").value;
    const commands = library.commands.slice();
    if (editorIndex >= 0) commands[editorIndex] = next;
    else commands.push(next);
    await persist({ ...library, commands });
  } else if (editorMode === "routine") {
    const steps = [...body.querySelectorAll(".step")].map((row) => ({
      command_id: row.querySelector("[name=command_id]").value,
      delay_ms: Number(row.querySelector("[name=delay_ms]").value || 0),
    }));
    const next = {
      id: editorIndex >= 0 ? library.routines[editorIndex].id : undefined,
      name: body.querySelector("[name=name]").value.trim(),
      phrases: parsePhrases(body.querySelector("[name=phrases]").value),
      steps,
      devices: readDeviceAssignment(),
      updated_at: isoNow(),
    };
    if (readSecretFlag()) {
      if (!settings.lock?.enabled) {
        toast("Set a lock first.");
        return;
      }
      next.secret = true;
    }
    const routines = library.routines.slice();
    if (editorIndex >= 0) routines[editorIndex] = next;
    else routines.push(next);
    await persist({ ...library, routines });
  } else if (editorMode === "variable") {
    const next = {
      id: editorIndex >= 0 ? (library.variables || [])[editorIndex]?.id : undefined,
      name: body.querySelector("[name=name]").value.trim(),
      value: body.querySelector("[name=value]").value,
      updated_at: isoNow(),
    };
    if (readSecretFlag()) {
      if (!settings.lock?.enabled) {
        toast("Set a lock first.");
        return;
      }
      next.secret = true;
    }
    const variables = (library.variables || []).slice();
    if (editorIndex >= 0) variables[editorIndex] = next;
    else variables.push(next);
    await persist({ ...library, variables });
  }
  stopRecording();
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
    await persist({ ...library, commands, routines });
  } else if (editorMode === "routine" && editorIndex >= 0) {
    const routines = library.routines.filter((_, i) => i !== editorIndex);
    await persist({ ...library, routines });
  } else if (editorMode === "variable" && editorIndex >= 0) {
    const variables = (library.variables || []).filter((_, i) => i !== editorIndex);
    await persist({ ...library, variables });
  }
  stopRecording();
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
  renderVoice();
  renderLibrary($("#chart-library"));
  toast("Saved");
}

function showView(name) {
  document.querySelectorAll(".view").forEach((el) => el.classList.add("hidden"));
  $(`#view-${name}`).classList.remove("hidden");
  document.querySelectorAll("nav button").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === name);
  });
  pulseNav(name);
  if (name === "overview") playOverviewMotion();
}

function pulsePress(el) {
  if (!el || motionReduced()) return;
  el.classList.remove("is-press");
  void el.offsetWidth;
  el.classList.add("is-press");
}

function pulseNav(name) {
  pulsePress(document.querySelector(`nav button[data-view="${name}"]`));
}

function bindPressFeedback() {
  document.addEventListener("click", (event) => {
    const btn = event.target.closest("button");
    if (!btn || btn.disabled || btn.getAttribute("aria-disabled") === "true") return;
    if (btn.id === "wordmark-pulse") return;
    if (btn.classList.contains("switch") || btn.classList.contains("swatch")) return;
    if (btn.classList.contains("primary") || btn.classList.contains("accent-btn") || btn.classList.contains("danger")) return;
    pulsePress(btn);
  });
}

function pulseWordmark() {
  const wordmark = $("#wordmark-pulse");
  if (!wordmark || document.documentElement.dataset.reduceMotion === "true") return;
  wordmark.classList.remove("is-press");
  void wordmark.offsetWidth;
  wordmark.classList.add("is-press");
}

function editorOpen() {
  return Boolean($("#editor") && $("#editor").open);
}

async function refreshStats() {
  if (editorOpen() || lockBlocks()) return;
  const [lib, stats] = await Promise.all([api("/api/library"), api(statsUrl())]);
  if (editorOpen()) return;
  library = lib;
  renderStats(stats);
}

async function refresh({ pull = false } = {}) {
  if (editorOpen() || settingsOpen() || lockBlocks()) return;
  if (pull) {
    try {
      await api("/api/sync/pull", { method: "POST" });
    } catch (_err) {
      try {
        applySettingsAttention((await api("/api/sync/status")).sync);
      } catch {
        /* keep the page usable if the cloud copy cannot be reached */
      }
    }
  }
  const [lib, stats, prefs] = await Promise.all([
    api("/api/library"),
    api(statsUrl()),
    api("/api/settings"),
  ]);
  if (editorOpen() || settingsOpen()) return;
  library = lib;
  mergeSettings(prefs);
  renderCommands();
  renderRoutines();
  renderVoice();
  renderStats(stats);
  renderPersonalization();
}

function startAutoRefresh() {
  if (autoRefreshStarted) return;
  autoRefreshStarted = true;
  let lastCloud = Date.now();
  const tickStats = () => {
    if (document.hidden || editorOpen() || lockBlocks()) return;
    refreshStats().catch((err) => toast(err.message));
    if (settingsOpen()) return;
    const now = Date.now();
    if (now - lastCloud < CLOUD_MS) return;
    lastCloud = now;
    refresh({ pull: true }).catch((err) => toast(err.message));
  };
  setInterval(tickStats, STATS_MS);
  const onActivate = () => {
    if (document.hidden || editorOpen() || lockBlocks()) return;
    refreshStats().catch((err) => toast(err.message));
  };
  document.addEventListener("visibilitychange", onActivate);
  window.addEventListener("focus", onActivate);
}

async function boot() {
  bindLockUi();
  bindPressFeedback();
  $("#wordmark-pulse")?.addEventListener("click", pulseWordmark);
  document.querySelectorAll("nav button").forEach((btn) => {
    btn.addEventListener("click", () => showView(btn.dataset.view));
  });
  $("#refresh-stats")?.addEventListener("click", () => {
    refreshStats()
      .then(() => {
        playOverviewMotion({ force: true });
        toast("Stats updated");
      })
      .catch((err) => toast(err.message));
  });
  $("#add-command").addEventListener("click", () => openCommandEditor(-1));
  $("#add-routine").addEventListener("click", () => openRoutineEditor(-1));
  $("#add-voice")?.addEventListener("click", () => openVoiceEditor(-1));
  $("#editor-cancel").addEventListener("click", () => {
    stopRecording();
    $("#editor").close();
  });
  $("#editor-delete").addEventListener("click", () => deleteCurrent());
  $("#editor-form").addEventListener("submit", (event) => {
    saveEditor(event).catch((err) => toast(err.message));
  });
  $("#editor-form").addEventListener("keydown", (event) => {
    if (recording && event.key === "Enter") event.preventDefault();
  });
  $("#command-search").addEventListener("input", (event) => {
    commandQuery = event.target.value;
    renderCommands();
  });
  $("#voice-search")?.addEventListener("input", (event) => {
    voiceQuery = event.target.value;
    renderVoice();
  });
  $("#activity-search").addEventListener("input", (event) => {
    activityQuery = event.target.value;
    renderActivity();
  });
  $("#command-filters").addEventListener("click", (event) => {
    const btn = event.target.closest("[data-filter]");
    if (!btn) return;
    commandFilter = btn.dataset.filter;
    $("#command-filters").querySelectorAll("button").forEach((el) => {
      el.classList.toggle("active", el === btn);
    });
    renderCommands();
  });
  bindCharts();
  bindSettings();
  window.matchMedia("(prefers-reduced-motion: reduce)").addEventListener("change", () => {
    applyAppearance(settings);
    if (motionReduced()) {
      clearOverviewFill();
      if (lastStats) setMeterValues(lastStats, false);
    }
  });
  try {
    applyLock(await api("/api/lock/status"));
    if (lockBlocks()) {
      const ok = await ensureUnlock();
      if (!ok) return;
    }
    await finishBoot();
  } catch (err) {
    toast(err.message);
  }
}

async function finishBoot() {
  if (appBooted) return;
  appBooted = true;
  try {
    await refresh({ pull: true });
    renderAccount();
    playOverviewMotion({ force: true });
  } catch (err) {
    toast(err.message);
  }
  startAutoRefresh();
}

function renderPersonalization() {
  $("#theme-picks").querySelectorAll("button").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.theme === settings.theme);
  });
  const accents = settings.accents || ACCENTS;
  $("#accent-swatches").innerHTML = accents
    .map(
      (id) =>
        `<button type="button" class="swatch${id === settings.accent ? " active" : ""}" data-accent="${id}" aria-label="${id}"></button>`
    )
    .join("");
  const zones = settings.timezones || [{ id: "local", label: "This Mac" }];
  $("#timezone-select").innerHTML = zones
    .map(
      (zone) =>
        `<option value="${escapeHtml(zone.id)}"${zone.id === settings.timezone ? " selected" : ""}>${escapeHtml(zone.label)}</option>`
    )
    .join("");
  const reduce = $("#reduce-motion");
  if (reduce) reduce.setAttribute("aria-pressed", settings.reduce_motion ? "true" : "false");
}

function applyModelState(data) {
  if (!data) return;
  modelState = {
    model: data.model || modelState.model,
    active: data.active || data.model || modelState.active,
    status: data.status || "ready",
    error: data.error || "",
    models: data.models || modelState.models || settings.models || [],
  };
  settings.model = modelState.model;
  if (data.models) settings.models = data.models;
  renderModel();
}

function modelPaneOpen() {
  return Boolean($("#settings")?.open && !$("#pane-model")?.classList.contains("hidden"));
}

function modelPickHtml(item, selected) {
  const id = item.id || item;
  const label = item.label || id;
  const hint = item.custom ? "custom" : item.hint || "";
  const active = id === selected ? " active" : "";
  const remove = item.custom
    ? `<span class="model-remove" data-remove-model="${escapeHtml(id)}" aria-label="Remove">×</span>`
    : "";
  return `<button type="button" class="model-pick${active}" data-model="${escapeHtml(id)}"><strong>${escapeHtml(label)}</strong>${
    hint ? `<span>${escapeHtml(hint)}</span>` : ""
  }${remove}</button>`;
}

function renderModel() {
  const builtin = $("#model-builtin");
  const custom = $("#model-custom");
  const status = $("#model-status");
  const models = modelState.models.length ? modelState.models : settings.models || [];
  const selected = modelState.model || settings.model;
  if (builtin) {
    builtin.innerHTML = models.filter((item) => !item.custom).map((item) => modelPickHtml(item, selected)).join("");
  }
  if (custom) {
    custom.innerHTML = models.filter((item) => item.custom).map((item) => modelPickHtml(item, selected)).join("");
  }
  renderModelAddForm();
  if (status) {
    if (modelState.status === "loading") status.textContent = "loading";
    else if (modelState.status === "error") status.textContent = modelState.error || "Could not load model.";
    else status.textContent = "";
  }
}

function renderModelAddForm() {
  const form = $("#model-add-form");
  const add = $("#add-custom-model");
  if (form) form.classList.toggle("hidden", !modelAddOpen);
  if (add) {
    add.textContent = modelAddOpen ? "×" : "+";
    add.setAttribute("aria-label", modelAddOpen ? "Cancel add model" : "Add custom model");
  }
}

function submitCustomModel() {
  const path = ($("#custom-model-path")?.value || "").trim();
  const name = ($("#custom-model-name")?.value || "").trim();
  if (!path) {
    toast("Choose a model folder.", "error");
    return;
  }
  addCustomModel(path, name).catch((err) => toast(err.message, "error"));
}

async function refreshModel() {
  applyModelState(await api("/api/model"));
}

function applyModelTest(data) {
  const box = $("#model-test");
  const hint = $("#model-test-hint");
  if (!data) return;
  const incoming = data.text || "";
  if (box && incoming !== lastModelTest) {
    if (incoming.startsWith(lastModelTest)) box.value += incoming.slice(lastModelTest.length);
    else box.value = incoming;
    lastModelTest = incoming;
  }
  if (box) box.classList.toggle("is-listening", data.phase === "recording");
  if (hint) {
    if (data.phase === "recording") hint.textContent = "listening";
    else if (data.phase === "busy") hint.textContent = "transcribing";
    else hint.innerHTML = "hold <kbd>fn</kbd>";
  }
}

async function refreshModelTest() {
  try {
    applyModelTest(await api("/api/model/test"));
  } catch {
    /* endpoint missing until the app is restarted */
  }
}

function syncModelTest(on) {
  if (on) {
    api("/api/model/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ listen: true }),
    })
      .then(applyModelTest)
      .catch(() => {});
    pollModel();
    return;
  }
  modelPoll += 1;
  api("/api/model/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ listen: false }),
  }).catch(() => {});
}

function pollModel() {
  const gen = ++modelPoll;
  const tick = () => {
    if (gen !== modelPoll) return;
    if (!$("#settings")?.open) return;
    const testing = modelPaneOpen();
    const loading = modelState.status === "loading";
    Promise.all([refreshModel(), testing ? refreshModelTest() : Promise.resolve()])
      .then(() => {
        if (gen !== modelPoll) return;
        if (loading || modelState.status === "loading" || modelPaneOpen()) {
          setTimeout(tick, modelState.status === "loading" ? 700 : 450);
        }
      })
      .catch((err) => toast(err.message, "error"));
  };
  setTimeout(tick, 300);
}

async function saveModel(id) {
  const data = await api("/api/model", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model: id }),
  });
  applyModelState(data);
  if (modelState.status === "loading") pollModel();
}

async function addCustomModel(path, name) {
  const data = await api("/api/model/custom", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, name }),
  });
  applyModelState(data);
  const pathInput = $("#custom-model-path");
  const nameInput = $("#custom-model-name");
  if (pathInput) pathInput.value = "";
  if (nameInput) nameInput.value = "";
  modelAddOpen = false;
  renderModelAddForm();
  if (modelState.status === "loading") pollModel();
}

async function removeCustomModel(id) {
  const data = await api("/api/model/custom/remove", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
  applyModelState(data);
  if (modelState.status === "loading") pollModel();
}

function renderAccount() {
  const username = $("#account-username");
  const deviceName = $("#account-device-name");
  if (username && document.activeElement !== username) {
    username.value = settings.username || "";
  }
  if (deviceName && document.activeElement !== deviceName) {
    deviceName.value = settings.device?.name || "";
  }
  const serial = $("#account-device-serial");
  if (serial) serial.value = settings.device?.serial || settings.device?.id || "";
  const priv = $("#private-mode");
  if (priv) priv.setAttribute("aria-pressed", settings.private_mode ? "true" : "false");
  renderLockFields();
  const list = $("#device-list");
  if (!list) return;
  const devices = settings.devices || [];
  const thisId = settings.device?.id;
  if (!devices.length) {
    list.innerHTML = `<li class="empty">None</li>`;
    return;
  }
  list.innerHTML = devices
    .map((device) => {
      const tag = device.id === thisId ? "this Mac" : "synced";
      const serialText = device.serial || device.id || "";
      return `<li><span>${escapeHtml(device.name || "Mac")} <span class="tag">${tag}</span></span><span class="serial">${escapeHtml(serialText)}</span></li>`;
    })
    .join("");
}

function syncDraft() {
  const current = settings.sync || {};
  const what = current.what || { library: true, stats: false };
  return {
    provider: ($("#sync-provider") && $("#sync-provider").value) || current.provider || "aws",
    bucket: ($("#sync-bucket") && $("#sync-bucket").value) || current.bucket || "",
    prefix: ($("#sync-prefix") && $("#sync-prefix").value) || current.prefix || "",
    account: ($("#sync-account") && $("#sync-account").value) || current.account || "",
    project: ($("#sync-project") && $("#sync-project").value) || current.project || "",
    keychain_scope:
      document.querySelector("#scope-picks button.active")?.dataset.scope ||
      settings.keychain_scope ||
      "local",
    what: {
      library: chipOn($("#sync-what-library"), what.library !== false),
      stats: chipOn($("#sync-what-stats"), Boolean(what.stats)),
    },
  };
}

function syncDestinationPayload(extra) {
  const sync = settings.sync || {};
  const what = sync.what || { library: true, stats: false };
  return {
    provider: sync.provider,
    bucket: sync.bucket,
    prefix: sync.prefix || "",
    account: sync.account || "",
    project: sync.project || "",
    keychain_scope: settings.keychain_scope || "local",
    what: { library: what.library !== false, stats: Boolean(what.stats) },
    ...extra,
  };
}

function chipOn(el, fallback) {
  if (!el) return fallback;
  return el.getAttribute("aria-pressed") === "true";
}

function validateSyncDraft(draft) {
  const info = (settings.providers || {})[draft.provider] || {};
  if (info.available === false) return info.message || "That cloud isn’t available on this Mac.";
  if (!(draft.bucket || "").trim()) return "Bucket required.";
  if (draft.provider === "azure" && !(draft.account || "").trim()) {
    return "Storage account required.";
  }
  return "";
}

function syncStep() {
  const sync = settings.sync || {};
  if (pendingPrivateKey) return "key";
  if (syncWizard === "destination") return "destination";
  if (Boolean(sync.needs_key) && !pendingPrivateKey) return "join";
  if (Boolean(sync.needs_create) && !pendingPrivateKey) return "create";
  if (sync.enabled || (sync.bucket || "").trim()) return "live";
  return "idle";
}

function syncIntervalOptions(current) {
  const allowed = settings.sync_intervals || [0, 300, 900, 1800, 3600];
  const value = allowed.includes(Number(current)) ? Number(current) : 900;
  return allowed
    .map((sec) => {
      const label = SYNC_INTERVAL_LABEL[sec] || `${sec / 60} minutes`;
      return `<option value="${sec}" ${sec === value ? "selected" : ""}>${label}</option>`;
    })
    .join("");
}

function renderSync(data) {
  if (data) mergeSettings(data);
  renderAccount();
  const sync = settings.sync || {};
  const providers = settings.providers || {};
  const what = (sync.what || { library: true, stats: false });
  const draft = {
    provider: sync.provider || "aws",
    bucket: sync.bucket || "",
    prefix: sync.prefix || "",
    account: sync.account || "",
    project: sync.project || "",
    keychain_scope: settings.keychain_scope || "local",
    what: { library: what.library !== false, stats: Boolean(what.stats) },
  };
  const existing = $("#sync-body");
  const step = syncStep();
  const editing = step === "destination" || (step === "live" && (syncEditing || syncEnableAfterSave));
  if (editing && existing && $("#sync-bucket")) {
    draft.provider = $("#sync-provider")?.value || draft.provider;
    draft.bucket = $("#sync-bucket").value;
    draft.prefix = $("#sync-prefix").value;
    draft.account = $("#sync-account")?.value || draft.account;
    draft.project = $("#sync-project")?.value || draft.project;
    if ($("#sync-what-library")) draft.what.library = chipOn($("#sync-what-library"), draft.what.library);
    if ($("#sync-what-stats")) draft.what.stats = chipOn($("#sync-what-stats"), draft.what.stats);
    const scopeBtn = document.querySelector("#scope-picks button.active");
    if (scopeBtn?.dataset.scope) draft.keychain_scope = scopeBtn.dataset.scope;
  }
  const providerIds = ["aws", "gcs", "azure"];
  const noneReady = providerIds.every((id) => (providers[id] || {}).available === false);
  const firstReady = providerIds.find((id) => (providers[id] || {}).available !== false);
  if ((providers[draft.provider] || {}).available === false && firstReady) {
    draft.provider = firstReady;
  }
  const selected = providers[draft.provider] || {};
  const canUse = selected.available !== false;
  const configured = Boolean((sync.bucket || "").trim());
  const switchOn = Boolean(sync.enabled) || Boolean(syncEnableAfterSave);
  const keyText = pendingPrivateKey || revealedKey;
  const error = sync.last_error;
  const phase =
    step === "key"
      ? "wait"
      : step === "create"
        ? "create"
        : step === "join"
          ? "key"
          : step === "destination"
            ? "setup"
            : sync.enabled
              ? "on"
              : "off";
  const phaseLabel =
    phase === "on"
      ? "On"
      : phase === "wait"
        ? "Save your key"
        : phase === "create"
          ? "Username"
          : phase === "key"
            ? "Unlock"
            : phase === "setup"
              ? "Set up"
              : "Off";
  const phaseMeta =
    sync.enabled && sync.last_sync_at ? `Last synced ${formatTime(sync.last_sync_at)}` : "";
  const usernameValue = escapeHtml(settings.username || "");
  const providerOptions = providerIds
    .map((id) => {
      const info = providers[id] || {};
      const off = info.available === false;
      const note = off && info.message ? ` — ${info.message}` : "";
      return `<option value="${id}" ${draft.provider === id ? "selected" : ""} ${off ? "disabled" : ""}>${PROVIDER_LABEL[id]}${escapeHtml(note)}</option>`;
    })
    .join("");
  const destFields = `<label>Provider
          <select id="sync-provider">${providerOptions}</select>
        </label>
        <div class="sync-grid">
          <label>Bucket<input id="sync-bucket" type="text" value="${escapeHtml(draft.bucket)}" placeholder="my-bucket" autocomplete="off" /></label>
          <label>Folder<input id="sync-prefix" type="text" value="${escapeHtml(draft.prefix)}" placeholder="optional" autocomplete="off" /></label>
        </div>
        <label class="${draft.provider === "azure" ? "" : "hidden"}" id="azure-account-field">Storage account<input id="sync-account" type="text" value="${escapeHtml(draft.account)}" placeholder="mystorageacct" autocomplete="off" /></label>
        <label class="${draft.provider === "gcs" ? "" : "hidden"}" id="gcs-project-field">Project<input id="sync-project" type="text" value="${escapeHtml(draft.project)}" placeholder="optional" autocomplete="off" /></label>
        ${syncValidateError ? `<p class="sync-note sync-error">${escapeHtml(syncValidateError)}</p>` : ""}`;
  const saveLabel = step === "destination" ? "continue" : syncEnableAfterSave ? "Save and turn on" : "Save";
  let heroActions = "";
  if (step === "key") {
    heroActions = `<button type="button" class="primary" id="confirm-sync" ${savedKeyConfirm ? "" : "disabled"}>Start sync</button>`;
  } else if (step === "idle") {
    heroActions = `<button type="button" class="primary" id="sync-setup">setup</button>`;
  } else if (step === "live") {
    heroActions = `<div class="sync-hero-actions">
                <div class="sync-switch">
                  <button type="button" class="switch" id="sync-toggle" aria-pressed="${switchOn ? "true" : "false"}" ${sync.enabled || canUse ? "" : "disabled"} aria-label="Turn sync ${switchOn ? "off" : "on"}"><i></i></button>
                  <span>${switchOn ? "on" : "off"}</span>
                </div>
                <button type="button" class="ghost accent-btn" id="sync-now" ${sync.enabled ? "" : "disabled"}>sync now</button>
              </div>`;
  }
  let stepCard = "";
  if (step === "key") {
    stepCard = `<section class="sync-card sync-key-card">
              <h3>Private key</h3>
              <p class="sync-note">Username ${usernameValue || "—"}</p>
              <textarea class="key-box" id="sync-key-view" readonly>${escapeHtml(keyText)}</textarea>
              <div class="sync-actions">
                <button type="button" class="ghost" id="copy-key">Copy</button>
                <label class="choice tight"><input type="checkbox" id="saved-key" ${savedKeyConfirm ? "checked" : ""} /> I saved this key</label>
              </div>
            </section>`;
  } else if (step === "create") {
    stepCard = `<section class="sync-card sync-key-card">
                <h3>Username</h3>
                <div class="sync-id-fields">
                  <input id="sync-username" type="text" maxlength="40" value="${usernameValue}" placeholder="username" autocomplete="off" />
                </div>
                <div class="sync-actions">
                  <button type="button" class="primary" id="sync-create">Create</button>
                  <button type="button" id="sync-cancel">cancel</button>
                </div>
              </section>`;
  } else if (step === "join") {
    stepCard = `<section class="sync-card sync-key-card">
                  <h3>Unlock</h3>
                  <p class="sync-note">If this copy already has a name, that name replaces the one on this Mac.</p>
                  <div class="sync-id-fields">
                    <label>Username<input id="sync-username" type="text" maxlength="40" value="${usernameValue}" placeholder="username" autocomplete="off" /></label>
                    <label>Private key<textarea id="sync-private-key" class="key-box short" placeholder="Paste the private key"></textarea></label>
                  </div>
                  <div class="sync-actions">
                    <button type="button" class="primary" id="sync-join">Unlock</button>
                    <button type="button" id="sync-cancel">cancel</button>
                  </div>
                </section>`;
  }
  let objectCard = "";
  if (step === "destination") {
    objectCard = `<section class="sync-card sync-object is-editing">
        <header class="sync-card-head"><h3>Cloud</h3></header>
        ${destFields}
        <div class="sync-edit-actions">
            <button type="button" id="sync-cancel">cancel</button>
            <button type="button" class="primary" id="sync-save">${saveLabel}</button>
          </div>
      </section>`;
  } else if (step === "live") {
    objectCard = `<section class="sync-card sync-object ${editing ? "is-editing" : ""}">
        <header class="sync-card-head">
          <h3>Cloud</h3>
          ${
            editing
              ? ""
              : `<button type="button" class="ghost icon-btn with-label" id="sync-edit" aria-label="Edit sync">
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M11.2 2.3l2.5 2.5M3 13l3.1-.8 7.1-7.1-2.5-2.5L3.6 9.7 3 13z"/></svg>
            edit
          </button>`
          }
        </header>
        ${
          editing
            ? destFields
            : configured
              ? `<dl class="sync-facts">
            <div><dt>Provider</dt><dd>${escapeHtml(PROVIDER_LABEL[draft.provider] || draft.provider)}</dd></div>
            <div><dt>Bucket</dt><dd>${escapeHtml(draft.bucket)}</dd></div>
            <div><dt>Folder</dt><dd>${escapeHtml(draft.prefix || "—")}</dd></div>
            ${draft.provider === "azure" ? `<div><dt>Storage account</dt><dd>${escapeHtml(draft.account || "—")}</dd></div>` : ""}
            ${draft.provider === "gcs" && draft.project ? `<div><dt>Project</dt><dd>${escapeHtml(draft.project)}</dd></div>` : ""}
          </dl>`
              : `<p class="sync-note">No destination</p>`
        }
        <div class="sync-compact">
        <div class="sync-row">
          <span class="sync-label">interval</span>
          <select id="sync-interval">${syncIntervalOptions(sync.interval_sec)}</select>
        </div>
        <div class="sync-row">
          <span class="sync-label">include</span>
          <div class="sync-chips">
            ${
              editing
                ? `<button type="button" class="chip" id="sync-what-library" aria-pressed="${draft.what.library ? "true" : "false"}">commands</button>
            <button type="button" class="chip" id="sync-what-stats" aria-pressed="${draft.what.stats ? "true" : "false"}">stats</button>`
                : `<span class="chip ${draft.what.library ? "locked" : "idle"}">commands</span>
            <span class="chip ${draft.what.stats ? "locked" : "idle"}">stats</span>`
            }
          </div>
        </div>
        <div class="sync-row">
          <span class="sync-label">key</span>
          <div class="sync-key-row">
            ${
              editing
                ? `<div class="type-picks" id="scope-picks">
              <button type="button" data-scope="local" class="${draft.keychain_scope !== "icloud" ? "active" : ""}">This Mac</button>
              <button type="button" data-scope="icloud" class="${draft.keychain_scope === "icloud" ? "active" : ""}" ${settings.icloud_keychain === false ? "disabled" : ""}>Other Macs</button>
            </div>`
                : `<span class="sync-scope">${draft.keychain_scope === "icloud" ? "Other Macs" : "This Mac"}</span>`
            }
            ${
              settings.has_private_key
                ? `<button type="button" class="ghost" id="reveal-key">${revealedKey ? "Hide" : "Show"}</button>
                     <button type="button" class="ghost" id="import-toggle">${importOpen ? "Hide paste" : "Paste"}</button>`
                : `<button type="button" class="ghost" id="import-toggle">${importOpen ? "Hide paste" : "Paste"}</button>`
            }
          </div>
        </div>
        ${
          revealedKey && !pendingPrivateKey
            ? `<textarea class="key-box" id="sync-key-view" readonly>${escapeHtml(revealedKey)}</textarea>
               <div class="sync-actions"><button type="button" class="ghost" id="copy-key">Copy</button></div>`
            : ""
        }
        ${
          importOpen && !pendingPrivateKey
            ? `<textarea id="import-key" class="key-box short" placeholder="Paste the private key"></textarea>
               <div class="sync-actions"><button type="button" class="primary" id="import-key-btn">Save</button></div>`
            : ""
        }
        ${
          editing
            ? `<div class="sync-edit-actions">
            <button type="button" id="sync-cancel">cancel</button>
            <button type="button" class="primary" id="sync-save">${saveLabel}</button>
          </div>`
            : ""
        }
        </div>
      </section>`;
  }
  if (!existing) return;
  existing.innerHTML = `
    <div class="sync-layout">
      <header class="sync-hero">
        <div>
          <div class="sync-kicker"><span class="sync-dot ${phase}"></span>${phaseLabel}</div>
          ${phaseMeta ? `<p>${escapeHtml(phaseMeta)}</p>` : ""}
        </div>
        ${heroActions}
      </header>
      ${
        noneReady
          ? `<aside class="notice" role="status">
              <div>
                <strong>No cloud CLI</strong>
                <p>Install the AWS, Google Cloud, or Azure CLI.</p>
              </div>
            </aside>`
          : error
            ? `<aside class="notice notice-row" role="status">
              <div>
                <strong>Sync failed</strong>
                <p>${escapeHtml(error.message || "")}</p>
                ${error.details ? `<details><summary>Details</summary><pre>${escapeHtml(error.details)}</pre></details>` : ""}
              </div>
              ${error.kind === "auth" ? `<button type="button" class="primary" id="sync-sign-in">Sign in</button>` : ""}
            </aside>`
            : ""
      }
      ${stepCard}
      ${objectCard}
    </div>
  `;
  applySettingsAttention(sync);
  bindSyncPane();
}


function bindSyncPane() {
  const stopEditing = () => {
    syncSaveGen += 1;
    const step = syncStep();
    syncEditing = false;
    syncEnableAfterSave = false;
    syncValidateError = "";
    syncWizard = step === "join" || step === "create" ? "destination" : "";
    renderSync();
  };
  const applyEnableResult = (data) => {
    syncEditing = false;
    syncEnableAfterSave = false;
    syncValidateError = "";
    syncWizard = "";
    if (data.needs_create) {
      renderSync(data);
      return;
    }
    if (data.needs_join || data.needs_key) {
      importOpen = false;
      pendingPrivateKey = "";
      renderSync(data);
      return;
    }
    if (data.private_key) {
      pendingPrivateKey = data.private_key;
      savedKeyConfirm = false;
    }
    renderSync(data);
    if (!data.private_key && data.push?.action === "error") toast(data.push.error, "error");
    else if (!data.private_key) toast("Sync is on");
  };
  const saveSync = () => {
    const draft = syncDraft();
    const localError = validateSyncDraft(draft);
    if (localError) {
      syncValidateError = localError;
      renderSync();
      return;
    }
    const btn = $("#sync-save");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Checking…";
    }
    const gen = ++syncSaveGen;
    const turnOn = syncWizard === "destination" || syncEnableAfterSave || settings.sync?.enabled;
    api("/api/sync/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(draft),
    })
      .then(() => {
        if (gen !== syncSaveGen) return;
        if (turnOn) {
          return api("/api/sync/enable", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ...draft, username: settings.username || "" }),
          }).then((data) => {
            if (gen !== syncSaveGen) return;
            applyEnableResult(data);
          });
        }
        return savePrefs({
          keychain_scope: draft.keychain_scope,
          sync: {
            provider: draft.provider,
            bucket: draft.bucket,
            prefix: draft.prefix,
            account: draft.account,
            project: draft.project,
            what: draft.what,
          },
        }).then(() => {
          if (gen !== syncSaveGen) return;
          syncEditing = false;
          syncEnableAfterSave = false;
          syncValidateError = "";
          renderSync();
          toast("Saved");
        });
      })
      .catch((err) => {
        if (gen !== syncSaveGen) return;
        syncValidateError = err.message;
        renderSync();
      });
  };
  const turnOff = () => {
    syncSaveGen += 1;
    api("/api/sync/disable", { method: "POST" })
      .then((data) => {
        pendingPrivateKey = "";
        syncEditing = false;
        syncEnableAfterSave = false;
        renderSync(data);
        toast("Sync is off");
      })
      .catch((err) => toast(err.message, "error"));
  };
  $("#sync-toggle")?.addEventListener("click", () => {
    if (settings.sync?.enabled) {
      turnOff();
      return;
    }
    if (syncEnableAfterSave) {
      stopEditing();
      return;
    }
    syncEditing = true;
    syncEnableAfterSave = true;
    syncValidateError = "";
    renderSync();
  });
  $("#sync-setup")?.addEventListener("click", () => {
    syncWizard = "destination";
    syncEditing = false;
    syncEnableAfterSave = false;
    syncValidateError = "";
    renderSync();
  });
  $("#sync-interval")?.addEventListener("change", (event) => {
    savePrefs({ sync: { interval_sec: Number(event.target.value) } }).catch((err) => toast(err.message, "error"));
  });
  $("#sync-edit")?.addEventListener("click", () => {
    syncEditing = true;
    syncEnableAfterSave = false;
    syncValidateError = "";
    renderSync();
  });
  $("#sync-cancel")?.addEventListener("click", stopEditing);
  $("#sync-save")?.addEventListener("click", saveSync);
  $("#sync-sign-in")?.addEventListener("click", () => {
    const btn = $("#sync-sign-in");
    if (btn) btn.disabled = true;
    api("/api/sync/sign-in", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: settings.sync?.provider || "" }),
    })
      .then((data) => {
        renderSync(data);
        toast("Finish sign-in in Terminal, then turn sync on.");
      })
      .catch((err) => toast(err.message, "error"))
      .finally(() => {
        const again = $("#sync-sign-in");
        if (again) again.disabled = false;
      });
  });
  $("#sync-now")?.addEventListener("click", () => {
    const btn = $("#sync-now");
    if (!btn || btn.disabled) return;
    btn.disabled = true;
    api("/api/sync/push", { method: "POST" })
      .then((data) => {
        renderSync(data);
        if (data.action === "error") toast(data.error || "Sync failed", "error");
        else toast("Synced");
      })
      .catch((err) => {
        toast(err.message, "error");
        return api("/api/sync/status")
          .then((data) => renderSync(data))
          .catch(() => {});
      })
      .finally(() => {
        const again = $("#sync-now");
        if (again) again.disabled = !(settings.sync && settings.sync.enabled);
      });
  });
  $("#sync-provider")?.addEventListener("change", () => {
    const provider = $("#sync-provider").value;
    $("#azure-account-field")?.classList.toggle("hidden", provider !== "azure");
    $("#gcs-project-field")?.classList.toggle("hidden", provider !== "gcs");
  });
  ["sync-what-library", "sync-what-stats"].forEach((id) => {
    $(`#${id}`)?.addEventListener("click", () => {
      const btn = $(`#${id}`);
      btn.setAttribute("aria-pressed", btn.getAttribute("aria-pressed") === "true" ? "false" : "true");
    });
  });
  $("#copy-key")?.addEventListener("click", async () => {
    const text = $("#sync-key-view")?.value || "";
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      toast("Copied");
    } catch (_err) {
      toast("Select the key and copy it", "error");
    }
  });
  $("#saved-key")?.addEventListener("change", (event) => {
    savedKeyConfirm = event.target.checked;
    const btn = $("#confirm-sync");
    if (btn) btn.disabled = !savedKeyConfirm;
  });
  $("#confirm-sync")?.addEventListener("click", () => {
    if (!savedKeyConfirm) return;
    api("/api/sync/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pem: pendingPrivateKey }),
    })
      .then((data) => {
        pendingPrivateKey = "";
        savedKeyConfirm = false;
        renderSync(data);
        if (data.push?.action === "error") toast(data.push.error, "error");
        else toast("Sync is on");
      })
      .catch((err) => toast(err.message, "error"));
  });
  $("#reveal-key")?.addEventListener("click", () => {
    if (revealedKey) {
      revealedKey = "";
      renderSync();
      return;
    }
    api("/api/sync/reveal-key", { method: "POST" })
      .then((data) => {
        revealedKey = data.private_key || "";
        importOpen = false;
        renderSync();
      })
      .catch((err) => toast(err.message, "error"));
  });
  $("#import-toggle")?.addEventListener("click", () => {
    importOpen = !importOpen;
    if (importOpen) revealedKey = "";
    renderSync();
  });
  $("#import-key-btn")?.addEventListener("click", () => {
    api("/api/sync/import-key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pem: $("#import-key")?.value || "" }),
    })
      .then((data) => {
        pendingPrivateKey = "";
        importOpen = false;
        renderSync(data);
        if (data.needs_key && data.push?.error) toast(data.push.error, "error");
        else if (data.sync?.enabled) toast("Synced");
        else toast("Key saved");
      })
      .catch((err) => toast(err.message, "error"));
  });
  $("#sync-create")?.addEventListener("click", () => {
    const username = $("#sync-username")?.value.trim() || "";
    api("/api/sync/enable", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(syncDestinationPayload({ username })),
    })
      .then((data) => applyEnableResult(data))
      .catch((err) => toast(err.message, "error"));
  });
  $("#sync-join")?.addEventListener("click", () => {
    api("/api/sync/join", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: $("#sync-username")?.value.trim() || "",
        private_key: $("#sync-private-key")?.value || "",
      }),
    })
      .then((data) => {
        pendingPrivateKey = "";
        importOpen = false;
        renderSync(data);
        if (data.push?.action === "error") toast(data.push.error, "error");
        else if (data.sync?.enabled) toast("Sync is on");
      })
      .catch((err) => toast(err.message, "error"));
  });
  $("#scope-picks")?.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-scope]");
    if (!btn || btn.disabled) return;
    $("#scope-picks").querySelectorAll("button").forEach((el) => {
      el.classList.toggle("active", el === btn);
    });
  });
}

async function savePrefs(patch) {
  const data = await api("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  mergeSettings(data);
  renderPersonalization();
  renderAccount();
  if ("reduce_motion" in patch && motionReduced()) {
    clearOverviewFill();
    if (lastStats) setMeterValues(lastStats, false);
  }
  if (patch.theme || patch.accent || patch.timezone) {
    const stats = await api(statsUrl());
    renderStats(stats);
  }
}

async function saveAccount(patch) {
  const data = await api("/api/account", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  mergeSettings({
    username: data.username,
    private_mode: data.private_mode,
    lock: data.lock,
    device: data.device,
    devices: data.devices,
  });
  renderAccount();
}

function bindSettings() {
  $("#open-settings").addEventListener("click", () => {
    syncSaveGen += 1;
    syncEditing = false;
    syncEnableAfterSave = false;
    syncValidateError = "";
    syncWizard = "";
    renderPersonalization();
    renderAccount();
    renderModel();
    refreshModel()
      .then(() => {
        if (modelState.status === "loading") pollModel();
      })
      .catch((err) => toast(err.message, "error"));
    api("/api/sync/status")
      .then((data) => renderSync(data))
      .catch((err) => toast(err.message));
    $("#settings").showModal();
    $("#open-settings").classList.add("is-open");
    setPageFreeze(true);
    if ($("#open-settings").classList.contains("has-notice")) showSettings("sync");
    else if (modelPaneOpen()) syncModelTest(true);
  });
  $("#settings-close").addEventListener("click", () => $("#settings").close());
  $("#settings").addEventListener("close", () => {
    $("#open-settings").classList.remove("is-open");
    setPageFreeze(false);
    syncModelTest(false);
    const el = $("#toast");
    if (el?.classList.contains("is-on")) placeToast(el);
    refresh().catch((err) => toast(err.message));
  });
  $("#settings-nav").addEventListener("click", (event) => {
    const btn = event.target.closest("[data-settings-pane]");
    if (!btn) return;
    showSettings(btn.dataset.settingsPane);
  });
  $("#theme-picks").addEventListener("click", (event) => {
    const btn = event.target.closest("[data-theme]");
    if (!btn) return;
    savePrefs({ theme: btn.dataset.theme }).catch((err) => toast(err.message));
  });
  $("#accent-swatches").addEventListener("click", (event) => {
    const btn = event.target.closest("[data-accent]");
    if (!btn) return;
    savePrefs({ accent: btn.dataset.accent }).catch((err) => toast(err.message));
  });
  $("#timezone-select").addEventListener("change", (event) => {
    savePrefs({ timezone: event.target.value })
      .then(() => api(statsUrl()).then(renderStats))
      .catch((err) => toast(err.message));
  });
  $("#reduce-motion")?.addEventListener("click", () => {
    savePrefs({ reduce_motion: !settings.reduce_motion }).catch((err) => toast(err.message));
  });
  $("#pane-model")?.addEventListener("click", (event) => {
    const remove = event.target.closest("[data-remove-model]");
    if (remove) {
      event.preventDefault();
      event.stopPropagation();
      removeCustomModel(remove.dataset.removeModel).catch((err) => toast(err.message, "error"));
      return;
    }
    const btn = event.target.closest("[data-model]");
    if (!btn) return;
    if (btn.dataset.model === modelState.model && modelState.status !== "error") return;
    saveModel(btn.dataset.model).catch((err) => toast(err.message, "error"));
  });
  $("#add-custom-model")?.addEventListener("click", () => {
    modelAddOpen = !modelAddOpen;
    renderModelAddForm();
    if (modelAddOpen) $("#custom-model-path")?.focus();
  });
  $("#pick-model-path")?.addEventListener("click", async () => {
    try {
      const result = await api("/api/pick-path", { method: "POST" });
      if (result?.path) {
        const input = $("#custom-model-path");
        if (input) input.value = result.path;
        if (!$("#custom-model-name")?.value) {
          const parts = result.path.split("/").filter(Boolean);
          const name = $("#custom-model-name");
          if (name) name.value = parts[parts.length - 1] || "";
        }
      }
    } catch (err) {
      toast(err.message, "error");
    }
  });
  $("#save-custom-model")?.addEventListener("click", () => submitCustomModel());
  $("#model-add-form")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      submitCustomModel();
    }
    if (event.key === "Escape") {
      event.preventDefault();
      modelAddOpen = false;
      renderModelAddForm();
    }
  });
  $("#clear-model-test")?.addEventListener("click", () => {
    lastModelTest = "";
    const box = $("#model-test");
    if (box) box.value = "";
    api("/api/model/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clear: true, listen: true }),
    })
      .then(applyModelTest)
      .catch((err) => toast(err.message, "error"));
  });
  $("#private-mode")?.addEventListener("click", () => {
    saveAccount({ private_mode: !settings.private_mode }).catch((err) => toast(err.message, "error"));
  });
  $("#dashboard-lock")?.addEventListener("click", () => {
    const sw = $("#dashboard-lock");
    const want = sw.getAttribute("aria-pressed") !== "true";
    if (want) {
      lockDrafting = true;
      lockChangingPin = false;
      renderLockFields();
      return;
    }
    if (settings.lock?.enabled) {
      api("/api/lock/disable", { method: "POST" })
        .then((data) => {
          lockDrafting = false;
          lockChangingPin = false;
          applyLock(data);
          toast("Lock is off");
        })
        .catch((err) => {
          sw.setAttribute("aria-pressed", "true");
          toast(err.message, "error");
        });
      return;
    }
    lockDrafting = false;
    lockChangingPin = false;
    renderLockFields();
  });
  $("#lock-change")?.addEventListener("click", () => {
    lockChangingPin = true;
    renderLockFields();
    $("#lock-pin-old")?.focus();
  });
  $("#lock-cancel-change")?.addEventListener("click", () => {
    lockChangingPin = false;
    clearLockPinFields();
    renderLockFields();
  });
  $("#lock-save")?.addEventListener("click", () => {
    const changing = lockChangingPin;
    const pin = changing ? $("#lock-pin-new")?.value || "" : $("#lock-pin")?.value || "";
    const again = changing ? $("#lock-pin-confirm")?.value || "" : $("#lock-pin-again")?.value || "";
    if (pin !== again) {
      toast("PINs do not match.", "error");
      return;
    }
    const body = { pin, timeout_sec: Number($("#lock-timeout")?.value || 900) };
    if (changing) body.current = $("#lock-pin-old")?.value || "";
    api("/api/lock/setup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((data) => {
        lockDrafting = false;
        lockChangingPin = false;
        applyLock(data);
        clearLockPinFields();
        toast(changing ? "PIN saved" : "Lock is on");
      })
      .catch((err) => toast(err.message, "error"));
  });
  $("#lock-timeout")?.addEventListener("change", (event) => {
    if (!settings.lock?.enabled) return;
    api("/api/lock", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ timeout_sec: Number(event.target.value) }),
    })
      .then(applyLock)
      .catch((err) => toast(err.message, "error"));
  });
  $("#lock-now")?.addEventListener("click", () => {
    $("#settings")?.close();
    lockNow().catch((err) => toast(err.message, "error"));
  });
  $("#account-username")?.addEventListener("change", (event) => {
    saveAccount({ username: event.target.value }).catch((err) => toast(err.message, "error"));
  });
  $("#account-device-name")?.addEventListener("change", (event) => {
    saveAccount({ device: { name: event.target.value } }).catch((err) => toast(err.message, "error"));
  });
  $("#stats-device")?.addEventListener("change", (event) => {
    statsDevice = event.target.value;
    api(statsUrl())
      .then(renderStats)
      .catch((err) => toast(err.message));
  });
}

boot();
