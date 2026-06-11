const API = "";

let latestState = { j0: 0, j1: 45, j2: -45, j3: 0, x: 0, y: 0, z: 0, recording: false };
let activeSlider = null;

// ── Joint limits (mirrors config.py) ────────────────────────────────

const JOINT_LIMITS = {
    j0: [-90, 90],
    j1: [0, 135],
    j2: [-135, 90],
    j3: [-90, 90],
};
const WARN_DEG = 10;
const DANGER_DEG = 5;
const paraFloor = (j1) => 2 * j1 - 180;

// ── Toast notifications ─────────────────────────────────────────────

function showToast(msg, type = "error", duration = 4000) {
    const container = document.getElementById("toast-container");
    const el = document.createElement("div");
    el.className = "toast" + (type !== "error" ? ` ${type}` : "");
    el.textContent = msg;
    container.appendChild(el);
    setTimeout(() => { el.remove(); }, duration);
}

// ── API helpers ─────────────────────────────────────────────────────

async function apiPost(path, body = {}) {
    const resp = await fetch(API + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (!resp.ok) {
        showToast(data.error || `Error ${resp.status}`);
        return null;
    }
    return data;
}

async function apiGet(path) {
    const resp = await fetch(API + path);
    return resp.json();
}

// ── WebSocket listener for state sync ───────────────────────────────

function connectControlWs() {
    const ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onmessage = (e) => {
        latestState = JSON.parse(e.data);
        syncSliders();
        syncRecordBtn();
    };
    ws.onclose = () => { setTimeout(connectControlWs, 1000); };
    ws.onerror = () => { ws.close(); };
}

// ── Joint sliders ───────────────────────────────────────────────────

const sliders = ["j0", "j1", "j2", "j3"];
let sliderThrottleId = null;

function syncSliders() {
    for (const name of sliders) {
        if (activeSlider === name) continue;
        const sl = document.getElementById(`sl-${name}`);
        const valEl = document.getElementById(`sl-${name}-val`);
        if (sl && latestState[name] !== undefined) {
            sl.value = latestState[name];
            valEl.textContent = latestState[name].toFixed(1);
        }
    }
    checkSoftLimits();
}

// ── Soft-limit checks ───────────────────────────────────────────────

let _lastLimitToast = 0;
const LIMIT_TOAST_COOLDOWN_MS = 3000;

function checkSoftLimits() {
    for (const name of sliders) {
        const val = latestState[name];
        const [lo, hi] = JOINT_LIMITS[name];
        const sl = document.getElementById(`sl-${name}`);
        const distLo = val - lo;
        const distHi = hi - val;
        const minDist = Math.min(distLo, distHi);

        sl.classList.remove("limit-warn", "limit-danger");
        if (minDist <= DANGER_DEG) {
            sl.classList.add("limit-danger");
        } else if (minDist <= WARN_DEG) {
            sl.classList.add("limit-warn");
        }
    }

    // Parallelogram coupled constraint: j2 > 2*j1 - 180
    const floor = paraFloor(latestState.j1);
    const paraMargin = latestState.j2 - floor;
    const paraEl = document.getElementById("sl-j2");
    if (paraMargin <= DANGER_DEG && paraMargin > 0) {
        paraEl.classList.add("limit-danger");
        _maybeToast(`Parallelogram constraint: j2 within ${paraMargin.toFixed(1)}° of limit`);
    } else if (paraMargin <= WARN_DEG && paraMargin > 0) {
        if (!paraEl.classList.contains("limit-danger"))
            paraEl.classList.add("limit-warn");
    }
}

function _maybeToast(msg) {
    const now = Date.now();
    if (now - _lastLimitToast > LIMIT_TOAST_COOLDOWN_MS) {
        _lastLimitToast = now;
        showToast(msg, "warning", 3000);
    }
}

function sendSliders() {
    const vals = {};
    for (const name of sliders) {
        vals[name] = parseFloat(document.getElementById(`sl-${name}`).value);
    }
    apiPost("/api/joints", vals);
}

function throttledSendSliders() {
    if (sliderThrottleId) return;
    sliderThrottleId = setTimeout(() => {
        sliderThrottleId = null;
        sendSliders();
    }, 80);
}

for (const name of sliders) {
    const sl = document.getElementById(`sl-${name}`);
    const valEl = document.getElementById(`sl-${name}-val`);

    sl.addEventListener("input", () => {
        activeSlider = name;
        valEl.textContent = parseFloat(sl.value).toFixed(1);
        throttledSendSliders();
    });

    sl.addEventListener("change", () => {
        activeSlider = null;
        sendSliders();
    });
}

// ── Jog buttons ─────────────────────────────────────────────────────

for (const btn of document.querySelectorAll(".jog-btn")) {
    btn.addEventListener("click", async () => {
        const axis = btn.dataset.axis;
        const dir = parseInt(btn.dataset.dir, 10);
        const step = parseFloat(document.getElementById("jog-step").value) || 10;
        const target = {
            x: latestState.x,
            y: latestState.y,
            z: latestState.z,
        };
        target[axis] += step * dir;
        btn.disabled = true;
        await apiPost("/api/goto", target);
        btn.disabled = false;
    });
}

// ── Home button ─────────────────────────────────────────────────────

document.getElementById("home-btn").addEventListener("click", async () => {
    const btn = document.getElementById("home-btn");
    btn.disabled = true;
    btn.textContent = "Homing...";
    await apiPost("/api/home");
    btn.disabled = false;
    btn.textContent = "Home";
});

// ── Go-to position form ─────────────────────────────────────────────

document.getElementById("goto-btn").addEventListener("click", async () => {
    const x = parseFloat(document.getElementById("goto-x").value);
    const y = parseFloat(document.getElementById("goto-y").value);
    const z = parseFloat(document.getElementById("goto-z").value);
    const wrist = parseFloat(document.getElementById("goto-w").value) || 0;
    if ([x, y, z].some(isNaN)) {
        showToast("Enter valid X, Y, Z values");
        return;
    }
    const btn = document.getElementById("goto-btn");
    btn.disabled = true;
    await apiPost("/api/goto", { x, y, z, wrist });
    btn.disabled = false;
});

// ── Teach / record ──────────────────────────────────────────────────

const recBtn = document.getElementById("rec-btn");

function syncRecordBtn() {
    if (latestState.recording) {
        recBtn.textContent = "Stop";
        recBtn.classList.add("recording");
    } else {
        recBtn.textContent = "Record";
        recBtn.classList.remove("recording");
    }
}

recBtn.addEventListener("click", async () => {
    if (latestState.recording) {
        recBtn.disabled = true;
        const data = await apiPost("/api/record/stop");
        recBtn.disabled = false;
        if (data) {
            showToast("Recording saved", "success", 2000);
            refreshRecordings();
        }
    } else {
        const name = document.getElementById("rec-name").value.trim();
        if (!name) {
            showToast("Enter a recording name");
            return;
        }
        await apiPost("/api/record/start", { name });
    }
});

// ── Recordings list ─────────────────────────────────────────────────

async function refreshRecordings() {
    const data = await apiGet("/api/recordings");
    const listEl = document.getElementById("rec-list");
    if (!data.recordings || data.recordings.length === 0) {
        listEl.innerHTML = "<em>none</em>";
        return;
    }
    listEl.innerHTML = "";
    for (const name of data.recordings) {
        const item = document.createElement("div");
        item.className = "rec-item";

        const label = document.createElement("span");
        label.textContent = name;

        const playBtn = document.createElement("button");
        playBtn.textContent = "Play";
        playBtn.addEventListener("click", async () => {
            const speed = parseFloat(document.getElementById("replay-speed").value) || 1.0;
            playBtn.disabled = true;
            playBtn.textContent = "...";
            await apiPost("/api/play", { name, speed_factor: speed });
            playBtn.disabled = false;
            playBtn.textContent = "Play";
        });

        item.appendChild(label);
        item.appendChild(playBtn);
        listEl.appendChild(item);
    }
}

// ── Panel toggle ────────────────────────────────────────────────────

document.getElementById("toggle-controls").addEventListener("click", () => {
    const panel = document.getElementById("controls");
    const btn = document.getElementById("toggle-controls");
    panel.classList.toggle("collapsed");
    btn.textContent = panel.classList.contains("collapsed") ? "›" : "‹";
});

// ── Workspace toggle ────────────────────────────────────────────────

document.getElementById("ws-toggle").addEventListener("click", () => {
    const btn = document.getElementById("ws-toggle");
    if (typeof window.toggleWorkspace === "function") {
        window.toggleWorkspace();
        btn.textContent = window._workspaceVisible ? "Hide Workspace" : "Show Workspace";
    }
});

// ── Calibration wizard ──────────────────────────────────────────────

const CAL_CHANNELS = [0, 1, 2, 3];
const CAL_NAMES = ["J0", "J1", "J2", "J3"];

async function loadCalibration() {
    const data = await apiGet("/api/calibration");
    if (!data) return;
    for (const ch of CAL_CHANNELS) {
        const cal = data[String(ch)];
        if (!cal) continue;
        document.getElementById(`cal-zero-${ch}`).value = cal.zero_deg;
        document.getElementById(`cal-dir-${ch}`).value = cal.direction;
        document.getElementById(`cal-min-${ch}`).value = cal.min_us;
        document.getElementById(`cal-max-${ch}`).value = cal.max_us;
    }
}

async function updateCalibration(channel) {
    const zero_deg = parseFloat(document.getElementById(`cal-zero-${channel}`).value);
    const direction = parseInt(document.getElementById(`cal-dir-${channel}`).value, 10);
    const min_us = parseInt(document.getElementById(`cal-min-${channel}`).value, 10);
    const max_us = parseInt(document.getElementById(`cal-max-${channel}`).value, 10);
    if ([zero_deg, direction, min_us, max_us].some(isNaN)) {
        showToast("Invalid calibration value");
        return;
    }
    await apiPost("/api/calibration", { channel, zero_deg, direction, min_us, max_us });
    showToast(`Ch ${channel} calibration updated`, "info", 2000);
}

async function testJoint(channel, angle) {
    const cmd = { j0: latestState.j0, j1: latestState.j1, j2: latestState.j2, j3: latestState.j3 };
    cmd[`j${channel}`] = angle;
    await apiPost("/api/joints", cmd);
}

for (const ch of CAL_CHANNELS) {
    document.getElementById(`cal-apply-${ch}`).addEventListener("click", () => updateCalibration(ch));
    document.getElementById(`cal-test0-${ch}`).addEventListener("click", () => testJoint(ch, 0));
    document.getElementById(`cal-test45-${ch}`).addEventListener("click", () => testJoint(ch, 45));
    document.getElementById(`cal-testn45-${ch}`).addEventListener("click", () => testJoint(ch, -45));
}

document.getElementById("cal-save").addEventListener("click", async () => {
    await apiPost("/api/calibration/save");
    showToast("Calibration saved to disk", "success", 2000);
});

document.getElementById("cal-reset").addEventListener("click", async () => {
    await apiPost("/api/calibration/reset");
    await loadCalibration();
    showToast("Calibration reset to defaults", "info", 2000);
});

// ── Pen / drawing config ────────────────────────────────────────────

let penCfg = null; // last-loaded /api/pen response

function renderPen() {
    if (!penCfg) return;
    document.getElementById("pen-table-z").value = penCfg.table_z;
    document.getElementById("pen-up").value = penCfg.pen_up;
    document.getElementById("pen-wrist").value = penCfg.wrist;
    document.getElementById("pen-label").value = penCfg.pen_label || "";
    const feedEl = document.getElementById("pen-feed");
    const travelEl = document.getElementById("pen-travel-feed");
    feedEl.value = penCfg.feed ?? "";
    feedEl.placeholder = `${penCfg.effective_feed}`;
    travelEl.value = penCfg.travel_feed ?? "";
    travelEl.placeholder = `${penCfg.effective_travel_feed}`;
}

async function loadPen() {
    penCfg = await apiGet("/api/pen");
    renderPen();
}

document.getElementById("pen-use-z").addEventListener("click", () => {
    document.getElementById("pen-table-z").value = latestState.z;
});

document.getElementById("pen-save").addEventListener("click", async () => {
    const num = (id) => {
        const v = document.getElementById(id).value.trim();
        return v === "" ? null : parseFloat(v); // empty feed = clear to default
    };
    const body = {
        table_z: num("pen-table-z"),
        pen_up: num("pen-up"),
        wrist: num("pen-wrist"),
        feed: num("pen-feed"),
        travel_feed: num("pen-travel-feed"),
        pen_label: document.getElementById("pen-label").value.trim(),
    };
    const data = await apiPost("/api/pen", body);
    if (data) {
        penCfg = data;
        renderPen();
        showToast("Pen config saved", "success", 2000);
    }
});

document.getElementById("pen-jog").addEventListener("click", async () => {
    const btn = document.getElementById("pen-jog");
    const body = {
        center_x: parseFloat(document.getElementById("pen-jog-cx").value) || 250,
        center_y: parseFloat(document.getElementById("pen-jog-cy").value) || 0,
        cell: parseFloat(document.getElementById("pen-jog-cell").value) || 40,
    };
    btn.disabled = true; btn.textContent = "Jogging…";
    const data = await apiPost("/api/pen/jog-corners", body);
    btn.disabled = false; btn.textContent = "Jog corners";
    if (data) showToast("Grid corners visited — footprint OK", "success", 2500);
});

// ── Activities ──────────────────────────────────────────────────────

let activitiesMeta = [];
let tttBusy = false;
const activitySelect = document.getElementById("activity-select");

async function loadActivities() {
    const data = await apiGet("/api/activities");
    activitiesMeta = data.activities || [];
    activitySelect.innerHTML = "";
    for (const a of activitiesMeta) {
        const opt = document.createElement("option");
        opt.value = a.slug;
        opt.textContent = a.name;
        activitySelect.appendChild(opt);
    }
    updateActivityUI();
}

function currentActivity() {
    return activitiesMeta.find((a) => a.slug === activitySelect.value);
}

function updateActivityUI() {
    const a = currentActivity();
    const isTTT = a && a.slug === "tic-tac-toe";
    const isShapes = a && a.slug === "draw-shapes";
    document.getElementById("activity-desc").textContent = a ? a.description : "";
    document.getElementById("ttt-widget").style.display = isTTT ? "block" : "none";
    document.getElementById("shapes-widget").style.display = isShapes ? "block" : "none";
    // Generic Run button only for non-interactive activities without a custom widget.
    const generic = a && !a.interactive && !isShapes;
    document.getElementById("activity-run").style.display = generic ? "block" : "none";
    if (isTTT) renderBoard(_emptyState());
}

activitySelect.addEventListener("change", updateActivityUI);

// Drawing trace controls (viz.js exposes window.trace)
document.getElementById("trace-clear").addEventListener("click", () => {
    window.trace?.clear();
});
document.getElementById("trace-toggle").addEventListener("change", (e) => {
    window.trace?.setEnabled(e.target.checked);
});

document.getElementById("activity-run").addEventListener("click", async () => {
    const a = currentActivity();
    if (!a) return;
    const btn = document.getElementById("activity-run");
    btn.disabled = true; btn.textContent = "Running…";
    await apiPost(`/api/activities/${a.slug}/run`);
    btn.disabled = false; btn.textContent = "Run";
});

// ── Tic-tac-toe ─────────────────────────────────────────────────────

function _emptyState() {
    return {
        board: [["", "", ""], ["", "", ""], ["", "", ""]],
        turn: "X", status: "Press New Game to start.", over: true,
    };
}

function renderBoard(state) {
    const boardEl = document.getElementById("ttt-board");
    boardEl.innerHTML = "";
    for (let r = 0; r < 3; r++) {
        for (let c = 0; c < 3; c++) {
            const cell = document.createElement("button");
            cell.className = "ttt-cell";
            const v = state.board[r][c];
            cell.textContent = v;
            cell.classList.toggle("x", v === "X");
            cell.classList.toggle("o", v === "O");
            const playable = !tttBusy && !state.over && state.turn === "X" && v === "";
            cell.disabled = !playable;
            cell.addEventListener("click", () => tttMove(r, c));
            boardEl.appendChild(cell);
        }
    }
    document.getElementById("ttt-status").textContent = state.status;
}

async function tttNewGame() {
    if (tttBusy) return;
    tttBusy = true;
    document.getElementById("ttt-status").textContent = "Drawing grid…";
    window.trace?.clear(); // fresh board, fresh trace
    const options = {
        center_x: parseFloat(document.getElementById("ttt-cx").value) || 250,
        center_y: parseFloat(document.getElementById("ttt-cy").value) || 0,
        cell: parseFloat(document.getElementById("ttt-cell").value) || 40,
    };
    const state = await apiPost("/api/activities/tic-tac-toe/start", options);
    tttBusy = false;
    if (state) {
        if (state.config) window.trace?.configure(state.config.table_z, state.config.pen_up);
        renderBoard(state);
    }
}

async function tttMove(r, c) {
    if (tttBusy) return;
    tttBusy = true;
    document.getElementById("ttt-status").textContent = "Thinking…";
    const state = await apiPost("/api/activities/tic-tac-toe/move", { row: r, col: c });
    tttBusy = false;
    if (state) renderBoard(state);
}

document.getElementById("ttt-new").addEventListener("click", tttNewGame);

// ── Draw-shapes ─────────────────────────────────────────────────────

document.getElementById("shapes-draw").addEventListener("click", async () => {
    const btn = document.getElementById("shapes-draw");
    const options = {
        shape: document.getElementById("shapes-shape").value,
        size: parseFloat(document.getElementById("shapes-size").value) || 40,
        center_x: parseFloat(document.getElementById("shapes-cx").value) || 250,
        center_y: parseFloat(document.getElementById("shapes-cy").value) || 0,
    };
    // draw-shapes loads the persisted pen geometry server-side; mirror it here.
    window.trace?.configure(penCfg?.table_z ?? 0, penCfg?.pen_up ?? 20);
    btn.disabled = true; btn.textContent = "Drawing…";
    await apiPost("/api/activities/draw-shapes/run", options);
    btn.disabled = false; btn.textContent = "Draw";
});

// ── Init ────────────────────────────────────────────────────────────

connectControlWs();
refreshRecordings();
loadCalibration();
loadActivities();
loadPen();
