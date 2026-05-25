import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

// Geometry constants (from config.py — mm)
const H_BASE = 80;
const L1 = 142;
const L2 = 158;
const L_TOOL = 56;
const DEG2RAD = Math.PI / 180;

// ── Scene ────────────────────────────────────────────────────────────────

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x1a1a2e);

const camera = new THREE.PerspectiveCamera(
    45,
    window.innerWidth / window.innerHeight,
    1,
    2000,
);
camera.position.set(350, 280, 350);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(window.devicePixelRatio);
document.body.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, H_BASE, 0);
controls.enableDamping = true;
controls.dampingFactor = 0.1;
controls.update();

// ── Lights ───────────────────────────────────────────────────────────────

scene.add(new THREE.AmbientLight(0x404040, 2));

const dirLight = new THREE.DirectionalLight(0xffffff, 1.5);
dirLight.position.set(200, 400, 300);
scene.add(dirLight);

const fillLight = new THREE.DirectionalLight(0xffffff, 0.5);
fillLight.position.set(-200, 200, -100);
scene.add(fillLight);

// ── Ground grid ──────────────────────────────────────────────────────────

scene.add(new THREE.GridHelper(800, 40, 0x444466, 0x333344));

// ── Materials ────────────────────────────────────────────────────────────

const matBase = new THREE.MeshPhongMaterial({ color: 0x555566 });
const matUpperArm = new THREE.MeshPhongMaterial({ color: 0x2196f3 });
const matForearm = new THREE.MeshPhongMaterial({ color: 0x43a047 });
const matTool = new THREE.MeshPhongMaterial({ color: 0xff9800 });
const matJoint = new THREE.MeshPhongMaterial({ color: 0xfdd835 });
const matTip = new THREE.MeshPhongMaterial({ color: 0xff5722 });

// ── Arm hierarchy ────────────────────────────────────────────────────────
//
// Three.js is Y-up.  Arm coordinate mapping:
//   arm X (radial)  →  Three.js +X
//   arm Z (up)      →  Three.js +Y
//   arm Y (lateral) →  Three.js -Z
//
// j0 rotates around Y.  j1/j2 rotate around local Z in the arm plane.

// Base — cylinder on the ground plane, rotates around Y by j0
const baseGroup = new THREE.Group();
scene.add(baseGroup);

const baseMesh = new THREE.Mesh(
    new THREE.CylinderGeometry(28, 34, H_BASE, 20),
    matBase,
);
baseMesh.position.y = H_BASE / 2;
baseGroup.add(baseMesh);

// Shoulder pivot — at the top of the base cylinder
const shoulderPivot = new THREE.Group();
shoulderPivot.position.y = H_BASE;
baseGroup.add(shoulderPivot);

const jointGeom = new THREE.SphereGeometry(9, 16, 12);
shoulderPivot.add(new THREE.Mesh(jointGeom, matJoint));

// Upper arm — rotates by j1 around local Z (absolute angle from horiz.)
const upperArmGroup = new THREE.Group();
shoulderPivot.add(upperArmGroup);

const upperArmMesh = new THREE.Mesh(
    new THREE.BoxGeometry(L1, 12, 12),
    matUpperArm,
);
upperArmMesh.position.x = L1 / 2;
upperArmGroup.add(upperArmMesh);

// Elbow pivot — at the far end of the upper arm
const elbowPivot = new THREE.Group();
elbowPivot.position.x = L1;
upperArmGroup.add(elbowPivot);

elbowPivot.add(
    new THREE.Mesh(new THREE.SphereGeometry(8, 16, 12), matJoint),
);

// Forearm — local rotation = (j2 − j1) so world rotation = j2 (absolute)
const forearmGroup = new THREE.Group();
elbowPivot.add(forearmGroup);

const forearmMesh = new THREE.Mesh(
    new THREE.BoxGeometry(L2, 10, 10),
    matForearm,
);
forearmMesh.position.x = L2 / 2;
forearmGroup.add(forearmMesh);

// Wrist pivot — at the far end of the forearm
const wristPivot = new THREE.Group();
wristPivot.position.x = L2;
forearmGroup.add(wristPivot);

wristPivot.add(
    new THREE.Mesh(new THREE.SphereGeometry(7, 16, 12), matJoint),
);

// Tool — local rotation = −j2 keeps it horizontal (parallel linkage)
const toolGroup = new THREE.Group();
wristPivot.add(toolGroup);

const toolMesh = new THREE.Mesh(
    new THREE.BoxGeometry(L_TOOL, 7, 7),
    matTool,
);
toolMesh.position.x = L_TOOL / 2;
toolGroup.add(toolMesh);

// Tool-tip marker
const tipMesh = new THREE.Mesh(
    new THREE.SphereGeometry(5, 12, 8),
    matTip,
);
tipMesh.position.x = L_TOOL;
toolGroup.add(tipMesh);

// ── Workspace volume (LatheGeometry from 2D cross-section) ──────────────

const J1_MIN = 0, J1_MAX = 135;
const J2_MIN = -135, J2_MAX = 90;
const paraFloor = (j1) => 2 * j1 - 180;

function fk2d(j1, j2) {
    const t1 = j1 * DEG2RAD;
    const t2 = j2 * DEG2RAD;
    const r = L1 * Math.cos(t1) + L2 * Math.cos(t2) + L_TOOL;
    const z = L1 * Math.sin(t1) + L2 * Math.sin(t2) + H_BASE;
    return new THREE.Vector2(r, z);
}

function computeWorkspaceProfile() {
    const pts = [];
    const step = 2;
    const eps = 0.5;
    const j1ParaDiagStart = (J2_MAX + 180) / 2 - eps;
    const j1ParaDiagEnd = (J2_MIN + 180) / 2;

    // Edge 1: j1=0, j2 from J2_MIN to J2_MAX
    for (let j2 = J2_MIN; j2 <= J2_MAX; j2 += step)
        pts.push(fk2d(0, j2));
    // Edge 2: j2=J2_MAX, j1 from 0 up to parallelogram limit
    for (let j1 = step; j1 <= j1ParaDiagStart; j1 += step)
        pts.push(fk2d(j1, J2_MAX));
    // Edge 3: parallelogram diagonal, j1 descending
    for (let j1 = j1ParaDiagStart; j1 >= j1ParaDiagEnd; j1 -= step) {
        const j2 = paraFloor(j1) + eps;
        if (j2 >= J2_MIN && j2 <= J2_MAX) pts.push(fk2d(j1, j2));
    }
    // Edge 4: j2=J2_MIN, j1 from j1ParaDiagEnd down to 0
    for (let j1 = j1ParaDiagEnd; j1 >= 0; j1 -= step)
        pts.push(fk2d(j1, J2_MIN));
    return pts;
}

const wsProfile = computeWorkspaceProfile();
const wsGeom = new THREE.LatheGeometry(wsProfile, 36, -Math.PI / 2, Math.PI);
const wsMat = new THREE.MeshPhongMaterial({
    color: 0x4fc3f7,
    transparent: true,
    opacity: 0.06,
    side: THREE.DoubleSide,
    depthWrite: false,
});
const workspaceMesh = new THREE.Mesh(wsGeom, wsMat);
scene.add(workspaceMesh);

const wsWireGeom = new THREE.LatheGeometry(wsProfile, 36, -Math.PI / 2, Math.PI);
const wsWireMat = new THREE.MeshBasicMaterial({
    color: 0x4fc3f7,
    wireframe: true,
    transparent: true,
    opacity: 0.04,
});
const workspaceWire = new THREE.Mesh(wsWireGeom, wsWireMat);
scene.add(workspaceWire);

window._workspaceVisible = true;
window.toggleWorkspace = function () {
    window._workspaceVisible = !window._workspaceVisible;
    workspaceMesh.visible = window._workspaceVisible;
    workspaceWire.visible = window._workspaceVisible;
};

// ── Pose update ──────────────────────────────────────────────────────────

function updateArm(state) {
    const j0 = state.j0 * DEG2RAD;
    const j1 = state.j1 * DEG2RAD;
    const j2 = state.j2 * DEG2RAD;

    baseGroup.rotation.y = -j0;
    upperArmGroup.rotation.z = j1;
    forearmGroup.rotation.z = j2 - j1;
    toolGroup.rotation.z = -j2;
}

function updateInfo(state) {
    document.getElementById("v-j0").textContent = state.j0.toFixed(2);
    document.getElementById("v-j1").textContent = state.j1.toFixed(2);
    document.getElementById("v-j2").textContent = state.j2.toFixed(2);
    document.getElementById("v-j3").textContent = state.j3.toFixed(2);
    document.getElementById("v-x").textContent = state.x.toFixed(1);
    document.getElementById("v-y").textContent = state.y.toFixed(1);
    document.getElementById("v-z").textContent = state.z.toFixed(1);
}

// ── WebSocket ────────────────────────────────────────────────────────────

function connectWebSocket() {
    const statusEl = document.getElementById("status");
    const ws = new WebSocket(`ws://${location.host}/ws`);

    ws.onopen = () => {
        statusEl.textContent = "Connected";
        statusEl.className = "connected";
    };

    ws.onmessage = (event) => {
        const state = JSON.parse(event.data);
        updateArm(state);
        updateInfo(state);
    };

    ws.onclose = () => {
        statusEl.textContent = "Disconnected — reconnecting…";
        statusEl.className = "error";
        setTimeout(connectWebSocket, 1000);
    };

    ws.onerror = () => {
        ws.close();
    };
}

connectWebSocket();

// ── Render loop ──────────────────────────────────────────────────────────

function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
}

animate();

// ── Resize ───────────────────────────────────────────────────────────────

window.addEventListener("resize", () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
});
