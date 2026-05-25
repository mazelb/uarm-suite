const API = "";

let latestState = { j0: 0, j1: 45, j2: -45, j3: 0, x: 0, y: 0, z: 0, recording: false };
let activeSlider = null;

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

// ── Init ────────────────────────────────────────────────────────────

connectControlWs();
refreshRecordings();
