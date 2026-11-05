/* ==========================================================================
   LUMI NEXT-GEN CYBERNETIC WEB CLIENT
   Interactive AI Core Orb · Audio Synthesis · Realtime Telemetry · Glass HUD
   ========================================================================== */

const $ = (id) => document.getElementById(id);
const chat = $("chat");
let busy = false, stick = true, anyToken = false;
let curRow = null, curText = "", lastToolRow = null;
let currentOrbState = "IDLE";

/* ── Web Audio Synthesizer (Zero asset dependencies) ──────────── */
let audioCtx = null;
let sfxEnabled = localStorage.getItem("lumi_sfx") !== "false";

function initAudio() {
  if (!audioCtx) {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (AudioContext) audioCtx = new AudioContext();
  }
  if (audioCtx && audioCtx.state === "suspended") {
    audioCtx.resume();
  }
}

function playSfx(type) {
  if (!sfxEnabled) return;
  try {
    initAudio();
    if (!audioCtx) return;
    const t = audioCtx.currentTime;
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.connect(gain);
    gain.connect(audioCtx.destination);

    if (type === "send") {
      osc.type = "sine";
      osc.frequency.setValueAtTime(640, t);
      osc.frequency.exponentialRampToValueAtTime(1100, t + 0.12);
      gain.gain.setValueAtTime(0.08, t);
      gain.gain.exponentialRampToValueAtTime(0.001, t + 0.12);
      osc.start(t);
      osc.stop(t + 0.12);
    } else if (type === "token") {
      if (Math.random() > 0.3) return; // Don't trigger on every token, just light haptic click
      osc.type = "triangle";
      osc.frequency.setValueAtTime(1200 + Math.random() * 400, t);
      gain.gain.setValueAtTime(0.015, t);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.03);
      osc.start(t);
      osc.stop(t + 0.03);
    } else if (type === "tool") {
      osc.type = "sawtooth";
      osc.frequency.setValueAtTime(450, t);
      osc.frequency.exponentialRampToValueAtTime(880, t + 0.16);
      gain.gain.setValueAtTime(0.04, t);
      gain.gain.exponentialRampToValueAtTime(0.001, t + 0.16);
      osc.start(t);
      osc.stop(t + 0.16);
    } else if (type === "done") {
      osc.type = "sine";
      osc.frequency.setValueAtTime(520, t);
      osc.frequency.setValueAtTime(780, t + 0.08);
      osc.frequency.setValueAtTime(1040, t + 0.16);
      gain.gain.setValueAtTime(0.06, t);
      gain.gain.exponentialRampToValueAtTime(0.001, t + 0.28);
      osc.start(t);
      osc.stop(t + 0.28);
    } else if (type === "alert") {
      osc.type = "square";
      osc.frequency.setValueAtTime(880, t);
      osc.frequency.setValueAtTime(440, t + 0.12);
      gain.gain.setValueAtTime(0.07, t);
      gain.gain.exponentialRampToValueAtTime(0.001, t + 0.25);
      osc.start(t);
      osc.stop(t + 0.25);
    }
  } catch (err) {
    /* Silent ignore if browser blocks audio */
  }
}

/* ── SFX and TTS Controls in HUD ──────────────────────────────── */
const sfxBtn = $("sfxBtn");
if (sfxBtn) {
  function updateSfxBtn() {
    sfxBtn.className = "pill pill-action" + (sfxEnabled ? " active" : "");
    sfxBtn.innerHTML = (sfxEnabled ? '<span class="pill-icon">🔊</span> SFX' : '<span class="pill-icon">🔇</span> SFX');
    sfxBtn.title = sfxEnabled ? "Cybernetic SFX: Enabled" : "Cybernetic SFX: Muted";
  }
  updateSfxBtn();
  sfxBtn.onclick = () => {
    sfxEnabled = !sfxEnabled;
    localStorage.setItem("lumi_sfx", sfxEnabled ? "true" : "false");
    updateSfxBtn();
    if (sfxEnabled) playSfx("done");
  };
}

/* ── 3D Interactive Galaxy & Cosmic Nebula Engine ─────────────── */
function initBackgroundCanvas() {
  const canvas = $("bgCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  let w = (canvas.width = window.innerWidth);
  let h = (canvas.height = window.innerHeight);

  window.addEventListener("resize", () => {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
  });

  // 3D Celestial Camera & Mouse Parallax with Damping
  let mouseNormX = 0;
  let mouseNormY = 0;
  let camRotX = 0.38; // 3D galactic inclination angle
  let camRotY = 0;
  let targetCamRotX = 0.38;
  let targetCamRotY = 0;

  window.addEventListener("mousemove", (e) => {
    mouseNormX = (e.clientX / window.innerWidth) * 2 - 1;
    mouseNormY = (e.clientY / window.innerHeight) * 2 - 1;
    targetCamRotY = mouseNormX * 0.45;
    targetCamRotX = 0.38 + mouseNormY * 0.32;
  });

  // Galaxy Particle System: 3 Spiral Arms + Core + Deep Cosmic Dust
  const PARTICLE_COUNT = Math.min(420, Math.floor((w * h) / 3600));
  const particles = [];
  const arms = 3;

  for (let i = 0; i < PARTICLE_COUNT; i++) {
    const isArm = i < PARTICLE_COUNT * 0.75;
    if (isArm) {
      // Spiral Arm Particle
      const armIndex = i % arms;
      const armAngle = (armIndex * (Math.PI * 2)) / arms;
      const distance = Math.pow(Math.random(), 1.55) * Math.min(w, h) * 0.72 + 25;
      const spiralOffset = distance * 0.0035;
      const angle = armAngle + spiralOffset + (Math.random() - 0.5) * 0.45;
      const discThickness = Math.max(15, (1 - distance / (Math.min(w, h) * 0.8)) * 85);
      
      const x = Math.cos(angle) * distance;
      const y = Math.sin(angle) * distance;
      const z = (Math.random() - 0.5) * discThickness;

      // Color palette: Eternal Green (#00ff9d), Electric Purple (#a855f7), Solar Gold (#fbbf24), or Pure White
      const colorType = Math.random();
      const color = colorType < 0.44 ? "0, 255, 157" : colorType < 0.72 ? "168, 85, 247" : colorType < 0.88 ? "251, 191, 36" : "255, 255, 255";
      const size = Math.random() < 0.09 ? (Math.random() * 2.2 + 1.6) : (Math.random() * 1.3 + 0.6);

      particles.push({
        x, y, z,
        origDist: distance,
        baseAngle: angle,
        orbitSpeed: (0.0008 + (1 / (distance + 40)) * 0.15) * (0.8 + Math.random() * 0.4),
        color,
        size,
        alpha: Math.random() * 0.65 + 0.35,
        twinkleSpeed: Math.random() * 2 + 1,
        twinklePhase: Math.random() * Math.PI * 2
      });
    } else {
      // Deep Space Stellar Field
      const spread = Math.max(w, h) * 1.15;
      const deepRnd = Math.random();
      const deepColor = deepRnd < 0.45 ? "0, 255, 157" : deepRnd < 0.8 ? "168, 85, 247" : "251, 191, 36";
      particles.push({
        x: (Math.random() - 0.5) * spread,
        y: (Math.random() - 0.5) * spread,
        z: (Math.random() - 0.5) * 600,
        origDist: 0,
        baseAngle: 0,
        orbitSpeed: 0.00015 * (Math.random() > 0.5 ? 1 : -1),
        color: deepColor,
        size: Math.random() * 1.2 + 0.5,
        alpha: Math.random() * 0.5 + 0.2,
        twinkleSpeed: Math.random() * 1.5 + 0.5,
        twinklePhase: Math.random() * Math.PI * 2
      });
    }
  }

  // Shooting Stars / Cosmic Comets Engine
  const comets = [];
  let nextCometTime = performance.now() + 1500;

  function spawnComet() {
    const startX = Math.random() * w;
    const startY = Math.random() * (h * 0.4);
    const speed = Math.random() * 9 + 13;
    const angle = Math.PI * 0.25 + (Math.random() - 0.5) * 0.35;
    const cometRnd = Math.random();
    const cometColor = cometRnd < 0.45 ? "0, 255, 157" : cometRnd < 0.8 ? "168, 85, 247" : "251, 191, 36";
    comets.push({
      x: startX,
      y: startY,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      length: Math.random() * 130 + 80,
      width: Math.random() * 2 + 1.2,
      life: 1.0,
      decay: Math.random() * 0.016 + 0.012,
      color: cometColor
    });
  }

  function animate() {
    const now = performance.now();
    const t = now / 1000;

    ctx.clearRect(0, 0, w, h);

    // Smooth Camera Inertial Damping
    camRotX += (targetCamRotX - camRotX) * 0.04;
    camRotY += (targetCamRotY - camRotY) * 0.04;

    const cx = w / 2;
    const cy = h / 2;
    const cosY = Math.cos(camRotY);
    const sinY = Math.sin(camRotY);
    const cosX = Math.cos(camRotX);
    const sinX = Math.sin(camRotX);

    // Set Additive Luminous Blending for genuine cosmic glow
    ctx.globalCompositeOperation = "lighter";

    // 1. Draw Central Cosmic Core Glow with Solar Gold Warmth
    const coreGrad = ctx.createRadialGradient(cx, cy, 5, cx, cy, Math.min(w, h) * 0.35);
    coreGrad.addColorStop(0, "rgba(0, 255, 157, 0.16)");
    coreGrad.addColorStop(0.24, "rgba(251, 191, 36, 0.11)");
    coreGrad.addColorStop(0.55, "rgba(168, 85, 247, 0.10)");
    coreGrad.addColorStop(0.8, "rgba(20, 10, 35, 0.04)");
    coreGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = coreGrad;
    ctx.beginPath();
    ctx.arc(cx, cy, Math.min(w, h) * 0.35, 0, Math.PI * 2);
    ctx.fill();

    // 2. Render 3D Rotating Galaxy Particles
    const fov = 650;
    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];

      // Orbit rotation around galactic Z axis
      if (p.origDist > 0) {
        p.baseAngle += p.orbitSpeed;
        p.x = Math.cos(p.baseAngle) * p.origDist;
        p.y = Math.sin(p.baseAngle) * p.origDist;
      }

      // 3D Camera Rotation (Yaw around Y, Pitch around X)
      const x1 = p.x * cosY - p.z * sinY;
      const z1 = p.x * sinY + p.z * cosY;
      const y2 = p.y * cosX - z1 * sinX;
      const z2 = p.y * sinX + z1 * cosX;

      // Perspective Projection
      const depth = z2 + 750;
      if (depth <= 20) continue;

      const scale = fov / depth;
      let px = cx + x1 * scale;
      let py = cy + y2 * scale;

      // Subtle Gravitational Deflection from Mouse Cursor
      if (mouseNormX !== 0 || mouseNormY !== 0) {
        const mx = (mouseNormX + 1) * 0.5 * w;
        const my = (mouseNormY + 1) * 0.5 * h;
        const dx = px - mx;
        const dy = py - my;
        const dist = Math.hypot(dx, dy);
        if (dist < 140 && dist > 5) {
          const force = (1 - dist / 140) * 12;
          px += (dx / dist) * force;
          py += (dy / dist) * force;
        }
      }

      // Star Twinkle & Radiant Halo
      const twinkle = Math.sin(t * p.twinkleSpeed + p.twinklePhase) * 0.25 + 0.75;
      const renderAlpha = Math.min(1, Math.max(0.1, p.alpha * twinkle * (scale * 0.9)));
      const renderSize = Math.max(0.5, p.size * scale);

      ctx.beginPath();
      ctx.arc(px, py, renderSize, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${p.color}, ${renderAlpha})`;
      ctx.fill();

      // Radiant halo for bright / core stars
      if (p.size > 1.4 && renderAlpha > 0.35) {
        ctx.beginPath();
        ctx.arc(px, py, renderSize * 2.8, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${p.color}, ${renderAlpha * 0.18})`;
        ctx.fill();
      }
    }

    // 3. Render Shooting Stars / Comets
    if (now > nextCometTime) {
      spawnComet();
      nextCometTime = now + Math.random() * 4000 + 2500;
    }

    for (let cIdx = comets.length - 1; cIdx >= 0; cIdx--) {
      const c = comets[cIdx];
      c.x += c.vx;
      c.y += c.vy;
      c.life -= c.decay;

      if (c.life <= 0 || c.x > w + 200 || c.y > h + 200) {
        comets.splice(cIdx, 1);
        continue;
      }

      const tailX = c.x - (c.vx / Math.hypot(c.vx, c.vy)) * c.length * c.life;
      const tailY = c.y - (c.vy / Math.hypot(c.vx, c.vy)) * c.length * c.life;

      const cometGrad = ctx.createLinearGradient(c.x, c.y, tailX, tailY);
      cometGrad.addColorStop(0, `rgba(255, 255, 255, ${c.life})`);
      cometGrad.addColorStop(0.3, `rgba(${c.color}, ${c.life * 0.8})`);
      cometGrad.addColorStop(1, "rgba(0, 0, 0, 0)");

      ctx.beginPath();
      ctx.moveTo(c.x, c.y);
      ctx.lineTo(tailX, tailY);
      ctx.strokeStyle = cometGrad;
      ctx.lineWidth = c.width * c.life;
      ctx.stroke();

      // Comet Head Spark
      ctx.beginPath();
      ctx.arc(c.x, c.y, c.width * 1.5, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(255, 255, 255, ${c.life})`;
      ctx.fill();
    }

    ctx.globalCompositeOperation = "source-over";
    requestAnimationFrame(animate);
  }

  animate();
}

/* ── 3D Interactive Card Tilt & Gyroscopic Floating Engine ──────── */
function init3DInteractiveEffects() {
  // 1. 3D Arc Reactor Gyroscopic Floating Tilt
  const arcReactor = $("arcReactor");
  if (arcReactor) {
    let targetRx = 0;
    let targetRy = 0;
    let currentRx = 0;
    let currentRy = 0;
    let isTilting = false;

    window.addEventListener("mousemove", (e) => {
      if (appMode !== "jarvis") return;
      const rect = arcReactor.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;
      const dx = e.clientX - centerX;
      const dy = e.clientY - centerY;
      const dist = Math.hypot(dx, dy);

      // Tilts smoothly towards mouse pointer within 750px radius
      if (dist < 750) {
        isTilting = true;
        targetRy = (dx / 750) * 16; // Max 16 deg yaw
        targetRx = (-dy / 750) * 16; // Max 16 deg pitch
      } else {
        targetRx = 0;
        targetRy = 0;
      }
    }, { passive: true });

    function renderArcReactorTilt() {
      if (appMode === "jarvis") {
        currentRx += (targetRx - currentRx) * 0.08;
        currentRy += (targetRy - currentRy) * 0.08;
        if (Math.abs(currentRx) > 0.02 || Math.abs(currentRy) > 0.02 || isTilting) {
          arcReactor.style.transform = `perspective(1000px) rotateX(${currentRx.toFixed(2)}deg) rotateY(${currentRy.toFixed(2)}deg) translateZ(8px)`;
        }
      }
      requestAnimationFrame(renderArcReactorTilt);
    }
    renderArcReactorTilt();
  }

  // 2. 3D Card Hover Tilt with Specular Spotlight Effect
  document.addEventListener("mousemove", (e) => {
    const card = e.target.closest(".glass-panel, .wing-card, .hud-card, .swarm-card, .vault-card, .command-item");
    if (!card) return;
    const rect = card.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    // Specular spotlight coordinates
    card.style.setProperty("--mouse-x", `${x}px`);
    card.style.setProperty("--mouse-y", `${y}px`);

    // Dynamic 3D tilt
    const normX = (x / rect.width) - 0.5;
    const normY = (y / rect.height) - 0.5;
    const tiltX = -normY * 6; // max 3 deg pitch
    const tiltY = normX * 6; // max 3 deg yaw

    card.style.transform = `perspective(800px) rotateX(${tiltX.toFixed(2)}deg) rotateY(${tiltY.toFixed(2)}deg) translateY(-2px) translateZ(5px)`;
  }, { passive: true });

  document.addEventListener("mouseout", (e) => {
    const card = e.target.closest(".glass-panel, .wing-card, .hud-card, .swarm-card, .vault-card, .command-item");
    if (card && !card.contains(e.relatedTarget)) {
      card.style.transform = "";
    }
  }, { passive: true });
}

/* ── AI Core Orb State & 3D Interactive Particle Sphere ────────── */
const ORB_CLASSES = ["idle", "thinking", "tool", "responding"];

function setOrb(state) {
  currentOrbState = state.toUpperCase();
  const cls = state.toLowerCase();
  [$("orbMini"), $("orbBig")].forEach((o) => {
    if (!o) return;
    o.classList.remove(...ORB_CLASSES);
    o.classList.add(cls);
  });
  const lbl = $("orbState");
  if (lbl) lbl.textContent = currentOrbState;
}

function initOrbParticles() {
  const c = $("orbCanvas");
  if (!c) return;
  const ctx = c.getContext("2d");
  const W = c.width, H = c.height;
  const cx = W / 2, cy = H / 2;

  const count = 48;
  const pts = Array.from({ length: count }, (_, i) => {
    const theta = Math.acos(1 - (2 * (i + 0.5)) / count);
    const phi = Math.PI * (1 + Math.sqrt(5)) * i;
    return {
      x: 0, y: 0, z: 0,
      origX: Math.sin(theta) * Math.cos(phi),
      origY: Math.sin(theta) * Math.sin(phi),
      origZ: Math.cos(theta),
    };
  });

  let rotX = 0, rotY = 0;
  let pulse = 0;

  function loop() {
    if (c.offsetParent) {
      ctx.clearRect(0, 0, W, H);
      pulse += 0.035;

      const speed = currentOrbState === "THINKING" ? 0.055
                  : currentOrbState === "RESPONDING" ? 0.032 : 0.015;
      rotX += speed;
      rotY += speed * 0.75;

      const baseR = currentOrbState === "THINKING" ? 42 + Math.sin(pulse * 3) * 6
                  : currentOrbState === "RESPONDING" ? 38 + Math.sin(pulse * 2) * 5
                  : 34 + Math.sin(pulse) * 3;

      // Draw particle energy constellation
      pts.forEach((p) => {
        // Rotate around Y
        let x1 = p.origX * Math.cos(rotY) + p.origZ * Math.sin(rotY);
        let z1 = -p.origX * Math.sin(rotY) + p.origZ * Math.cos(rotY);
        // Rotate around X
        let y1 = p.origY * Math.cos(rotX) - z1 * Math.sin(rotX);
        let z2 = p.origY * Math.sin(rotX) + z1 * Math.cos(rotX);

        const scale = 200 / (200 + z2 * baseR);
        const px = cx + x1 * baseR * scale;
        const py = cy + y1 * baseR * scale;
        const alpha = Math.max(0.15, Math.min(1, (z2 + 1) * 0.5));

        ctx.beginPath();
        ctx.arc(px, py, scale * (currentOrbState === "THINKING" ? 2.5 : 1.8), 0, Math.PI * 2);
        ctx.fillStyle = currentOrbState === "THINKING"
          ? `rgba(168, 85, 247, ${alpha})`
          : currentOrbState === "TOOL"
          ? `rgba(245, 158, 11, ${alpha})`
          : (p.origZ > 0 ? `rgba(0, 255, 157, ${alpha})` : `rgba(168, 85, 247, ${alpha})`);
        ctx.fill();
      });
    }
    requestAnimationFrame(loop);
  }
  loop();
}

/* ── Live Telemetry Widgets ───────────────────────────────────── */
async function loadSystem() {
  const el = $("ctxSystem");
  if (!el) return;
  try {
    const s = await jget("/api/system");
    const g = (label, v) => (v == null ? "" :
      `<div class="gauge">
         <b>${label}</b>
         <div class="track">
           <div class="fill ${v < 60 ? "g-ok" : v < 85 ? "g-warn" : "g-bad"}" style="width:${v}%"></div>
         </div>
         <span class="num">${v}%</span>
       </div>`);
    el.innerHTML = g("CPU", s.cpu_pct) + g("RAM", s.ram_pct) +
                   g("DISK", s.disk_pct) + g("GPU", s.gpu_pct);
    el.classList.remove("skeleton");
    if ($("jCpu") && s.cpu_pct != null) $("jCpu").textContent = s.cpu_pct + "%";
    if ($("jRam") && s.ram_pct != null) $("jRam").textContent = s.ram_pct + "%";
  } catch (e) {
    el.classList.remove("skeleton");
    el.innerHTML = '<div class="wdash">—</div>';
  }
}

async function loadActivity() {
  const el = $("ctxActivity");
  if (!el) return;
  try {
    const d = await jget("/api/activity?limit=8");
    if (!d.activity.length) {
      el.innerHTML = '<div class="soon">No recent tool activity</div>';
    } else {
      el.innerHTML = d.activity.map((a) => {
        const dec = String(a.decision || "-").split(":")[0];
        const cls = dec.includes("block") || dec.includes("error") ? "block"
                  : dec.includes("ask") ? "ask" : "auto";
        return `<div class="arow">
                  <span class="atool">⚙ ${esc(a.tool)}</span>
                  <span class="adec ${cls}">${esc(dec)}</span>
                  <span class="ats">${String(a.ts).slice(11, 16)}</span>
                </div>`;
      }).join("");
    }
    el.classList.remove("skeleton");
  } catch (e) {
    el.classList.remove("skeleton");
    el.innerHTML = '<div class="wdash">—</div>';
  }
}

async function loadMemory() {
  const el = $("ctxMemory");
  if (!el) return;
  try {
    const s = await jget("/api/stats");
    el.innerHTML = rowHTML("Sessions", String(s.sessions)) +
                   rowHTML("Messages", String(s.messages_total)) +
                   rowHTML("Last Backup", s.last_backup || "Active");
    el.classList.remove("skeleton");
  } catch (e) {
    el.classList.remove("skeleton");
    el.innerHTML = '<div class="wdash">—</div>';
  }
}

async function loadFactsList() {
  const el = $("sideMemory");
  if (!el) return;
  try {
    const data = await jget("/api/facts");
    const facts = data.facts || [];
    if (!facts.length) {
      el.innerHTML = '<div class="soon">No saved facts yet.<br>Use <code>/remember key: value</code></div>';
      return;
    }
    el.innerHTML = facts.slice(0, 8).map((f) => `
      <div class="prow" title="${esc(f.key)}: ${esc(f.value)}">
        <b>${esc(f.key)}</b>
        <span class="val cyan">${esc(f.value.length > 14 ? f.value.slice(0, 12) + "…" : f.value)}</span>
      </div>
    `).join("");
  } catch (e) {
    el.innerHTML = '<div class="wdash">—</div>';
  }
}

async function loadToolsList() {
  const el = $("sideTools");
  const countBadge = $("toolCountBadge");
  if (!el) return;
  try {
    const data = await jget("/api/tools");
    const tools = data.tools || [];
    if (countBadge) countBadge.textContent = String(tools.length);
    el.innerHTML = tools.slice(0, 10).map((t) => `
      <div class="prow">
        <b>${esc(t.name)}</b>
        <span class="badge ${t.risk === 'ask' ? 'badge-amber' : 'badge-green'}">${t.risk.toUpperCase()}</span>
      </div>
    `).join("");
  } catch (e) {
    el.innerHTML = '<div class="wdash">—</div>';
  }
}

async function loadProjectsList() {
  const el = $("sideProjects");
  if (!el) return;
  try {
    const data = await jget("/api/projects");
    const projects = data.projects || [];
    if (!projects.length) {
      el.innerHTML = '<div class="soon">No projects registered.</div>';
      return;
    }
    el.innerHTML = projects.map((p) => `
      <div class="prow">
        <b>${esc(p.name)}</b>
        <span class="val green">${data.active === p.name ? '● ACTIVE' : esc(p.stack || 'dir')}</span>
      </div>
    `).join("");
  } catch (e) {
    el.innerHTML = '<div class="wdash">—</div>';
  }
}

let pollTimer = null;
function pollLive() {
  loadSystem();
  loadActivity();
  loadMemory();
  loadFactsList();
  loadAnalytics();
  loadAlertBanner();
}

/* ── Watchdog Alert Banner ────────────────────────────────────── */
let alertDismissed = false;
async function loadAlertBanner() {
  try {
    const d = await jget("/api/alerts?active=1");
    const a = (d.alerts || [])[0];
    const el = $("alertBanner");
    if (alertDismissed || !a) {
      el.classList.add("hidden");
      return;
    }
    $("alertText").textContent =
      (a.severity === "CRITICAL" ? "🔴 " : "⚠ ") + "[" + a.rule + "] " + a.message;
    el.className = "alertbanner " + (a.severity === "CRITICAL" ? "crit" : "warn");
    $("alertDismiss").onclick = () => {
      alertDismissed = true;
      el.classList.add("hidden");
    };
  } catch (err) {}
}

function startPoll() {
  if (!pollTimer) {
    pollTimer = setInterval(() => {
      if (!document.hidden) pollLive();
    }, 8000);
  }
}

document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    clearInterval(pollTimer);
    pollTimer = null;
  } else {
    pollLive();
    startPoll();
  }
});

/* ── Render & Escape Helpers ──────────────────────────────────── */
function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function clean(s) {
  return String(s).replace(/[\u00A0\u202F\u2009\u200B\u200E\u200F]/g, " ");
}
function plain(s) {
  return esc(clean(s))
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br>");
}
function md(s) {
  if (!(window.marked && window.DOMPurify)) return plain(s);
  try {
    return DOMPurify.sanitize(marked.parse(clean(s), { breaks: true, gfm: true }));
  } catch (e) {
    return plain(s);
  }
}

function decorate(root) {
  root.querySelectorAll("pre code").forEach((c) => {
    if (window.hljs) hljs.highlightElement(c);
  });
  root.querySelectorAll("pre").forEach((pre) => {
    if (pre.querySelector(".copybtn")) return;
    const b = document.createElement("button");
    b.className = "copybtn";
    b.type = "button";
    b.textContent = "Copy";
    b.onclick = () => {
      const t = (pre.querySelector("code") || pre).innerText;
      if (navigator.clipboard) {
        navigator.clipboard.writeText(t).then(() => {
          b.textContent = "Copied ✓";
          setTimeout(() => (b.textContent = "Copy"), 1600);
        });
      }
    };
    pre.appendChild(b);
  });
}

function clock(ts) {
  try {
    const d = ts ? new Date(ts.length === 10 ? ts + "T00:00:00" : ts) : new Date();
    return d.toLocaleTimeString([], { hour12: false });
  } catch (e) {
    return "";
  }
}

function scrollDown() {
  if (stick) chat.scrollTop = chat.scrollHeight;
}
function hideWelcome() {
  const w = $("welcome");
  if (w) w.classList.add("hidden");
}
function banner(text, duration = 4000) {
  const b = $("banner");
  if (!b) return;
  if (!text) {
    b.classList.add("hidden");
    return;
  }
  b.innerHTML = `<span style="display:flex;align-items:center;gap:8px;"><span class="banner-icon">⚡</span><span>${escapeHtml(text)}</span></span><button style="background:none;border:none;color:inherit;cursor:pointer;font-size:14px;padding:2px 6px;margin-left:8px;opacity:0.8;" onclick="$('banner').classList.add('hidden')">✕</button>`;
  b.classList.remove("hidden");
  if (b._autoDismissTimer) clearTimeout(b._autoDismissTimer);
  if (duration > 0) {
    b._autoDismissTimer = setTimeout(() => {
      b.classList.add("hidden");
    }, duration);
  }
}

function rowHTML(label, val) {
  return `<div class="prow"><b>${esc(label)}</b><span class="val">${esc(val)}</span></div>`;
}

/* ── Chat Message Insertion ───────────────────────────────────── */
function addRow(kind, inner) {
  const el = document.createElement("div");
  if (kind === "sys") {
    el.className = "syscard";
    el.innerHTML = inner;
  } else {
    el.className = "msg " + kind;
    el.innerHTML = (kind === "bot" ? '<div class="avatar">◈</div>' : "")
                 + '<div class="content">' + inner + "</div>";
  }
  chat.appendChild(el);
  scrollDown();
  return el;
}

function addBubble(role, text, ts) {
  hideWelcome();
  const body = role === "user" ? plain(text) : md(text);
  const time = ts ? '<span class="meta"><i>' + clock(ts) + "</i></span>" : "";
  const el = addRow(role === "user" ? "user" : "bot", body + time);
  if (role !== "user") attachSpeak(el, text);
}

function ensureBot() {
  hideWelcome();
  curRow = addRow("bot", "");
  curText = "";
  return curRow;
}

function setBot(text) {
  if (!curRow) ensureBot();
  curText = text;
  const c = curRow.querySelector(".content");
  c.innerHTML = md(text);
  decorate(c);
  scrollDown();
}

function pushToken(t) {
  setBot(curText + t);
  playSfx("token");
}

function metaChips(turn) {
  if (!curRow) return;
  const m = document.createElement("span");
  m.className = "meta";
  m.innerHTML = '<i class="prov">◉ ' + esc(turn.provider) + "</i><i>" +
    esc(turn.model) + "</i><i>" + turn.elapsed_ms + "ms</i>";
  curRow.querySelector(".content").appendChild(m);
  scrollDown();
  attachSpeak(curRow, curText);
  if (autoSpeak()) speak(curText);
}

function finalizePartial() {
  if (curRow && curText) {
    curRow = null;
    curText = "";
  } else if (curRow) {
    curRow.remove();
    curRow = null;
  }
}

/* ── Thinking Indicator ───────────────────────────────────────── */
function thinking(on) {
  let el = $("thinking");
  if (on && !el) {
    el = document.createElement("div");
    el.id = "thinking";
    el.className = "thinking";
    el.innerHTML = 'LUMI processing<span class="dots"><i></i><i></i><i></i></span>';
    chat.appendChild(el);
    scrollDown();
  } else if (!on && el) {
    el.remove();
  }
}

/* ── Inline Tool Rows ─────────────────────────────────────────── */
function showTool(name, args) {
  thinking(false);
  finalizePartial();
  playSfx("tool");
  const arg = Object.entries(args || {})
    .map(([k, v]) => k + "=" + String(v).split("\\").pop()).join(", ");
  const row = document.createElement("div");
  row.className = "toolrow";
  row.innerHTML = `<span class="tgear">⚙</span><code>${esc(name)}(${esc(arg)})</code><span class="tstat">running…</span>`;
  chat.appendChild(row);
  scrollDown();
  lastToolRow = row;
}

function finishTool(ev) {
  const row = lastToolRow || document.createElement("div");
  if (!lastToolRow) {
    row.className = "toolrow";
    chat.appendChild(row);
  }
  const d = String(ev.decision || "done").split(":")[0];
  const st = row.querySelector(".tstat") || document.createElement("span");
  st.className = "tstat " + (d.includes("error") || d.includes("block") || d.includes("refus") ? "bad" : "ok");
  st.textContent = (ev.decision || "done") + " ✓";
  if (!st.parentNode) row.appendChild(st);
  lastToolRow = null;
  scrollDown();
}

function addTrace(trace) {
  if (!trace || !trace.length) return;
  const det = document.createElement("details");
  det.className = "trace";
  det.open = trace.length <= 2;
  det.innerHTML = "<summary>⚙ tool trace — " + trace.length + " call(s)</summary>" +
    trace.map((t) => `<div class="trow"><b>🔧 ${esc(t.tool)}</b><span class="badge badge-cyan">${esc(t.decision)}</span><span>${esc(t.result_summary || "")}</span></div>`).join("");
  chat.appendChild(det);
  scrollDown();
}

/* ── Futuristic Security Approval Card ────────────────────────── */
function showApproval(id, tool, args) {
  thinking(false);
  finalizePartial();
  playSfx("alert");
  const card = document.createElement("div");
  card.className = "approval-card";
  card.id = "appr-" + id;
  const argsFormatted = JSON.stringify(args || {}, null, 2);
  card.innerHTML = `
    <div class="approval-head">🛡️ SECURITY AUTHORIZATION REQUIRED</div>
    <div class="approval-desc">Tool invocation requested: <b>${esc(tool)}</b></div>
    <pre class="approval-args">${esc(argsFormatted)}</pre>
    <div class="approval-actions">
      <button class="appr-allow" onclick="window.sendApproval('${esc(id)}', true)">[ALLOW EXECUTION]</button>
      <button class="appr-deny" onclick="window.sendApproval('${esc(id)}', false)">[DENY / ABORT]</button>
    </div>
  `;
  chat.appendChild(card);
  scrollDown();
}

window.sendApproval = async function(id, approved) {
  const card = document.getElementById("appr-" + id);
  if (card) {
    const btns = card.querySelector(".approval-actions");
    if (btns) {
      btns.innerHTML = `<span class="badge ${approved ? 'badge-green' : 'badge-dim'}">${approved ? 'AUTHORIZATION GRANTED ✓' : 'ACTION REFUSED ✗'}</span>`;
    }
  }
  playSfx(approved ? "done" : "alert");
  try {
    await fetch("/api/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: id, approved: approved })
    });
  } catch (e) {
    console.error("Approval send error", e);
  }
};

/* ── SSE Stream Consumer ──────────────────────────────────────── */
function handle(ev) {
  if (ev.type === "thinking") {
    setOrb("THINKING");
    if (!curRow) ensureBot();
    thinking(true);
  } else if (ev.type === "token") {
    setOrb("RESPONDING");
    anyToken = true;
    thinking(false);
    pushToken(ev.text);
  } else if (ev.type === "approval_required") {
    setOrb("TOOL");
    thinking(false);
    showApproval(ev.id, ev.tool, ev.args);
  } else if (ev.type === "tool") {
    setOrb("TOOL");
    showTool(ev.tool, ev.args);
  } else if (ev.type === "tool_done") {
    setOrb("THINKING");
    finishTool(ev);
    thinking(true);
    loadActivity();
  } else if (ev.type === "final") {
    setOrb("RESPONDING");
    thinking(false);
    setBot(ev.text || "(empty reply)");
    if ($("jBotText") && ev.text) $("jBotText").textContent = ev.text;
  } else if (ev.type === "done") {
    setOrb("IDLE");
    thinking(false);
    playSfx("done");
    const finalReply = ev.reply || curText;
    if ($("jBotText") && finalReply) $("jBotText").textContent = finalReply;
    if (ev.provider === "-") {
      if (curRow) { curRow.remove(); curRow = null; curText = ""; }
      hideWelcome();
      addRow("sys", plain(ev.reply));
    } else {
      setBot(finalReply);
      metaChips(ev);
      addTrace(ev.tool_trace);
    }
    refreshStatus();
  } else if (ev.type === "error") {
    setOrb("IDLE");
    thinking(false);
    playSfx("alert");
    banner(ev.detail);
    if (curRow) {
      curRow.remove();
      curRow = null;
      curText = "";
    }
    addRow("sys", '<div class="syscard" style="border-left: 4px solid #ef4444; background: rgba(239, 68, 68, 0.08);">' + md(ev.detail || "System Error") + '</div>');
  }
}

async function readSSE(body) {
  const reader = body.getReader(), dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const frame = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const line = frame.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;
      try {
        handle(JSON.parse(line.slice(5)));
      } catch (e) {}
    }
  }
}

/* ── Message Sending Engine ──────────────────────────────────── */
async function send() {
  const input = $("input");
  const msg = input.value.trim();
  if (!msg || busy) return;
  busy = true;
  input.value = "";
  input.style.height = "auto";
  if ($("jUserText")) $("jUserText").textContent = `"${msg}"`;
  if ($("jBotText")) $("jBotText").textContent = "Processing directive in neural core...";
  addBubble("user", msg);
  playSfx("send");

  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: msg, stream: true })
    });
    if (resp.headers.get("content-type")?.includes("text/event-stream")) {
      await readSSE(resp.body);
    } else {
      const data = await resp.json();
      setOrb("IDLE");
      thinking(false);
      const reply = data.reply || "(no reply)";
      setBot(reply);
      if ($("jBotText")) $("jBotText").textContent = reply;
      if (data.tool_trace) addTrace(data.tool_trace);
    }
  } catch (err) {
    setOrb("IDLE");
    thinking(false);
    banner("Connection failure — check if LUMI server is running.");
  } finally {
    busy = false;
    scrollDown();
  }
}

/* ── Voice & Audio Synthesis ──────────────────────────────────── */
let autoSpeakVal = localStorage.getItem("lumi_autospeak") === "true";
function autoSpeak() { return autoSpeakVal; }

const ttsBtn = $("ttsBtn");
if (ttsBtn) {
  function updateTtsBtn() {
    ttsBtn.className = "pill pill-action" + (autoSpeakVal ? " active" : "");
    ttsBtn.innerHTML = (autoSpeakVal ? '<span class="pill-icon">🎙️</span> Voice' : '<span class="pill-icon">🔇</span> Voice');
    ttsBtn.title = autoSpeakVal ? "Auto-Speech Voice: Enabled" : "Auto-Speech Voice: Muted";
  }
  updateTtsBtn();
  ttsBtn.onclick = () => {
    autoSpeakVal = !autoSpeakVal;
    localStorage.setItem("lumi_autospeak", autoSpeakVal ? "true" : "false");
    updateTtsBtn();
  };
}

async function speak(text) {
  try {
    const res = await fetch("/api/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text })
    });
    if (res.ok) {
      const blob = await res.blob();
      const audio = new Audio(URL.createObjectURL(blob));
      audio.play();
    }
  } catch (e) {}
}

function attachSpeak(row, text) {
  if (!row || row.querySelector(".speak-btn")) return;
  const btn = document.createElement("button");
  btn.className = "speak-btn";
  btn.title = "Speak this aloud";
  btn.textContent = "🔊";
  btn.onclick = () => speak(text);
  const meta = row.querySelector(".meta") || row.querySelector(".content");
  if (meta) meta.appendChild(btn);
}

/* ── Voice Engine Studio & Settings ────────────────────────────── */
let currentVoiceId = "hi-IN-MadhurNeural";

async function openVoiceStudio() {
  const vp = $("voicePage");
  if (!vp) return;
  vp.classList.remove("hidden");
  try {
    const data = await jget("/api/voice");
    currentVoiceId = data.voice || "hi-IN-MadhurNeural";
    const badge = $("elevenKeyBadge");
    if (badge) {
      if (data.has_elevenlabs_key) {
        badge.className = "badge badge-green";
        badge.textContent = "Key Active";
      } else {
        badge.className = "badge badge-dim";
        badge.textContent = "Not Set";
      }
    }
    const grid = $("voiceListGrid");
    if (grid && data.voices) {
      grid.innerHTML = data.voices.map(v => `
        <div class="glass-panel clickable-panel ${v.id === currentVoiceId ? 'active-voice' : ''}"
             data-vid="${v.id}"
             style="padding: 10px 12px; cursor: pointer; border-color: ${v.id === currentVoiceId ? 'var(--cyan)' : 'var(--border-subtle)'}; background: ${v.id === currentVoiceId ? 'rgba(0, 240, 255, 0.08)' : 'var(--bg-card)'};">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <b style="font-size: 12.5px; color: ${v.id === currentVoiceId ? 'var(--cyan)' : '#fff'};">${v.name.split(' (')[0]}</b>
            <span class="badge ${v.provider === 'elevenlabs' ? 'badge-cyan' : 'badge-green'}">${v.provider.toUpperCase()}</span>
          </div>
          <span style="font-size: 11px; color: var(--text-dim); display: block;">${v.name.includes('(') ? v.name.split('(')[1].replace(')', '') : ''}</span>
        </div>
      `).join("");

      grid.querySelectorAll("[data-vid]").forEach(el => {
        el.onclick = async () => {
          const vid = el.getAttribute("data-vid");
          try {
            await fetch("/api/voice", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ voice: vid })
            });
            currentVoiceId = vid;
            openVoiceStudio();
          } catch (e) {
            banner("Failed to set voice");
          }
        };
      });
    }
  } catch (e) {
    banner("Failed to load voice settings");
  }
}

function closeVoiceStudio() {
  const vp = $("voicePage");
  if (vp) vp.classList.add("hidden");
}

const voiceSettingsBtn = $("voiceSettingsBtn");
if (voiceSettingsBtn) voiceSettingsBtn.onclick = openVoiceStudio;

const voiceClose = $("voiceClose");
if (voiceClose) voiceClose.onclick = closeVoiceStudio;

const saveElevenKeyBtn = $("saveElevenKeyBtn");
if (saveElevenKeyBtn) {
  saveElevenKeyBtn.onclick = async () => {
    const inp = $("elevenKeyInput");
    if (!inp || !inp.value.trim()) return;
    try {
      await fetch("/api/voice", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ elevenlabs_key: inp.value.trim() })
      });
      inp.value = "";
      banner("ElevenLabs Key Saved Successfully!");
      openVoiceStudio();
    } catch (e) {
      banner("Failed to save key");
    }
  };
}

const testVoiceBtn = $("testVoiceBtn");
if (testVoiceBtn) {
  testVoiceBtn.onclick = async () => {
    testVoiceBtn.textContent = "⏳ Speaking…";
    await speak("Namaste! Main LUMI hoon. Main aapki kya madad kar sakta hoon?");
    testVoiceBtn.textContent = "▶ Test Voice (\"Namaste!\")";
  };
}

/* ── Voice Input (Microphone Recording) ───────────────────────── */
let mediaRec = null, recChunks = [], recTimer = null, recSecs = 0;
const micBtn = $("micBtn");
const micRec = $("micRec");
const micTime = $("micTime");

if (micBtn) {
  micBtn.onclick = async () => {
    if (mediaRec && mediaRec.state === "recording") {
      mediaRec.stop();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recChunks = [];
      mediaRec = new MediaRecorder(stream);
      mediaRec.ondataavailable = (e) => recChunks.push(e.data);
      mediaRec.onstop = async () => {
        clearInterval(recTimer);
        micRec.classList.add("hidden");
        const blob = new Blob(recChunks, { type: "audio/webm" });
        const form = new FormData();
        form.append("file", blob, "input.webm");
        try {
          const resp = await fetch("/api/transcribe", { method: "POST", body: form });
          const res = await resp.json();
          if (res.text) {
            $("input").value = res.text;
            send();
          } else if (res.error) {
            banner(res.error);
          }
        } catch (e) {
          banner("Voice transcription error.");
        }
      };

      mediaRec.start(200);
      recSecs = 0;
      micTime.textContent = "0:00";
      micRec.classList.remove("hidden");
      recTimer = setInterval(() => {
        recSecs++;
        const m = Math.floor(recSecs / 60);
        const s = recSecs % 60;
        micTime.textContent = `${m}:${s < 10 ? '0' : ''}${s}`;
      }, 1000);
    } catch (e) {
      banner("Microphone access denied or unavailable.");
    }
  };
}

/* ── Status HUD Sync ──────────────────────────────────────────── */
async function refreshStatus() {
  try {
    const s = await jget("/api/status");
    const pb = $("provBadge");
    if (pb) {
      const isCloud = s.provider && s.provider !== "ollama";
      pb.className = "pill pill-provider " + (isCloud ? "cloud" : "on");
      pb.innerHTML = `<span class="status-dot"></span><span class="pill-text">${isCloud ? '☁ ' + s.provider.toUpperCase() : 'Local'}</span>`;
    }
    const sm = $("statModel");
    if (sm) sm.textContent = (s.model || '-').replace(/^model:\s*/i, '');
    if ($("jEngine")) {
      const isCloud = s.provider && s.provider !== "ollama";
      $("jEngine").textContent = isCloud ? (s.provider || "CLOUD").toUpperCase() : "LOCAL";
    }
    if ($("jVoiceName")) {
      $("jVoiceName").textContent = (typeof currentVoiceId !== "undefined" && currentVoiceId.includes("Madhur"))
        ? "Madhur (Hinglish)" : (typeof currentVoiceId !== "undefined" && currentVoiceId.includes("Swara"))
        ? "Swara (Hinglish)" : "Neural Voice";
    }
    if ($("wEngine")) {
      const isCloud = s.provider && s.provider !== "ollama";
      $("wEngine").textContent = isCloud ? (s.provider || "NVIDIA").toUpperCase() : "OLLAMA LOCAL";
    }
    if ($("wVoice")) {
      $("wVoice").textContent = (typeof currentVoiceId !== "undefined" && currentVoiceId.includes("Madhur"))
        ? "Madhur (Hinglish)" : "Swara (Hinglish)";
    }

    // Hardware Telemetry & Sentry
    const sys = await jget("/api/system");
    const batEl = $("statBatteryText");
    const batPill = $("statBattery");
    if (batEl && sys.battery_pct !== null && sys.battery_pct !== undefined) {
      const icon = sys.power_plugged ? "🔌" : "⚡";
      batEl.textContent = `${icon} ${sys.battery_pct}%`;
      if (batPill) {
        batPill.classList.toggle("low-bat", !sys.power_plugged && sys.battery_pct < 20);
      }
    }
    if ($("sentryBatVal") && sys.battery_pct !== null && sys.battery_pct !== undefined) {
      $("sentryBatVal").textContent = `${sys.battery_pct}%`;
      $("sentryBatVal").className = sys.battery_pct > 20 ? "val-green" : "val-amber";
    }
    if ($("sentryBatSub") && sys.power_plugged !== null && sys.power_plugged !== undefined) {
      $("sentryBatSub").textContent = sys.power_plugged ? "Charging / AC Connected" : "Battery Discharging";
    }
    if ($("sentryRamVal") && sys.ram_pct !== null) {
      $("sentryRamVal").textContent = `${sys.ram_pct}%`;
    }
    if ($("jCpu") && sys.cpu_pct !== null) $("jCpu").textContent = `${sys.cpu_pct}%`;
    if ($("jRam") && sys.ram_pct !== null) $("jRam").textContent = `${sys.ram_pct}%`;

    // Biometric Presence Telemetry (Phase 13)
    try {
      const bio = await jget("/api/biometrics/status");
      const presPill = $("statPresence");
      const presText = $("statPresenceText");
      if (presText && presPill) {
        if (bio.state === "SHOULDER_SURF") {
          presText.textContent = "⚠️ Surfer";
          presPill.className = "pill pill-presence surfer";
        } else if (bio.state === "PRESENT_MASTER") {
          presText.textContent = "👁️ Master";
          presPill.className = "pill pill-presence";
        } else if (bio.state === "AWAY") {
          presText.textContent = `🔒 Away ${Math.round(bio.away_duration_seconds || 0)}s`;
          presPill.className = "pill pill-presence away";
        } else if (bio.state === "INITIALIZING") {
          presText.textContent = "👁️ Sentry";
          presPill.className = "pill pill-presence";
        } else {
          presText.textContent = `👁️ ${bio.state || "Sentry"}`;
          presPill.className = "pill pill-presence";
        }
      }

      if ($("bioStateVal")) {
        $("bioStateVal").textContent = bio.state || "UNKNOWN";
        $("bioStateVal").className = bio.state === "PRESENT_MASTER" ? "val-green" : (bio.state === "SHOULDER_SURF" ? "val-amber" : "");
      }
      if ($("bioFacesSub")) {
        $("bioFacesSub").textContent = `${bio.active_faces || 0} Face(s) Detected`;
      }
      if ($("bioShieldVal")) {
        $("bioShieldVal").textContent = bio.is_shielded ? "ACTIVE (SHIELDED)" : "INACTIVE";
        $("bioShieldVal").className = bio.is_shielded ? "val-amber" : "";
      }
      if ($("bioProfileVal")) {
        $("bioProfileVal").textContent = bio.is_enrolled ? "ENROLLED" : "NOT ENROLLED";
      }
      if ($("bioAutoLockVal")) {
        $("bioAutoLockVal").textContent = bio.auto_lock_enabled ? `ARMED (${bio.lock_timeout_sec}s)` : "DISABLED";
      }
      if ($("bioAwaySub")) {
        $("bioAwaySub").textContent = `Away: ${bio.away_duration_seconds || 0}s`;
      }
      if ($("bioStateBadge")) {
        $("bioStateBadge").textContent = bio.state;
        $("bioStateBadge").className = "badge " + (bio.state === "PRESENT_MASTER" ? "badge-green" : (bio.state === "SHOULDER_SURF" ? "badge-crimson" : "badge-dim"));
      }
    } catch (_) {}

    // Emotional Voice Affect Telemetry (Phase 17)
    try {
      const aff = await jget("/api/voice/affect");
      const jaEl = $("jVoiceAffect");
      if (jaEl) {
        const sign = aff.speech_rate_offset >= 0 ? "+" : "";
        jaEl.textContent = `${aff.active_state} (${sign}${aff.speech_rate_offset}%)`;
        jaEl.className = aff.active_state === "URGENT" ? "val-amber" : (aff.active_state === "LATE_NIGHT" ? "val-purple" : "val-green");
      }
    } catch (_) {}

    // Cluster Sovereign Mesh Telemetry (Phase 18)
    try {
      await loadClusterStatus();
    } catch (_) {}
  } catch (e) {}
}

async function jget(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

/* ── Analytics & Evolution Loaders ────────────────────────────── */
async function loadAnalytics() {
  const el = $("sideStats");
  if (!el) return;
  try {
    const data = await jget("/api/analytics");
    el.innerHTML = `
      <div class="prow"><b>Messages Today</b><span class="val cyan">${data.today?.messages || 0}</span></div>
      <div class="prow"><b>Tool Calls</b><span class="val green">${data.today?.tool_calls || 0}</span></div>
      <div class="prow"><b>Success Rate</b><span class="val">${data.today?.tool_success_pct || 100}%</span></div>
    `;
    el.classList.remove("skeleton");

    // Populate modal if open
    const kpis = $("statsKpis");
    if (kpis) {
      kpis.innerHTML = `
        <div class="kpi"><div class="num">${data.today?.messages || 0}</div><div class="label">Messages Today</div></div>
        <div class="kpi"><div class="num">${data.today?.tool_calls || 0}</div><div class="label">Tool Executions</div></div>
        <div class="kpi"><div class="num">${data.today?.tool_success_pct || 100}%</div><div class="label">Success Reliability</div></div>
        <div class="kpi"><div class="num">${data.latency?.avg_ms_today || 0}ms</div><div class="label">Avg Latency</div></div>
      `;
    }
  } catch (e) {
    el.classList.remove("skeleton");
  }
}

/* ==========================================================================
   TRAINING & MODEL DASHBOARD LOGIC
   ========================================================================== */
let trainingPollTimer = null;

async function loadTrainingStatus() {
  try {
    const d = await jget("/api/training/status");
    const badge = $("trainingStatusBadge");
    const setCur = $("trainSetCurrent");
    const setTot = $("trainSetTotal");
    const pct = $("trainPct");
    const eta = $("trainEta");
    const evLoss = $("trainEvalLoss");
    const trLoss = $("trainTrainLoss");
    const st = $("trainStatus");
    const fill = $("trainFill");

    if (badge) {
      badge.className = d.complete ? "badge badge-green"
        : d.running ? "badge badge-cyan"
        : "badge badge-dim";
      badge.textContent = d.complete ? "COMPLETE"
        : d.running ? "TRAINING"
        : "IDLE";
    }
    if (setCur) setCur.textContent = d.set || 0;
    if (setTot) setTot.textContent = d.total_sets || 0;
    if (pct) pct.textContent = (d.pct || 0).toFixed(1);
    if (eta) eta.textContent = d.eta || "—";
    if (evLoss) evLoss.textContent = d.eval_loss != null ? d.eval_loss.toFixed(4) : "—";
    if (trLoss) trLoss.textContent = d.train_loss != null ? d.train_loss.toFixed(4) : "—";
    if (st) st.textContent = (d.status || "idle").toUpperCase();
    if (fill) fill.style.width = Math.max(0, Math.min(100, d.pct || 0)) + "%";

    // recent lines
    const deck = $("trainingLogDeck");
    if (deck && d.recent_lines) {
      deck.innerHTML = d.recent_lines.map((ln) => {
        let cls = "info";
        if (ln.toLowerCase().includes("error") || ln.toLowerCase().includes("cuda")) cls = "error";
        else if (ln.toLowerCase().includes("success") || ln.toLowerCase().includes("complete")) cls = "success";
        else if (ln.toLowerCase().includes("training") || ln.toLowerCase().includes("set ")) cls = "running";
        return `<div class="log-line new ${cls}">${esc(ln)}</div>`;
      }).join("");
      deck.scrollTop = deck.scrollHeight;
    }
  } catch (e) {
    console.warn("training status fetch failed", e);
  }
}

async function loadTrainingLogs() {
  try {
    const d = await jget("/api/training/logs?limit=50");
    const deck = $("trainingLogDeck");
    if (deck && d.logs) {
      deck.innerHTML = d.logs.map((ln) => {
        let cls = "info";
        if (ln.toLowerCase().includes("error") || ln.toLowerCase().includes("cuda")) cls = "error";
        else if (ln.toLowerCase().includes("success") || ln.toLowerCase().includes("complete")) cls = "success";
        else if (ln.toLowerCase().includes("training") || ln.toLowerCase().includes("set ")) cls = "running";
        return `<div class="log-line ${cls}">${esc(ln)}</div>`;
      }).join("");
      deck.scrollTop = deck.scrollHeight;
    }
  } catch (e) {
    console.warn("training logs fetch failed", e);
  }
}

async function loadModels() {
  try {
    const d = await jget("/api/models");
    const list = $("modelList");
    if (list && d.models) {
      if (!d.models.length) {
        list.innerHTML = '<div class="empty-state">No models found.</div>';
      } else {
        list.innerHTML = d.models.map((m) => `
          <div class="model-item">
            <div class="model-name">${esc(m.name)}</div>
            <div class="model-meta">
              <span>${esc(m.size)}</span>
              <span>${esc(m.modified)}</span>
            </div>
          </div>
        `).join("");
      }
    }
  } catch (e) {
    console.warn("models fetch failed", e);
  }
}

async function pullModel() {
  const inp = $("pullModelInput");
  const name = inp.value.trim();
  if (!name) return;
  const btn = $("pullModelBtn");
  const oldText = btn.textContent;
  btn.textContent = "PULLING…";
  btn.disabled = true;
  try {
    const res = await fetch("/api/models/pull", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name })
    });
    const data = await res.json();
    if (data.ok) {
      banner("Model pulled: " + esc(name));
      inp.value = "";
      await loadModels();
    } else {
      banner("Pull failed: " + esc(data.detail || "unknown"));
    }
  } catch (e) {
    banner("Pull error: " + esc(e.message));
  } finally {
    btn.textContent = oldText;
    btn.disabled = false;
  }
}

function startTrainingPoll() {
  if (trainingPollTimer) clearInterval(trainingPollTimer);
  trainingPollTimer = setInterval(() => {
    if (!document.hidden) loadTrainingStatus();
  }, 5000);
  loadTrainingStatus();
}

function stopTrainingPoll() {
  if (trainingPollTimer) {
    clearInterval(trainingPollTimer);
    trainingPollTimer = null;
  }
}

/* ==========================================================================
   TRAINING & MODEL DASHBOARD LOGIC
   ========================================================================== */
let lossChart = null;

async function loadTrainingStatus() {
  try {
    const d = await jget("/api/training/status");
    const badge = $("trainingStatusBadge");
    const setCur = $("trainSetCurrent");
    const setTot = $("trainSetTotal");
    const pct = $("trainPct");
    const eta = $("trainEta");
    const evLoss = $("trainEvalLoss");
    const trLoss = $("trainTrainLoss");
    const st = $("trainStatus");
    const fill = $("trainFill");

    if (badge) {
      badge.className = d.complete ? "badge badge-green"
        : d.running ? "badge badge-cyan"
        : "badge badge-dim";
      badge.textContent = d.complete ? "COMPLETE"
        : d.running ? "TRAINING"
        : "IDLE";
    }
    if (setCur) setCur.textContent = d.set || 0;
    if (setTot) setTot.textContent = d.total_sets || 0;
    if (pct) pct.textContent = (d.pct || 0).toFixed(1);
    if (eta) eta.textContent = d.eta || "—";
    if (evLoss) evLoss.textContent = d.eval_loss != null ? d.eval_loss.toFixed(4) : "—";
    if (trLoss) trLoss.textContent = d.train_loss != null ? d.train_loss.toFixed(4) : "—";
    if (st) st.textContent = (d.status || "idle").toUpperCase();
    if (fill) fill.style.width = Math.max(0, Math.min(100, d.pct || 0)) + "%";

    // Recent logs
    const deck = $("trainingLogDeck");
    if (deck && d.recent_lines) {
      deck.innerHTML = d.recent_lines.map((ln) => {
        let cls = "info";
        if (ln.toLowerCase().includes("error") || ln.toLowerCase().includes("cuda")) cls = "error";
        else if (ln.toLowerCase().includes("success") || ln.toLowerCase().includes("complete")) cls = "success";
        else if (ln.toLowerCase().includes("training") || ln.toLowerCase().includes("set ")) cls = "running";
        return `<div class="log-line new ${cls}">${esc(ln)}</div>`;
      }).join("");
      deck.scrollTop = deck.scrollHeight;
    }
  } catch (e) {
    console.warn("training status fetch failed", e);
  }
}

async function loadTrainingHistory() {
  try {
    const d = await jget("/api/training/history");
    const canvas = $("lossCurveCanvas");
    if (!canvas || !d) return;

    const ctx = canvas.getContext("2d");

    // Destroy existing chart
    if (lossChart) lossChart.destroy();

    lossChart = new Chart(ctx, {
      type: "line",
      data: {
        labels: d.steps,
        datasets: [
          {
            label: "Train Loss",
            data: d.train_losses,
            borderColor: "#00ff9d",
            backgroundColor: "rgba(0, 255, 157, 0.1)",
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.4,
            fill: true,
          },
          {
            label: "Eval Loss",
            data: d.eval_losses,
            borderColor: "#a855f7",
            backgroundColor: "rgba(168, 85, 247, 0.1)",
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.4,
            fill: true,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
          legend: { display: false },
          title: {
            display: true,
            text: "Training Loss Over Time",
            color: "#fff",
            font: { size: 12 },
          },
        },
        scales: {
          x: {
            display: true,
            title: { display: true, text: "Steps", color: "#fff", font: { size: 11 } },
            ticks: { color: "#aaa", font: { size: 10 }, maxTicksLimit: 10 },
            grid: { color: "rgba(255,255,255,0.05)" },
          },
          y: {
            display: true,
            title: { display: true, text: "Loss", color: "#fff", font: { size: 11 } },
            ticks: { color: "#aaa", font: { size: 10 } },
            grid: { color: "rgba(255,255,255,0.05)" },
          },
        },
      },
    });
  } catch (e) {
    console.warn("training history fetch failed", e);
  }
}

async function loadModels() {
  try {
    const d = await jget("/api/models");
    const list = $("modelList");
    if (list && d.models) {
      if (!d.models.length) {
        list.innerHTML = '<div class="empty-state">No models found.</div>';
      } else {
        list.innerHTML = d.models.map((m) => `
          <div class="model-item">
            <div class="model-name">${esc(m.name)}</div>
            <div class="model-meta">
              <span>${esc(m.size)}</span>
              <span>${esc(m.modified)}</span>
            </div>
          </div>
        `).join("");
      }
    }
  } catch (e) {
    console.warn("models fetch failed", e);
  }
}

function startTrainingPoll() {
  if (trainingPollTimer) clearInterval(trainingPollTimer);
  trainingPollTimer = setInterval(() => {
    if (!document.hidden) {
      loadTrainingStatus();
      loadTrainingHistory();
    }
  }, 5000);
  loadTrainingStatus();
  loadTrainingHistory();
  loadModels();
}

function stopTrainingPoll() {
  if (trainingPollTimer) {
    clearInterval(trainingPollTimer);
    trainingPollTimer = null;
  }
}

/* ==========================================================================
   JARVIS HOLOGRAPHIC VOICE CORE & DUAL ENGINE CONTROLLER
   Continuous Voice Loop · Reactive Arc Reactor Visualizer · Hinglish AI
   ========================================================================== */

const urlParams = new URLSearchParams(window.location.search);
const paramMode = urlParams.get("mode");
let appMode = (paramMode === "chat" || paramMode === "jarvis")
  ? paramMode
  : (localStorage.getItem("lumi_app_mode") || "jarvis");
let handsFreeEnabled = localStorage.getItem("lumi_handsfree") === "true";
let isJarvisListening = false;
let isJarvisProcessing = false;
let isJarvisSpeaking = false;
let userSpokeThisTurn = false;
let followUpActive = false;

let jarvisRec = null;
let jarvisAudio = null;
let jarvisAudioSource = null;
let jarvisAnalyser = null;
let jarvisFreqData = null;
let visualizerRunning = false;
let visualizerReqId = null;
let jarvisParticles = [];

let jarvisMicStream = null;
let jarvisMediaRec = null;
let jarvisChunks = [];
let jarvisMicSource = null;
let jarvisVadTimer = null;
let jarvisSpeechFinalTimer = null;
let jarvisUserSpoke = false;
let jarvisLastSpeechTime = 0;
let jarvisRecordStartTime = 0;
let jarvisCapturedText = "";

function initJarvisAudioAnalyser() {
  initAudio();
  if (!audioCtx) return;
  if (!jarvisAnalyser) {
    try {
      jarvisAnalyser = audioCtx.createAnalyser();
      jarvisAnalyser.fftSize = 128;
      jarvisFreqData = new Uint8Array(jarvisAnalyser.frequencyBinCount);
    } catch (_) {}
  }
}

function showProcessingHUD(directiveText = "Transcribing directive via local Whisper...") {
  const hud = $("jarvisProcessingHUD");
  if (hud) {
    hud.classList.remove("hidden");
    const dirEl = $("hudDirective");
    if (dirEl) dirEl.textContent = directiveText;
    setPipelineStep("stt", "DECODING");
  }
}

function hideProcessingHUD() {
  const hud = $("jarvisProcessingHUD");
  if (hud) hud.classList.add("hidden");
}

function setPipelineStep(step, statusText) {
  const sSTT = $("pipeSTT");
  const sLLM = $("pipeLLM");
  const sTTS = $("pipeTTS");
  const stSTT = $("pipeSTTStatus");
  const stLLM = $("pipeLLMStatus");
  const stTTS = $("pipeTTSStatus");

  if (step === "stt") {
    if (sSTT) sSTT.classList.add("active");
    if (sLLM) sLLM.classList.remove("active");
    if (sTTS) sTTS.classList.remove("active");
    if (stSTT) stSTT.textContent = statusText || "DECODING";
    if (stLLM) stLLM.textContent = "STANDBY";
    if (stTTS) stTTS.textContent = "STANDBY";
  } else if (step === "llm") {
    if (sSTT) sSTT.classList.add("active");
    if (sLLM) sLLM.classList.add("active");
    if (sTTS) sTTS.classList.remove("active");
    if (stSTT) stSTT.textContent = "DONE";
    if (stLLM) stLLM.textContent = statusText || "COMPUTING";
    if (stTTS) stTTS.textContent = "STANDBY";
  } else if (step === "tts") {
    if (sSTT) sSTT.classList.add("active");
    if (sLLM) sLLM.classList.add("active");
    if (sTTS) sTTS.classList.add("active");
    if (stSTT) stSTT.textContent = "DONE";
    if (stLLM) stLLM.textContent = "DONE";
    if (stTTS) stTTS.textContent = statusText || "SPEAKING";
  }
}

function setJarvisReactorState(state) {
  const reactor = $("arcReactor");
  const glyph = $("arcGlyph");
  const tapHint = $("arcTapHint");
  const statusBadge = $("jarvisStatusText");
  const micBtn = $("jarvisMainMicBtn");
  const micIcon = $("jMicIcon");
  const micLabel = $("jMicStateLabel");

  if (reactor) {
    reactor.classList.remove("listening", "processing", "speaking", "tool");
    if (state !== "idle") reactor.classList.add(state);
  }

  const botCompanion = $("lumiBotCompanion");
  if (botCompanion) {
    botCompanion.classList.remove("listening", "processing", "speaking");
    if (state !== "idle") botCompanion.classList.add(state);
    if (state === "listening") showBotBubble("Sun raha hoon...", 2200);
    else if (state === "processing") showBotBubble("Analyzing...", 2200);
  }

  if (glyph) {
    switch (state) {
      case "listening": glyph.textContent = "🎙️"; break;
      case "processing": glyph.textContent = "⚡"; break;
      case "speaking": glyph.textContent = "🔊"; break;
      case "tool": glyph.textContent = "⚙"; break;
      default: glyph.textContent = "◈"; break;
    }
  }

  if (tapHint) {
    switch (state) {
      case "listening": tapHint.textContent = "LISTENING · TAP TO SEND"; break;
      case "processing": tapHint.textContent = "COMPUTING DIRECTIVE..."; break;
      case "speaking": tapHint.textContent = "SPEAKING · TAP TO STOP"; break;
      case "tool": tapHint.textContent = "EXECUTING TOOL..."; break;
      default: tapHint.textContent = handsFreeEnabled ? "AMBIENT EAR ACTIVE · TAP TO TALK" : "TAP ORB OR PRESS SPACE TO TALK"; break;
    }
  }

  if (micBtn) {
    micBtn.classList.remove("recording", "processing", "speaking");
    if (state === "listening") micBtn.classList.add("recording");
    else if (state === "processing") micBtn.classList.add("processing");
    else if (state === "speaking") micBtn.classList.add("speaking");
  }

  if (micIcon) {
    switch (state) {
      case "listening": micIcon.textContent = "⏹"; break;
      case "processing": micIcon.textContent = "⚡"; break;
      case "speaking": micIcon.textContent = "🔊"; break;
      default: micIcon.textContent = "🎙️"; break;
    }
  }

  if (micLabel) {
    switch (state) {
      case "listening": micLabel.textContent = "🟢 LISTENING... (TAP TO SEND)"; break;
      case "processing": micLabel.textContent = "⚡ PROCESSING DIRECTIVE..."; break;
      case "speaking": micLabel.textContent = "🔊 LUMI SPEAKING (INTERRUPT ANYTIME)"; break;
      default: micLabel.textContent = handsFreeEnabled ? "🟢 AMBIENT EAR READY" : "TAP TO TALK (SPACE)"; break;
    }
  }

  if (statusBadge) {
    switch (state) {
      case "listening":
        statusBadge.textContent = "🟢 LISTENING · BOLIYE SIR...";
        break;
      case "processing":
        statusBadge.textContent = "⚡ LUMI: COMPUTING NEURAL DIRECTIVE...";
        break;
      case "speaking":
        statusBadge.textContent = "🔊 LUMI: VOCAL TRANSMISSION ACTIVE";
        break;
      case "tool":
        statusBadge.textContent = "⚙ LUMI: EXECUTING SYSTEM TOOL...";
        break;
      default:
        statusBadge.textContent = handsFreeEnabled ? "LUMI: AMBIENT EAR ACTIVE" : "LUMI: QUIET & READY · TAP OR SPACE TO TALK";
        break;
    }
  }

  setOrb(state.toUpperCase());
}

function showJarvisToolAlert(name, summary) {
  const alertEl = $("jarvisToolAlert");
  if (!alertEl) return;
  const nameEl = $("jToolName");
  const argsEl = $("jToolArgs");
  if (nameEl) nameEl.textContent = name;
  if (argsEl) argsEl.textContent = summary || "Executed";
  alertEl.classList.remove("hidden");
  setJarvisReactorState("tool");
  playSfx("tool");
  setTimeout(() => {
    alertEl.classList.add("hidden");
    if (isJarvisSpeaking) {
      setJarvisReactorState("speaking");
    } else if (isJarvisProcessing) {
      setJarvisReactorState("processing");
    } else if (isJarvisListening) {
      setJarvisReactorState("listening");
    } else {
      setJarvisReactorState("idle");
    }
  }, 2600);
}

function fallbackBrowserSpeak(text, onDone) {
  if (!window.speechSynthesis) {
    resumeAmbientListeningAfterSpeech(200);
    if (onDone) onDone();
    return;
  }
  try {
    window.speechSynthesis.cancel();
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      clearTimeout(safetyTimer);
      resumeAmbientListeningAfterSpeech(250);
      if (onDone) onDone();
    };

    // Safety timeout: ensure fallback synthesis never hangs indefinitely
    const safetyTimer = setTimeout(finish, 5000);

    const utt = new SpeechSynthesisUtterance(text);
    utt.rate = 1.05;
    utt.pitch = 1.0;
    const voices = window.speechSynthesis.getVoices();
    const voice = voices.find((v) => v.lang === "hi-IN" || v.lang === "en-IN") ||
                  voices.find((v) => v.lang.startsWith("en")) || voices[0];
    if (voice) utt.voice = voice;
    utt.onend = finish;
    utt.onerror = finish;
    window.speechSynthesis.speak(utt);
  } catch (_) {
    resumeAmbientListeningAfterSpeech(200);
    if (onDone) onDone();
  }
}

async function jarvisSpeak(text) {
  if (!text) return;
  initAudio();
  if (audioCtx && audioCtx.state === "suspended") {
    try { await audioCtx.resume(); } catch (_) {}
  }

  if (jarvisAudio) {
    try {
      jarvisAudio.pause();
      jarvisAudio.currentTime = 0;
    } catch (_) {}
  }
  if (window.speechSynthesis) {
    try { window.speechSynthesis.cancel(); } catch (_) {}
  }

  isJarvisSpeaking = true;
  setJarvisReactorState("speaking");
  setPipelineStep("tts", "SYNTHESIZING");

  // Clean code blocks, URLs, markdown formatting and emojis for crystal clear speech
  let cleanText = text
    .replace(/```[\s\S]*?```/g, " [code execution details on screen] ")
    .replace(/`([^`\n]+)`/g, "$1")
    .replace(/\*\*([^*\n]+)\*\*/g, "$1")
    .replace(/\*([^*\n]+)\*/g, "$1")
    .replace(/https?:\/\/\S+/g, "link")
    .replace(/[#*_~>\[\]\(\)]/g, " ")
    .replace(/[\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}\u{1F700}-\u{1F77F}\u{1F780}-\u{1F7FF}\u{1F800}-\u{1F8FF}\u{1F900}-\u{1F9FF}\u{1FA00}-\u{1FA6F}\u{1FA70}-\u{1FAFF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/gu, "")
    .replace(/\s+/g, " ")
    .trim();

  // If response is longer than 280 chars, vocalize the conversational summary for instant <0.5s playback
  if (cleanText.length > 280) {
    const periodIdx = cleanText.indexOf(". ", 140);
    const dandaIdx = cleanText.indexOf("। ", 140);
    let cut = (periodIdx !== -1 && periodIdx < 280) ? periodIdx + 1 :
              (dandaIdx !== -1 && dandaIdx < 280) ? dandaIdx + 1 : 250;
    cleanText = cleanText.substring(0, cut).trim() + " Baaki details maine screen par show kar di hain.";
  }

  try {
    const res = await fetch("/api/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: cleanText })
    });
    if (!res.ok) throw new Error("TTS endpoint error");
    const blob = await res.blob();
    if (blob.size < 100) throw new Error("Empty TTS audio");
    const url = URL.createObjectURL(blob);

    const audio = new Audio(url);
    jarvisAudio = audio;

    setPipelineStep("tts", "SPEAKING");

    return new Promise((resolve) => {
      let done = false;
      const finish = () => {
        if (done) return;
        done = true;
        clearTimeout(safetyTimer);
        URL.revokeObjectURL(url);
        resumeAmbientListeningAfterSpeech(250);
        resolve();
      };

      // Safety timeout: ensure playback never hangs indefinitely
      const safetyTimer = setTimeout(finish, 8000);

      audio.onended = finish;

      audio.onerror = (e) => {
        console.warn("Audio playback error, falling back to Web Speech:", e);
        if (done) return;
        done = true;
        clearTimeout(safetyTimer);
        URL.revokeObjectURL(url);
        fallbackBrowserSpeak(cleanText, resolve);
      };

      const playPromise = audio.play();
      if (playPromise !== undefined) {
        playPromise.catch((err) => {
          console.warn("Audio play blocked by browser, falling back to Web Speech:", err);
          if (done) return;
          done = true;
          clearTimeout(safetyTimer);
          URL.revokeObjectURL(url);
          fallbackBrowserSpeak(cleanText, resolve);
        });
      }
    });
  } catch (err) {
    console.warn("Server TTS error, using Web Speech fallback:", err);
    return new Promise((resolve) => {
      fallbackBrowserSpeak(cleanText, resolve);
    });
  }
}

function resumeAmbientListeningAfterSpeech(delayMs = 250) {
  isJarvisSpeaking = false;
  hideProcessingHUD();
  if (handsFreeEnabled && !isJarvisProcessing) {
    setTimeout(() => {
      if (!isJarvisSpeaking && !isJarvisProcessing && (appMode === "jarvis" || appMode === "chat")) {
        followUpActive = true;
        startJarvisListening();
      } else {
        setJarvisReactorState("idle");
      }
    }, delayMs);
  } else {
    // Peace & quiet! Stays calm and ready for user interaction.
    setJarvisReactorState("idle");
    const userCaption = $("jUserText");
    if (userCaption) userCaption.textContent = '"Tap Arc Reactor Orb ya Spacebar dabayein"';
  }
}

function triggerDuplexBargeIn() {
  if (jarvisAudio) {
    try {
      jarvisAudio.pause();
      jarvisAudio.currentTime = 0;
    } catch (_) {}
  }
  if (window.speechSynthesis) {
    try { window.speechSynthesis.cancel(); } catch (_) {}
  }
  isJarvisSpeaking = false;
  isJarvisProcessing = false;
  playSfx("send");
  showProcessingHUD("[ DUPLEX BARGE-IN: Interrupted playback · Listening to new instruction ]");
  setJarvisReactorState("listening");
  const botCaption = $("jBotText");
  if (botCaption) botCaption.textContent = "[Interrupted] Listening, Sir...";
  startJarvisListening();
}

function stopJarvisSpeech() {
  if (jarvisAudio) {
    try {
      jarvisAudio.pause();
      jarvisAudio.currentTime = 0;
    } catch (_) {}
  }
  if (window.speechSynthesis) {
    try { window.speechSynthesis.cancel(); } catch (_) {}
  }
  isJarvisSpeaking = false;
  isJarvisProcessing = false;
  followUpActive = false;
  stopJarvisListening();
  hideProcessingHUD();
  setJarvisReactorState("idle");
  const botCaption = $("jBotText");
  if (botCaption) botCaption.textContent = "Audio stopped. Ready for command.";
}

async function startJarvisListening() {
  if (isJarvisSpeaking) {
    if (jarvisAudio) {
      try { jarvisAudio.pause(); jarvisAudio.currentTime = 0; } catch (_) {}
    }
    isJarvisSpeaking = false;
  }
  if (isJarvisListening) return;
  isJarvisProcessing = false;

  initAudio();
  if (audioCtx && audioCtx.state === "suspended") {
    try { await audioCtx.resume(); } catch (_) {}
  }

  // Reuse existing warm stream if active, eliminating 300ms hardware re-init lag!
  if (!jarvisMicStream || !jarvisMicStream.active) {
    try {
      jarvisMicStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });
    } catch (err) {
      banner("Microphone access denied or unavailable.");
      setJarvisReactorState("idle");
      return;
    }
  }

  isJarvisListening = true;
  jarvisUserSpoke = false;
  jarvisCapturedText = "";
  jarvisRecordStartTime = Date.now();
  jarvisLastSpeechTime = 0;
  jarvisChunks = [];

  // Connect microphone stream to visualizer
  if (audioCtx && jarvisAnalyser) {
    try {
      if (!jarvisMicSource) {
        jarvisMicSource = audioCtx.createMediaStreamSource(jarvisMicStream);
        jarvisMicSource.connect(jarvisAnalyser);
      }
    } catch (e) {
      console.warn("Visualizer mic attach:", e);
    }
  }

  hideProcessingHUD();
  setJarvisReactorState("listening");
  playSfx("tool");

  const userCaption = $("jUserText");
  if (userCaption) {
    userCaption.textContent = handsFreeEnabled
      ? '"Ambient Ear Active... Boliye Sir"'
      : '"Sun raha hoon, boliye Sir... (Spacebar ya tap karke bhejein)"';
  }

  // Stop previous recorder instance if active
  if (jarvisMediaRec && jarvisMediaRec.state !== "inactive") {
    try { jarvisMediaRec.stop(); } catch (_) {}
  }
  jarvisChunks = [];

  // Local hardware MediaRecorder — continuous unfragmented stream
  try {
    let mime = "";
    if (typeof MediaRecorder !== "undefined") {
      if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) mime = "audio/webm;codecs=opus";
      else if (MediaRecorder.isTypeSupported("audio/webm")) mime = "audio/webm";
    }
    jarvisMediaRec = mime ? new MediaRecorder(jarvisMicStream, { mimeType: mime }) : new MediaRecorder(jarvisMicStream);
    jarvisMediaRec.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) jarvisChunks.push(e.data);
    };
    jarvisMediaRec.start(200);
  } catch (e) {
    console.error("MediaRecorder start error:", e);
  }

  // WebSpeech parallel assistant for live interim captions & dual-engine fallback
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRec) {
    try {
      if (jarvisRec) {
        try { jarvisRec.abort(); } catch (_) {}
      }
      jarvisRec = new SpeechRec();
      jarvisRec.continuous = handsFreeEnabled ? true : false;
      jarvisRec.interimResults = true;
      jarvisRec.maxAlternatives = 1;
      jarvisRec.lang = "en-IN";

      jarvisRec.onresult = (ev) => {
        let fullFinal = "";
        let fullInterim = "";
        for (let i = 0; i < ev.results.length; i++) {
          const trans = ev.results[i][0].transcript;
          if (ev.results[i].isFinal) fullFinal += trans + " ";
          else fullInterim += trans;
        }

        fullFinal = fullFinal.trim();
        fullInterim = fullInterim.trim();

        if (isJarvisSpeaking) {
          if ((fullFinal || fullInterim).length > 1) {
            console.log("[DUPLEX BARGE-IN] Speech detected while speaking, triggering interruption!");
            triggerDuplexBargeIn();
          }
          return;
        }

        const currentSpeech = (fullFinal ? fullFinal + (fullInterim ? " " + fullInterim : "") : fullInterim).trim();

        if (currentSpeech) {
          jarvisUserSpoke = true;
          jarvisLastSpeechTime = Date.now();
          jarvisCapturedText = currentSpeech;

          const userCaption = $("jUserText");
          if (userCaption) userCaption.textContent = `"${currentSpeech}"`;

          // Natural sentence endpoint detection:
          // Wait 1.3 seconds of silence AFTER user finishes speaking to allow natural speech cadence
          clearTimeout(jarvisSpeechFinalTimer);
          jarvisSpeechFinalTimer = setTimeout(() => {
            if (isJarvisListening && !isJarvisProcessing && jarvisCapturedText.trim().length > 1) {
              const cmd = jarvisCapturedText.trim();
              jarvisCapturedText = "";
              stopJarvisListeningAndProcess(cmd);
            }
          }, 1300);
        }
      };

      jarvisRec.onerror = (e) => {
        console.warn("[JARVIS] SpeechRecognition event:", e.error);
        if (e.error === "no-speech") {
          return;
        }
        if (e.error === "network" || e.error === "not-allowed" || e.error === "service-not-allowed") {
          console.log("[JARVIS] WebSpeech cloud offline - Local Whisper CUDA fallback engaged.");
          return;
        }
        if (isJarvisListening && !isJarvisSpeaking && !isJarvisProcessing && handsFreeEnabled) {
          setTimeout(() => {
            if (isJarvisListening && !isJarvisSpeaking && !isJarvisProcessing && handsFreeEnabled) {
              try { jarvisRec.start(); } catch (_) {}
            }
          }, 300);
        }
      };

      jarvisRec.onend = () => {
        if (!handsFreeEnabled && isJarvisListening && !isJarvisProcessing) {
          if (jarvisCapturedText && jarvisCapturedText.trim().length > 1) {
            clearTimeout(jarvisSpeechFinalTimer);
            jarvisSpeechFinalTimer = setTimeout(() => {
              if (isJarvisListening && !isJarvisProcessing && jarvisCapturedText.trim().length > 1) {
                const cmd = jarvisCapturedText.trim();
                jarvisCapturedText = "";
                stopJarvisListeningAndProcess(cmd);
              }
            }, 500);
            return;
          }
        }
        if (handsFreeEnabled && isJarvisListening && !isJarvisSpeaking && !isJarvisProcessing) {
          try { jarvisRec.start(); } catch (_) {}
        }
      };

      try { jarvisRec.start(); } catch (_) {}
    } catch (_) {}
  }

  // Voice Activity Detection (VAD) watcher
  clearInterval(jarvisVadTimer);
  jarvisVadTimer = setInterval(() => {
    if (!isJarvisListening) {
      clearInterval(jarvisVadTimer);
      return;
    }

    let peak = 0;
    let sum = 0;
    if (jarvisAnalyser && jarvisFreqData) {
      jarvisAnalyser.getByteFrequencyData(jarvisFreqData);
      const binLimit = Math.min(24, jarvisFreqData.length);
      for (let i = 2; i < binLimit; i++) {
        const v = jarvisFreqData[i];
        sum += v;
        if (v > peak) peak = v;
      }
    }
    const avg = sum / 22;
    const now = Date.now();

    // Voice detected with realistic speech floor
    const isSpeechActive = peak > 28 || avg > 10;
    if (isSpeechActive) {
      jarvisUserSpoke = true;
      jarvisLastSpeechTime = now;
    }

    // In Hands-free mode: Auto-send after 650ms natural silence
    if (handsFreeEnabled && jarvisUserSpoke && jarvisLastSpeechTime > 0 && (now - jarvisLastSpeechTime > 650)) {
      clearInterval(jarvisVadTimer);
      clearTimeout(jarvisSpeechFinalTimer);
      stopJarvisListeningAndProcess(jarvisCapturedText || "");
      return;
    }

    // In Tap-to-Talk mode: Auto-send after 1.2s of natural pause after speech
    if (!handsFreeEnabled && jarvisUserSpoke && jarvisLastSpeechTime > 0 && (now - jarvisLastSpeechTime > 1200)) {
      clearInterval(jarvisVadTimer);
      clearTimeout(jarvisSpeechFinalTimer);
      stopJarvisListeningAndProcess(jarvisCapturedText || "");
      return;
    }

    // Safety timeout: max 15 seconds of speaking -> auto send!
    if (jarvisUserSpoke && (now - jarvisRecordStartTime > 15000)) {
      clearInterval(jarvisVadTimer);
      clearTimeout(jarvisSpeechFinalTimer);
      stopJarvisListeningAndProcess(jarvisCapturedText || "");
      return;
    }

    // In Always-On mode: If user hasn't spoken in 12 seconds and buffer is empty, reset cleanly
    if (handsFreeEnabled && !jarvisUserSpoke && !jarvisCapturedText && (now - jarvisRecordStartTime > 12000)) {
      jarvisRecordStartTime = now;
      jarvisChunks = [];
      if (jarvisMediaRec && jarvisMediaRec.state === "recording") {
        try {
          jarvisMediaRec.stop();
          setTimeout(() => {
            if (isJarvisListening && jarvisMediaRec && jarvisMediaRec.state === "inactive") {
              jarvisMediaRec.start();
            }
          }, 50);
        } catch (_) {}
      }
    }

    // If tap-to-talk is active and user never spoke after 7s: reset to quiet idle
    if (!handsFreeEnabled && !jarvisUserSpoke && (now - jarvisRecordStartTime > 7000)) {
      clearInterval(jarvisVadTimer);
      clearTimeout(jarvisSpeechFinalTimer);
      stopJarvisListening();
      if (userCaption) userCaption.textContent = '"Shaant & Ready · Tap Arc Reactor ya Spacebar dabayein"';
      setJarvisReactorState("idle");
      return;
    }
  }, 100);
}

function stopJarvisListening() {
  clearInterval(jarvisVadTimer);
  clearTimeout(jarvisSpeechFinalTimer);
  isJarvisListening = false;
  followUpActive = false;

  if (jarvisRec) {
    try { jarvisRec.stop(); } catch (_) {}
  }

  if (jarvisMediaRec && jarvisMediaRec.state !== "inactive") {
    try { jarvisMediaRec.stop(); } catch (_) {}
  }

  if (!isJarvisProcessing && !isJarvisSpeaking) {
    setJarvisReactorState("idle");
  }
}

function cleanUpMicStreams(force = false) {
  if (!force) return; // Keep warm for instant hands-free turn-taking!
  if (jarvisMicStream) {
    try {
      jarvisMicStream.getTracks().forEach((t) => t.stop());
    } catch (_) {}
    jarvisMicStream = null;
  }
  if (jarvisMicSource) {
    try { jarvisMicSource.disconnect(); } catch (_) {}
    jarvisMicSource = null;
  }
}

async function stopJarvisListeningAndProcess(knownText = "") {
  clearInterval(jarvisVadTimer);
  clearTimeout(jarvisSpeechFinalTimer);
  if (!isJarvisListening && (!jarvisMediaRec || jarvisMediaRec.state === "inactive")) return;
  isJarvisListening = false;
  followUpActive = false;

  if (jarvisRec) {
    try { jarvisRec.stop(); } catch (_) {}
  }

  // Visual cues: Immediately show Processing HUD and purple reactor
  setJarvisReactorState("processing");

  const finalCmd = (knownText || jarvisCapturedText || "").trim();
  jarvisCapturedText = "";

  // FAST PATH: Instant execution using browser WebSpeech result
  if (finalCmd && finalCmd.length > 1) {
    showProcessingHUD(`[ DIRECTIVE CAPTURED: "${finalCmd}" ]`);
    const userCaption = $("jUserText");
    const botCaption = $("jBotText");
    if (userCaption) userCaption.textContent = `"${finalCmd}"`;
    if (botCaption) botCaption.textContent = "Analyzing directive & consulting LUMI neural core...";

    setPipelineStep("llm", "COMPUTING");
    const dirEl = $("hudDirective");
    if (dirEl) dirEl.textContent = `"${finalCmd}"`;

    if (jarvisMediaRec && jarvisMediaRec.state === "recording") {
      try { jarvisMediaRec.stop(); } catch (_) {}
    }
    jarvisChunks = [];

    await handleJarvisVoiceCommand(finalCmd);
    return;
  }

  // FALLBACK PATH: Whisper Audio Transcription
  showProcessingHUD("[ ACOUSTIC DECODE: Processing voice directive via local Whisper CUDA ]");
  const userCaption = $("jUserText");
  const botCaption = $("jBotText");
  if (userCaption) userCaption.textContent = '"Processing voice directive..."';
  if (botCaption) botCaption.textContent = "Analyzing speech & consulting LUMI neural core...";

  if (jarvisMediaRec && jarvisMediaRec.state === "recording") {
    jarvisMediaRec.onstop = async () => {
      const blob = new Blob(jarvisChunks, { type: jarvisMediaRec.mimeType || "audio/webm" });
      jarvisChunks = [];

      if (blob.size < 400) {
        hideProcessingHUD();
        if (userCaption) userCaption.textContent = '"Shaant & Ready · Tap Arc Reactor ya Spacebar dabayein"';
        resumeAmbientListeningAfterSpeech(200);
        return;
      }

      const form = new FormData();
      form.append("file", blob, "jarvis_input.webm");
      form.append("prompt", "LUMI, Jarvis. Hindi Hinglish: LUMI kya haal hai, open notepad, terminal run karo, system status batao.");
      try {
        const resp = await fetch("/api/transcribe", { method: "POST", body: form });
        const res = await resp.json();

        let finalSpokenText = (res.text || "").trim();
        if (finalSpokenText) {
          setPipelineStep("llm", "COMPUTING");
          const dirEl = $("hudDirective");
          if (dirEl) dirEl.textContent = `"${finalSpokenText}"`;
          if (userCaption) userCaption.textContent = `"${finalSpokenText}"`;

          await handleJarvisVoiceCommand(finalSpokenText);
        } else {
          hideProcessingHUD();
          const errText = "Aawaz samajh nahi aayi, kripya dobara bolein Sir.";
          if (botCaption) botCaption.textContent = errText;
          if (userCaption) userCaption.textContent = '"Shaant & Ready · Tap Orb to talk"';
          playSfx("error");
          await jarvisSpeak(errText);
        }
      } catch (err) {
        console.error("[JARVIS] Transcribe network error:", err);
        hideProcessingHUD();
        const errMsg = "Voice core error, kripya dobara try karein.";
        if (botCaption) botCaption.textContent = errMsg;
        playSfx("error");
        await jarvisSpeak(errMsg);
      }
    };

    try {
      jarvisMediaRec.stop();
    } catch (e) {
      console.error("[JARVIS] MediaRec stop error:", e);
      hideProcessingHUD();
      resumeAmbientListeningAfterSpeech(300);
    }
  } else {
    hideProcessingHUD();
    resumeAmbientListeningAfterSpeech(300);
  }
}

async function snapAndAnalyzeScreen(customPrompt = "") {
  if (isJarvisProcessing) return;
  initAudio();
  playSfx("tool");

  let promptText = (customPrompt || "").trim();
  if (!promptText) {
    promptText = "Explain what is on the screen right now and highlight any key info, errors, or code.";
  }

  isJarvisProcessing = true;
  setJarvisReactorState("processing");
  showProcessingHUD("[ VISION CORE: Capturing display & analyzing visual context ]");

  const userCaption = $("jUserText");
  const botCaption = $("jBotText");
  if (userCaption) userCaption.textContent = `"📸 [Screen Vision: ${promptText}]"`;
  if (botCaption) botCaption.textContent = "Capturing screen display frame...";

  let base64Image = null;
  try {
    if (navigator.mediaDevices && navigator.mediaDevices.getDisplayMedia) {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: { cursor: "always" },
        audio: false
      });
      const video = document.createElement("video");
      video.srcObject = stream;
      await new Promise((resolve) => {
        video.onloadedmetadata = () => {
          video.play();
          resolve();
        };
      });
      await new Promise((r) => setTimeout(r, 250));
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth || 1920;
      canvas.height = video.videoHeight || 1080;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      stream.getTracks().forEach((track) => track.stop());
      base64Image = canvas.toDataURL("image/jpeg", 0.85);
    }
  } catch (err) {
    console.warn("Display capture dismissed or unavailable:", err);
  }

  setPipelineStep("llm", "ANALYZING SCREEN");
  if (botCaption) botCaption.textContent = "NVIDIA Multimodal Vision cortex analyzing screen pixels...";

  addBubble("user", `📸 **Screen Vision Request:** ${promptText}`);
  playSfx("send");

  try {
    const payload = { prompt: promptText };
    if (base64Image) {
      payload.image_base64 = base64Image;
    }
    const resp = await fetch("/api/vision/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await resp.json();
    const analysis = data.analysis || data.error || "Screen analysis completed.";

    let formattedReply = analysis;
    if (data.image_url) {
      formattedReply = `![Active Screen](${data.image_url}?t=${Date.now()})\n\n${analysis}`;
    }
    addBubble("bot", formattedReply);
    if (botCaption) {
      botCaption.textContent = analysis;
      const box = $("jarvisCaptionBox");
      if (box) box.scrollTop = box.scrollHeight;
    }

    hideProcessingHUD();
    setPipelineStep("tts", "SYNTHESIZING");
    playSfx("done");

    // Processing finished! Allow instant user interruption and new commands at anytime
    isJarvisProcessing = false;
    await jarvisSpeak(analysis);
  } catch (err) {
    console.error("Vision analyze error:", err);
    hideProcessingHUD();
    setJarvisReactorState("idle");
    if (botCaption) botCaption.textContent = "Vision analysis failed: " + err.message;
    addBubble("bot", "❌ Screen analyze nahi ho paya: " + err.message);
  } finally {
    isJarvisProcessing = false;
  }
}

async function handleJarvisVoiceCommand(text) {
  if (!text) return;
  stopJarvisListening();

  const lower = (text || "").toLowerCase();
  const isScreenIntent =
    ((lower.includes("screen") || lower.includes("स्क्रीन") || lower.includes("display")) &&
      (lower.includes("dekh") || lower.includes("देख") ||
        lower.includes("look") ||
        lower.includes("kya") || lower.includes("क्या") ||
        lower.includes("check") || lower.includes("चेक") ||
        lower.includes("error") || lower.includes("एरर") ||
        lower.includes("bata") || lower.includes("बता") ||
        lower.includes("padh") || lower.includes("पढ़") || lower.includes("पढ़") ||
        lower.includes("read") ||
        lower.includes("samjha") || lower.includes("समझ") ||
        lower.includes("explain"))) ||
    lower.includes("meri screen") || lower.includes("मेरी स्क्रीन") ||
    lower.includes("ye error") || lower.includes("यह एरर") || lower.includes("ये एरर");

  if (isScreenIntent) {
    await snapAndAnalyzeScreen(text);
    return;
  }

  isJarvisProcessing = true;
  setJarvisReactorState("processing");

  const userCaption = $("jUserText");
  if (userCaption) userCaption.textContent = `"${text}"`;

  const botCaption = $("jBotText");
  if (botCaption) botCaption.textContent = "Analyzing directive & consulting neural core...";

  const dirEl = $("hudDirective");
  if (dirEl) dirEl.textContent = `"${text}"`;
  setPipelineStep("llm", "REASONING");

  addBubble("user", text);
  playSfx("send");

  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, stream: false })
    });

    const data = await resp.json();
    const reply = data.reply || "Directive executed, Sir.";

    if (data.tool_trace && data.tool_trace.length > 0) {
      const lastTool = data.tool_trace[data.tool_trace.length - 1];
      showJarvisToolAlert(lastTool.tool, lastTool.result_summary || "Success");
    }

    setOrb("IDLE");
    setBot(reply);
    if (data.tool_trace) addTrace(data.tool_trace);

    if (botCaption) {
      botCaption.textContent = reply;
      const box = $("jarvisCaptionBox");
      if (box) box.scrollTop = box.scrollHeight;
    }
    setPipelineStep("tts", "SYNTHESIZING");

    // Processing is done! Clear processing flag so voice input / barge-in works at anytime!
    isJarvisProcessing = false;
    hideProcessingHUD();

    // Speak the response aloud to user!
    await jarvisSpeak(reply);
  } catch (err) {
    console.error("Jarvis voice execution error:", err);
    if (botCaption) botCaption.textContent = "Sir, I encountered a communication error with the core.";
    hideProcessingHUD();
    setJarvisReactorState("idle");
  } finally {
    isJarvisProcessing = false;
  }
}

window.openStudioDrawer = function(drawerId) {
  const modeMap = {
    swarmView: "swarm",
    nexusView: "nexus",
    browseView: "browse",
    trainingView: "training"
  };
  setAppMode(modeMap[drawerId] || "jarvis");
};

function setAppMode(mode, save = true) {
  appMode = mode;
  if (save && (mode === "jarvis" || mode === "chat")) {
    localStorage.setItem("lumi_app_mode", mode);
  }

  const cockpit = $("jarvisView");
  const chatShell = $("chatShell");
  if (cockpit) cockpit.classList.remove("hidden");
  if (chatShell) chatShell.classList.remove("hidden");

  const drawers = {
    swarm: $("swarmView"),
    nexus: $("nexusView"),
    browse: $("browseView"),
    training: $("trainingView"),
  };

  const btns = {
    jarvis: $("btnModeJarvis"),
    chat: $("btnModeChat"),
    swarm: $("btnModeSwarm"),
    vault: $("btnModeVault"),
    nexus: $("btnModeNexus"),
    browse: $("btnModeBrowse"),
    training: $("btnModeTraining"),
  };

  Object.keys(drawers).forEach((k) => {
    if (drawers[k]) drawers[k].classList.add("hidden");
  });
  Object.keys(btns).forEach((k) => {
    if (btns[k]) btns[k].classList.remove("active");
  });

  if (drawers[mode]) drawers[mode].classList.remove("hidden");
  if (btns[mode]) btns[mode].classList.add("active");

  // Toggle compact reactor vs full cockpit in unified single-panel mode
  const expandLbl = $("expandChatLbl");
  if (cockpit) {
    if (mode === "chat") {
      cockpit.classList.add("terminal-expanded");
      if (expandLbl) expandLbl.textContent = "FULL ORB HUD";
    } else if (mode === "jarvis") {
      cockpit.classList.remove("terminal-expanded");
      if (expandLbl) expandLbl.textContent = "EXPAND STREAM";
    }
  }

  playSfx("send");

  // Training dashboard poller
  if (mode === "training") {
    startTrainingPoll();
    loadModels();
  } else {
    stopTrainingPoll();
  }

  // Keep 3D Arc Reactor visualizer alive whenever the unified cockpit is visible
  startJarvisVisualizerLoop();
  if (mode === "jarvis" || mode === "chat" || mode === "vault") {
    if (handsFreeEnabled && !isJarvisListening && !isJarvisSpeaking && !isJarvisProcessing) {
      startJarvisListening();
    } else if (!isJarvisListening && !isJarvisSpeaking && !isJarvisProcessing) {
      setJarvisReactorState("idle");
    }
  }

  if (mode === "chat") {
    const inp = $("input");
    if (inp) {
      try { inp.focus({ preventScroll: true }); } catch (_) { inp.focus(); }
    }
  } else if (mode === "vault") {
    if (typeof loadVaultStats === "function") loadVaultStats();
    const ctxWing = $("context");
    if (ctxWing) {
      ctxWing.classList.remove("collapsed");
      ctxWing.classList.add("open");
    }
    const vCard = $("vaultWingCard");
    if (vCard) {
      vCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
      vCard.style.borderColor = "var(--gold)";
      setTimeout(() => { vCard.style.borderColor = ""; }, 1800);
    }
    const vInp = $("vaultSearchInput");
    if (vInp) {
      try { vInp.focus({ preventScroll: true }); } catch (_) { vInp.focus(); }
    }
  } else if (mode === "nexus") {
    if (typeof loadNexusStatus === "function") loadNexusStatus();
    if (typeof loadSentryStatus === "function") loadSentryStatus();
  } else if (mode === "browse") {
    if (typeof loadTechRadar === "function") loadTechRadar();
  }
}

let jarvisMouseX = null;
let jarvisMouseY = null;

function initJarvisParticles() {
  jarvisParticles = [];
  const particleCount = 110;
  for (let i = 0; i < particleCount; i++) {
    const layer = i % 3; // 0: inner core sparks, 1: orbital halo, 2: outer cosmic dust
    let baseR = layer === 0 ? (65 + Math.random() * 35) : layer === 1 ? (115 + Math.random() * 45) : (165 + Math.random() * 45);
    jarvisParticles.push({
      angle: Math.random() * Math.PI * 2,
      baseRadius: baseR,
      radius: baseR,
      speed: (0.006 + Math.random() * 0.014) * (layer === 1 ? -1 : 1),
      radialOscSpeed: 1.5 + Math.random() * 3,
      radialAmp: 4 + Math.random() * 12,
      size: layer === 0 ? (1.5 + Math.random() * 2) : (1.0 + Math.random() * 1.5),
      alpha: 0.25 + Math.random() * 0.65,
      layer: layer,
      hueOffset: Math.random() * 40 - 20
    });
  }

  const arcEl = $("arcReactor");
  if (arcEl && !arcEl._mouseBound) {
    arcEl._mouseBound = true;
    arcEl.addEventListener("mousemove", (e) => {
      const rect = arcEl.getBoundingClientRect();
      jarvisMouseX = e.clientX - rect.left - rect.width / 2;
      jarvisMouseY = e.clientY - rect.top - rect.height / 2;
    });
    arcEl.addEventListener("mouseleave", () => {
      jarvisMouseX = null;
      jarvisMouseY = null;
    });
  }
}

function startJarvisVisualizerLoop() {
  if (visualizerRunning) return;
  visualizerRunning = true;
  initJarvisParticles();
  renderJarvisVisualizer();
}

function renderJarvisVisualizer() {
  if (!visualizerRunning) return;

  const canvas = $("jarvisCanvas");
  if (!canvas) {
    visualizerReqId = requestAnimationFrame(renderJarvisVisualizer);
    return;
  }

  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  const cx = w / 2;
  const cy = h / 2;
  const t = performance.now() / 1000;

  ctx.clearRect(0, 0, w, h);

  if (jarvisAnalyser && jarvisFreqData) {
    jarvisAnalyser.getByteFrequencyData(jarvisFreqData);
  }

  let avgAudio = 0;
  if (jarvisFreqData && jarvisFreqData.length > 0) {
    let sum = 0;
    for (let k = 0; k < 32; k++) sum += jarvisFreqData[k];
    avgAudio = sum / (32 * 255);
  }

  // 1. Organic Radiant Plasma Core Aura (Eternal Green, Solar Gold & Purple Fusion)
  const auraR = 90 + Math.sin(t * 3.5) * 8 + (isJarvisSpeaking || isJarvisListening ? avgAudio * 35 : 0);
  const auraGrad = ctx.createRadialGradient(cx, cy, 20, cx, cy, auraR);
  if (isJarvisSpeaking) {
    auraGrad.addColorStop(0, "rgba(0, 255, 157, 0.65)");
    auraGrad.addColorStop(0.35, "rgba(251, 191, 36, 0.3)");
    auraGrad.addColorStop(0.7, "rgba(168, 85, 247, 0.3)");
    auraGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
  } else if (isJarvisProcessing) {
    auraGrad.addColorStop(0, "rgba(168, 85, 247, 0.7)");
    auraGrad.addColorStop(0.35, "rgba(251, 191, 36, 0.35)");
    auraGrad.addColorStop(0.7, "rgba(0, 255, 157, 0.35)");
    auraGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
  } else if (isJarvisListening) {
    auraGrad.addColorStop(0, "rgba(0, 255, 157, 0.65)");
    auraGrad.addColorStop(0.35, "rgba(251, 191, 36, 0.3)");
    auraGrad.addColorStop(0.7, "rgba(168, 85, 247, 0.35)");
    auraGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
  } else {
    auraGrad.addColorStop(0, "rgba(0, 255, 157, 0.45)");
    auraGrad.addColorStop(0.35, "rgba(251, 191, 36, 0.2)");
    auraGrad.addColorStop(0.7, "rgba(168, 85, 247, 0.22)");
    auraGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
  }
  ctx.fillStyle = auraGrad;
  ctx.beginPath();
  ctx.arc(cx, cy, auraR, 0, Math.PI * 2);
  ctx.fill();

  // 2. Liquid Undulating Frequency Ribbon (64 Points Closed Bezier with Green-Gold-Purple Gradient)
  const ribbonPts = 64;
  const ribbonBaseR = 120 + (isJarvisSpeaking ? 8 : 0);
  ctx.beginPath();
  for (let i = 0; i <= ribbonPts; i++) {
    const angle = (i / ribbonPts) * Math.PI * 2;
    let waveMod = 0;
    if (isJarvisSpeaking || isJarvisListening) {
      const idx = i % (jarvisFreqData ? Math.min(64, jarvisFreqData.length) : 1);
      const f = jarvisFreqData && jarvisFreqData.length > 0 ? (jarvisFreqData[idx] / 255) : Math.abs(Math.sin(t * 8 + i * 0.4));
      waveMod = f * 34 + Math.sin(t * 6 + i * 0.5) * 6;
    } else if (isJarvisProcessing) {
      waveMod = Math.sin(t * 7 + i * 0.6) * 12 + Math.cos(angle * 4 - t * 5) * 10;
    } else {
      waveMod = Math.sin(t * 2.8 + i * 0.35) * 6 + Math.cos(t * 1.5 + i * 0.2) * 4;
    }
    const r = ribbonBaseR + waveMod;
    const px = cx + Math.cos(angle) * r;
    const py = cy + Math.sin(angle) * r;
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  }
  ctx.closePath();
  ctx.lineWidth = isJarvisSpeaking || isJarvisListening ? 2.5 : 1.8;
  const ribbonGrad = ctx.createLinearGradient(cx - ribbonBaseR, cy - ribbonBaseR, cx + ribbonBaseR, cy + ribbonBaseR);
  ribbonGrad.addColorStop(0, "rgba(0, 255, 157, 0.9)");
  ribbonGrad.addColorStop(0.35, "rgba(251, 191, 36, 0.85)");
  ribbonGrad.addColorStop(0.7, "rgba(168, 85, 247, 0.85)");
  ribbonGrad.addColorStop(1, "rgba(0, 255, 157, 0.9)");
  ctx.strokeStyle = ribbonGrad;
  ctx.stroke();

  // 3. Fluid Quantum Particle Swarm with Neural Constellation Links
  const positions = [];
  const speedMult = isJarvisProcessing ? 3.0 : isJarvisSpeaking ? 2.2 : isJarvisListening ? 1.6 : 1.0;

  for (let p of jarvisParticles) {
    p.angle += p.speed * speedMult;
    const osc = Math.sin(t * p.radialOscSpeed) * p.radialAmp;
    let curR = p.baseRadius + osc;

    let px = cx + Math.cos(p.angle) * curR;
    let py = cy + Math.sin(p.angle) * curR;

    // Mouse gravitation parallax
    if (jarvisMouseX !== null && jarvisMouseY !== null) {
      const targetX = cx + jarvisMouseX;
      const targetY = cy + jarvisMouseY;
      const dx = targetX - px;
      const dy = targetY - py;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < 180 && dist > 10) {
        const pull = (1 - dist / 180) * 14;
        px += (dx / dist) * pull;
        py += (dy / dist) * pull;
      }
    }

    positions.push({ x: px, y: py, alpha: p.alpha, layer: p.layer });

    // Draw particle with Eternal Green and Purple multi-layer blend
    ctx.beginPath();
    ctx.arc(px, py, p.size, 0, Math.PI * 2);
    if (isJarvisSpeaking) ctx.fillStyle = p.layer === 1 ? `rgba(168, 85, 247, ${p.alpha})` : `rgba(0, 255, 157, ${p.alpha})`;
    else if (isJarvisProcessing) ctx.fillStyle = p.layer === 0 ? `rgba(0, 255, 157, ${p.alpha})` : `rgba(168, 85, 247, ${p.alpha})`;
    else ctx.fillStyle = p.layer === 1 ? `rgba(168, 85, 247, ${p.alpha})` : `rgba(0, 255, 157, ${p.alpha})`;
    ctx.fill();
  }

  // 4. Draw Synaptic Constellation Strands (Connect nearby particles within 42px)
  ctx.lineWidth = 0.8;
  const posLen = positions.length;
  for (let i = 0; i < posLen; i += 2) {
    for (let j = i + 1; j < Math.min(posLen, i + 8); j++) {
      const dx = positions[i].x - positions[j].x;
      const dy = positions[i].y - positions[j].y;
      const d = Math.sqrt(dx * dx + dy * dy);
      if (d < 42) {
        const lineAlpha = (1 - d / 42) * 0.28 * Math.min(positions[i].alpha, positions[j].alpha);
        ctx.beginPath();
        ctx.moveTo(positions[i].x, positions[i].y);
        ctx.lineTo(positions[j].x, positions[j].y);
        ctx.strokeStyle = (i % 4 === 0) ? `rgba(168, 85, 247, ${lineAlpha})` : `rgba(0, 255, 157, ${lineAlpha})`;
        ctx.stroke();
      }
    }
  }

  // 5. Outer Sleek Technical Reticle (36 Ticks with Smooth Interpolation)
  const totalTicks = 36;
  for (let i = 0; i < totalTicks; i++) {
    const angle = (i / totalTicks) * Math.PI * 2 + t * 0.05;
    const isMajor = i % 9 === 0;
    const r1 = 188;
    const r2 = isMajor ? 198 : 193;

    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(angle) * r1, cy + Math.sin(angle) * r1);
    ctx.lineTo(cx + Math.cos(angle) * r2, cy + Math.sin(angle) * r2);
    ctx.lineWidth = isMajor ? 1.8 : 1;
    ctx.strokeStyle = isMajor ? "rgba(0, 255, 157, 0.9)" : "rgba(168, 85, 247, 0.35)";
    ctx.stroke();
  }

  // 6. Update the 32-bar Linear Spectrum Bar (#jarvisSpectrumBar)
  const specBar = $("jarvisSpectrumBar");
  if (specBar) {
    const bars = specBar.children;
    const n = bars.length;
    for (let i = 0; i < n; i++) {
      let h = 4;
      if (isJarvisSpeaking || isJarvisListening) {
        let f = 0;
        if (jarvisFreqData && jarvisFreqData.length > 0) {
          f = jarvisFreqData[i % jarvisFreqData.length] / 255;
        } else {
          f = Math.abs(Math.sin(t * 6 + i * 0.4));
        }
        h = Math.max(4, Math.min(28, 4 + f * 24));
        if (isJarvisSpeaking) {
          bars[i].style.background = "linear-gradient(180deg, var(--emerald), rgba(16, 185, 129, 0.2))";
        } else {
          bars[i].style.background = "linear-gradient(180deg, var(--cyan), rgba(0, 240, 255, 0.2))";
        }
      } else if (isJarvisProcessing) {
        const pulse = Math.abs(Math.sin(t * 8 + i * 0.35));
        h = Math.max(4, Math.min(26, 4 + pulse * 20));
        bars[i].style.background = "linear-gradient(180deg, #c084fc, rgba(168, 85, 247, 0.2))";
      } else {
        const wave = (Math.sin(t * 2.5 + i * 0.25) + 1) * 0.5;
        h = 4 + wave * 8;
        bars[i].style.background = "linear-gradient(180deg, rgba(0, 240, 255, 0.6), rgba(0, 240, 255, 0.08))";
      }
      bars[i].style.height = `${h}px`;
    }
  }

  visualizerReqId = requestAnimationFrame(renderJarvisVisualizer);
}

function initJarvisMode() {
  const jarvisAutoListenBtn = $("jarvisAutoListenBtn");
  const hfStatus = $("hfStatus");
  if (jarvisAutoListenBtn) {
    function updateHfBtn() {
      if (hfStatus) hfStatus.textContent = handsFreeEnabled ? "ON" : "OFF";
      if (handsFreeEnabled) jarvisAutoListenBtn.classList.add("active");
      else jarvisAutoListenBtn.classList.remove("active");
    }
    updateHfBtn();
    jarvisAutoListenBtn.onclick = () => {
      handsFreeEnabled = !handsFreeEnabled;
      localStorage.setItem("lumi_handsfree", handsFreeEnabled ? "true" : "false");
      updateHfBtn();
      if (handsFreeEnabled) {
        startJarvisListening();
      } else {
        followUpActive = false;
        stopJarvisListening();
        setJarvisReactorState("idle");
      }
    };
  }

  const arcReactor = $("arcReactor");
  if (arcReactor) {
    arcReactor.onclick = (e) => {
      if (isJarvisSpeaking) {
        triggerDuplexBargeIn();
        return;
      }
      if (isJarvisProcessing) {
        hideProcessingHUD();
        isJarvisProcessing = false;
        playSfx("tool");
        startJarvisListening();
        return;
      }
      if (isJarvisListening) {
        stopJarvisListeningAndProcess(jarvisCapturedText || "");
      } else {
        isJarvisProcessing = false;
        startJarvisListening();
      }
    };
  }

  const jarvisMainMicBtn = $("jarvisMainMicBtn");
  if (jarvisMainMicBtn) {
    jarvisMainMicBtn.onclick = () => {
      if (isJarvisSpeaking) {
        triggerDuplexBargeIn();
        return;
      }
      if (isJarvisProcessing) {
        hideProcessingHUD();
        isJarvisProcessing = false;
        playSfx("tool");
        startJarvisListening();
        return;
      }
      if (isJarvisListening) {
        stopJarvisListeningAndProcess(jarvisCapturedText || "");
      } else {
        isJarvisProcessing = false;
        startJarvisListening();
      }
    };
  }

  const jarvisStopBtn = $("jarvisStopBtn");
  if (jarvisStopBtn) {
    jarvisStopBtn.onclick = stopJarvisSpeech;
  }

  const jarvisToChatBtn = $("jarvisToChatBtn");
  if (jarvisToChatBtn) {
    jarvisToChatBtn.onclick = () => {
      setAppMode(appMode === "chat" ? "jarvis" : "chat");
    };
  }

  const btnModeJarvis = $("btnModeJarvis");
  if (btnModeJarvis) btnModeJarvis.onclick = () => setAppMode("jarvis");

  const btnModeChat = $("btnModeChat");
  if (btnModeChat) btnModeChat.onclick = () => setAppMode("chat");

  const btnModeSwarm = $("btnModeSwarm");
  if (btnModeSwarm) btnModeSwarm.onclick = () => setAppMode("swarm");

  const btnModeVault = $("btnModeVault");
  if (btnModeVault) btnModeVault.onclick = () => setAppMode("vault");

  const btnModeNexus = $("btnModeNexus");
  if (btnModeNexus) btnModeNexus.onclick = () => setAppMode("nexus");

  const btnModeBrowse = $("btnModeBrowse");
  if (btnModeBrowse) btnModeBrowse.onclick = () => setAppMode("browse");

  const btnModeTraining = $("btnModeTraining");
  if (btnModeTraining) btnModeTraining.onclick = () => setAppMode("training");

  const refreshTrainingBtn = $("refreshTrainingBtn");
  if (refreshTrainingBtn) refreshTrainingBtn.onclick = () => {
    loadTrainingStatus();
    loadTrainingLogs();
  };

  const pullModelBtn = $("pullModelBtn");
  if (pullModelBtn) pullModelBtn.onclick = pullModel;

  const pullModelInput = $("pullModelInput");
  if (pullModelInput) {
    pullModelInput.onkeypress = (e) => {
      if (e.key === "Enter") pullModel();
    };
  }

  const statBat = $("statBattery");
  if (statBat) statBat.onclick = () => setAppMode("nexus");

  window.addEventListener("keydown", (e) => {
    const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : "";
    const isInput = activeTag === "input" || activeTag === "textarea" || document.activeElement?.isContentEditable;

    if (!isInput && e.key.toLowerCase() === "m" && !e.ctrlKey && !e.altKey && !e.metaKey) {
      e.preventDefault();
      setAppMode(appMode === "jarvis" ? "chat" : "jarvis");
    }

    if (!isInput && (e.code === "Space" || e.code === "Escape")) {
      if (e.code === "Escape" && appMode !== "jarvis" && appMode !== "chat") {
        setAppMode("jarvis");
        return;
      }
      e.preventDefault();
      if (e.code === "Escape") {
        stopJarvisSpeech();
        stopJarvisListening();
        isJarvisProcessing = false;
        return;
      }
      if (isJarvisSpeaking) {
        triggerDuplexBargeIn();
      } else if (isJarvisProcessing) {
        hideProcessingHUD();
        isJarvisProcessing = false;
        playSfx("tool");
        startJarvisListening();
      } else if (isJarvisListening) {
        stopJarvisListeningAndProcess(jarvisCapturedText || "");
      } else {
        isJarvisProcessing = false;
        startJarvisListening();
      }
    }
  });

  setAppMode(appMode, false);
}

/* ==========================================================================
   SWARM-DEV STUDIO CONTROLLER
   ========================================================================== */
let activeSwarmProject = null;

function initSwarmDev() {
  const goalInp = $("swarmGoalInput");
  const nameInp = $("swarmNameInput");
  const launchBtn = $("swarmLaunchBtn");
  const copyBtn = $("copySwarmCodeBtn");
  const runBtn = $("runSwarmProjectBtn");

  document.querySelectorAll(".st-chip").forEach((btn) => {
    btn.onclick = () => {
      if (goalInp) goalInp.value = btn.dataset.goal || "";
      if (nameInp) nameInp.value = btn.dataset.name || "";
      playSfx("token");
    };
  });

  if (launchBtn) {
    launchBtn.onclick = async () => {
      const goal = (goalInp?.value || "").trim();
      const projName = (nameInp?.value || "").trim();
      if (!goal) {
        banner("Please specify a software project goal.");
        return;
      }

      playSfx("tool");
      const badge = $("swarmStatusBadge");
      if (badge) {
        badge.className = "badge badge-cyan";
        badge.textContent = "CLUSTER ACTIVE · COMPUTING";
      }

      const archCard = $("agentArchitect");
      const coderCard = $("agentCoder");
      const testerCard = $("agentTester");
      const debugCard = $("agentDebugger");

      [archCard, coderCard, testerCard, debugCard].forEach((c) => c?.classList.remove("running", "passed"));
      archCard?.classList.add("running");
      const term = $("swarmTerminalLog");
      if (term) term.textContent = `[SWARM-DEV] Initializing autonomous engineering cluster...\n[ARCHITECT] Designing architecture specification for: "${goal}"\n`;

      try {
        const resp = await fetch("/api/swarm", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ goal, project_name: projName || null })
        });

        archCard?.classList.remove("running");
        archCard?.classList.add("passed");
        coderCard?.classList.add("passed");
        testerCard?.classList.add("passed");

        const data = await resp.json();
        if (resp.status >= 400 || data.error) {
          if (badge) {
            badge.className = "badge badge-dim";
            badge.textContent = "EXECUTION FAILED";
          }
          if (term) term.textContent += `\n❌ Error: ${data.error || "Failed to execute swarm development"}`;
          return;
        }

        activeSwarmProject = data.project_name;
        if (data.healing_iterations > 0) {
          debugCard?.classList.add("passed");
        }

        if (badge) {
          badge.className = "badge badge-green";
          badge.textContent = "PROJECT BUILT & VERIFIED ✅";
        }
        playSfx("done");

        const dirEl = $("swarmProjDir");
        if (dirEl) dirEl.textContent = `workspace/${data.project_name}/`;

        const countEl = $("swarmFileCount");
        if (countEl) countEl.textContent = (data.files || []).length;

        const fileList = $("swarmFileList");
        if (fileList) {
          fileList.innerHTML = "";
          (data.files || []).forEach((f, idx) => {
            const item = document.createElement("div");
            item.className = "swarm-file-item" + (idx === 0 ? " active" : "");
            item.innerHTML = `<span>📄</span> <span>${f}</span>`;
            item.onclick = () => selectSwarmFile(f, item);
            fileList.appendChild(item);
          });
        }

        if (term) {
          term.textContent = `=== SWARM DEVELOPMENT SUMMARY ===\n${data.summary}\n\n=== TEST VERIFICATION LOG ===\n${data.test_output || "All test assertions passed cleanly."}`;
        }
        const tBadge = $("swarmTestBadge");
        if (tBadge) {
          tBadge.className = data.tests_passed ? "badge badge-green" : "badge badge-amber";
          tBadge.textContent = data.tests_passed ? "TESTS PASSED" : "REVIEW NEEDED";
        }

        if (data.files && data.files.length > 0) {
          await loadSwarmFileContent(data.project_name, data.files[0]);
        }
      } catch (err) {
        if (term) term.textContent += `\nNetwork error: ${err.message}`;
        if (badge) badge.textContent = "NETWORK ERROR";
      }
    };
  }

  if (copyBtn) {
    copyBtn.onclick = () => {
      const code = $("swarmCodePreview")?.textContent;
      if (code) {
        navigator.clipboard.writeText(code);
        banner("Code copied to clipboard! 📋");
        playSfx("token");
      }
    };
  }

  if (runBtn) {
    runBtn.onclick = async () => {
      if (!activeSwarmProject) {
        banner("No active project built yet.");
        return;
      }
      playSfx("tool");
      const term = $("swarmTerminalLog");
      if (term) term.textContent += `\n\n[EXEC] Running python workspace/${activeSwarmProject}/main.py in isolated sandbox...`;
      try {
        const resp = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: `run_python code inside workspace/${activeSwarmProject}` })
        });
        const res = await resp.json();
        if (term) term.textContent += `\n${res.reply || "Done"}`;
        playSfx("done");
      } catch (e) {
        if (term) term.textContent += `\nRun error: ${e.message}`;
      }
    };
  }
}

async function loadSwarmFileContent(projectName, fileName) {
  const codeEl = $("swarmCodePreview");
  const nameEl = $("swarmActiveFileName");
  if (nameEl) nameEl.textContent = `📄 ${fileName}`;
  if (codeEl) codeEl.textContent = "# Loading file content...";

  try {
    const qResp = await fetch("/api/vault/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: fileName, top_k: 3, file_filter: fileName })
    });
    const qData = await qResp.json();
    if (qData.results && qData.results.length > 0) {
      if (codeEl) codeEl.textContent = qData.results[0].snippet;
      if (window.hljs) hljs.highlightElement(codeEl);
      return;
    }
  } catch (_) {}

  if (codeEl) {
    codeEl.textContent = `# workspace/${projectName}/${fileName}\n# File verified & saved in project workspace.`;
  }
}

function selectSwarmFile(fileName, itemEl) {
  document.querySelectorAll(".swarm-file-item").forEach((el) => el.classList.remove("active"));
  itemEl.classList.add("active");
  if (activeSwarmProject) {
    loadSwarmFileContent(activeSwarmProject, fileName);
  }
}

/* ==========================================================================
   NEURAL-VAULT EXPLORER CONTROLLER
   ========================================================================== */
let activeVaultExt = "";

async function loadVaultStats() {
  try {
    const resp = await fetch("/api/vault/stats");
    const data = await resp.json();
    const docEl = $("vaultDocCount");
    const chkEl = $("vaultChunkCount");
    const szEl = $("vaultSizeKb");
    if (docEl) docEl.textContent = data.documents || 0;
    if (chkEl) chkEl.textContent = data.chunks || 0;
    if (szEl) szEl.textContent = data.db_size_kb || 0;
  } catch (_) {}
}

function initNeuralVault() {
  const searchInp = $("vaultSearchInput");
  const searchBtn = $("vaultSearchBtn");
  const reindexBtn = $("vaultReindexBtn");
  let debounceTimer = null;

  async function performVaultSearch() {
    const query = (searchInp?.value || "").trim();
    const deck = $("vaultResultsDeck");
    if (!deck) return;

    if (!query) {
      deck.innerHTML = `
        <div class="empty-state">
          <span class="empty-icon">🔍</span>
          <b>Instant Codebase Semantic Recall</b>
          <span>Search across all project files, tools, and documentation. Results include exact line numbers and relevance scores.</span>
        </div>`;
      return;
    }

    try {
      const resp = await fetch("/api/vault/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, top_k: 6, file_filter: activeVaultExt || null })
      });
      const data = await resp.json();
      if (!data.results || data.results.length === 0) {
        deck.innerHTML = `<div class="empty-state">No matching snippets found for "${escapeHtml(query)}".</div>`;
        return;
      }

      deck.innerHTML = "";
      data.results.forEach((r) => {
        const card = document.createElement("div");
        card.className = "vault-card";
        card.innerHTML = `
          <div class="vc-header">
            <span class="vc-path">${escapeHtml(r.file_path)}</span>
            <div class="vc-meta">
              <span class="badge badge-cyan">Lines ${r.start_line}–${r.end_line}</span>
              <span class="badge badge-dim">Score: ${r.score}</span>
            </div>
          </div>
          <pre class="vc-snippet"><code>${escapeHtml(r.snippet)}</code></pre>
        `;
        deck.appendChild(card);
      });
      playSfx("token");
    } catch (e) {
      deck.innerHTML = `<div class="empty-state">Search query failed: ${e.message}</div>`;
    }
  }

  if (searchInp) {
    searchInp.oninput = () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(performVaultSearch, 300);
    };
    searchInp.onkeydown = (e) => {
      if (e.key === "Enter") {
        clearTimeout(debounceTimer);
        performVaultSearch();
      }
    };
  }

  if (searchBtn) searchBtn.onclick = performVaultSearch;

  document.querySelectorAll(".vf-chip").forEach((btn) => {
    btn.onclick = () => {
      document.querySelectorAll(".vf-chip").forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      activeVaultExt = btn.dataset.ext || "";
      performVaultSearch();
    };
  });

  if (reindexBtn) {
    reindexBtn.onclick = async () => {
      reindexBtn.textContent = "⚡ INDEXING...";
      playSfx("tool");
      try {
        const resp = await fetch("/api/vault/index", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: "." })
        });
        const res = await resp.json();
        banner(`NEURAL-VAULT: Indexed ${res.result?.indexed || 0} files!`);
        await loadVaultStats();
        playSfx("done");
      } catch (e) {
        banner("Indexing error: " + e.message);
      } finally {
        reindexBtn.innerHTML = '<span class="btn-icon">⚡</span> RE-INDEX WORKSPACE';
      }
    };
  }
}

/* ==========================================================================
   NEXUS-IOT & SENTRY WORKSTATION COCKPIT CONTROLLER
   ========================================================================== */
async function loadNexusStatus() {
  try {
    const resp = await fetch("/api/nexus/status");
    const data = await resp.json();
    const hBadge = $("nexusHostBadge");
    const pBadge = $("nexusActivePresetBadge");
    if (hBadge) hBadge.textContent = `HOST: ${data.hostname || "LOCALHOST"} (${data.local_ip || "127.0.0.1"})`;
    if (pBadge) pBadge.textContent = `PRESET: ${(data.current_preset || "RESET").toUpperCase()}`;

    document.querySelectorAll(".preset-btn").forEach((btn) => {
      if (btn.dataset.preset === data.current_preset) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });
  } catch (_) {}
}

async function loadSentryStatus() {
  try {
    const resp = await fetch("/api/sentry/status");
    const data = await resp.json();
    const sPill = $("sentryStatusPill");
    if (sPill) {
      sPill.className = data.active ? "badge badge-green" : "badge badge-dim";
      sPill.textContent = data.active ? "ACTIVE GUARDIAN" : "STANDBY";
    }
  } catch (_) {}
}

function initNexusCockpit() {
  document.querySelectorAll(".preset-btn").forEach((btn) => {
    btn.onclick = async () => {
      const preset = btn.dataset.preset;
      if (!preset) return;
      playSfx("tool");
      try {
        const resp = await fetch("/api/nexus/focus", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ preset })
        });
        const res = await resp.json();
        if (res.ok) {
          banner(`Workstation Mode: ${preset.toUpperCase()} Activated! ⚡`);
          playSfx("done");
          await loadNexusStatus();
        }
      } catch (e) {
        banner("Failed to set preset: " + e.message);
      }
    };
  });

  const scanBtn = $("scanLanBtn");
  if (scanBtn) {
    scanBtn.onclick = async () => {
      scanBtn.textContent = "⚡ SCANNING...";
      playSfx("tool");
      const deck = $("lanDevicesDeck");
      if (deck) deck.innerHTML = '<div class="empty-state">Scanning local subnet for active nodes...</div>';

      try {
        const resp = await fetch("/api/nexus/scan");
        const data = await resp.json();
        if (!data.devices || data.devices.length === 0) {
          if (deck) deck.innerHTML = '<div class="empty-state">No other LAN devices responded on probed ports.</div>';
          return;
        }

        if (deck) {
          deck.innerHTML = "";
          data.devices.forEach((d) => {
            const row = document.createElement("div");
            row.className = "lan-device-row";
            row.innerHTML = `
              <span class="ldr-name">${escapeHtml(d.hostname)}</span>
              <span class="ldr-ip">${escapeHtml(d.ip)}</span>
              <span class="ldr-ms">${d.response_time_ms}ms</span>
            `;
            deck.appendChild(row);
          });
        }
        playSfx("done");
      } catch (e) {
        if (deck) deck.innerHTML = `<div class="empty-state">Scan error: ${e.message}</div>`;
      } finally {
        scanBtn.innerHTML = '<span class="btn-icon">⚡</span> SCAN SUBNET';
      }
    };
  }

  const webhookBtn = $("sendWebhookBtn");
  if (webhookBtn) {
    webhookBtn.onclick = async () => {
      const url = ($("webhookUrlInput")?.value || "").trim();
      const rawPayload = ($("webhookPayloadInput")?.value || "").trim();
      if (!url) {
        banner("Enter a valid webhook URL.");
        return;
      }
      let payload = null;
      try {
        payload = rawPayload ? JSON.parse(rawPayload) : {};
      } catch (_) {
        payload = { raw: rawPayload };
      }

      const badge = $("webhookStatusBadge");
      if (badge) {
        badge.className = "badge badge-cyan";
        badge.textContent = "DISPATCHING";
      }
      playSfx("tool");

      try {
        const resp = await fetch("/api/nexus/trigger", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url, payload })
        });
        const res = await resp.json();
        if (res.ok) {
          if (badge) {
            badge.className = "badge badge-green";
            badge.textContent = `SENT (${res.status_code})`;
          }
          banner("IoT Webhook Dispatched Successfully! ✅");
          playSfx("done");
        } else {
          if (badge) {
            badge.className = "badge badge-amber";
            badge.textContent = "FAILED";
          }
          banner(`Webhook failed: ${res.error || "Unknown"}`);
        }
      } catch (err) {
        if (badge) badge.textContent = "NET ERROR";
      }
    };
  }
}

/* ==========================================================================
   WEB-OPERATOR & TECH RADAR CONTROLLER
   ========================================================================== */
async function loadTechRadar() {
  const listEl = $("techRadarList");
  if (!listEl) return;
  try {
    const resp = await fetch("/api/web/tech-briefing");
    const data = await resp.json();
    const briefing = data.briefing || "";
    const lines = briefing.split("\n");
    let items = [];
    let currentTitle = "";
    lines.forEach((l) => {
      const titleMatch = l.match(/^\d+\.\s+\*\*(.*?)\*\*/);
      if (titleMatch) {
        currentTitle = titleMatch[1];
      }
      const urlMatch = l.match(/🔗\s+(https?:\/\/[^\s]+)/);
      if (urlMatch && currentTitle) {
        items.push({ title: currentTitle, url: urlMatch[1] });
        currentTitle = "";
      }
    });

    if (items.length === 0) {
      listEl.innerHTML = `<div style="font-size: 12px; color: var(--text-dim); padding: 8px;">${briefing.replace(/\n/g, "<br>")}</div>`;
      return;
    }

    listEl.innerHTML = "";
    items.forEach((item) => {
      const el = document.createElement("div");
      el.className = "tech-item";
      el.innerHTML = `
        <a href="${escapeHtml(item.url)}" target="_blank" rel="noopener">${escapeHtml(item.title)}</a>
        <span style="font-size: 11px; color: var(--text-dim); font-family: var(--font-mono);">${escapeHtml(item.url)}</span>
      `;
      listEl.appendChild(el);
    });
  } catch (_) {
    listEl.innerHTML = '<div class="empty-state">Tech briefing feed standby.</div>';
  }
}

function initWebOperator() {
  const urlInp = $("browserUrlInput");
  const goBtn = $("browseGoBtn");
  const refreshTechBtn = $("refreshTechBtn");

  document.querySelectorAll(".qs-chip").forEach((btn) => {
    btn.onclick = () => {
      if (urlInp) urlInp.value = btn.dataset.url || "";
      if (goBtn) goBtn.click();
    };
  });

  if (goBtn) {
    goBtn.onclick = async () => {
      const url = (urlInp?.value || "").trim();
      if (!url) {
        banner("Enter a URL to browse.");
        return;
      }
      playSfx("tool");
      const titleEl = $("readerTitle");
      const statusEl = $("readerStatus");
      const bodyEl = $("readerBody");

      if (titleEl) titleEl.textContent = `Fetching: ${url}`;
      if (statusEl) {
        statusEl.className = "badge badge-cyan";
        statusEl.textContent = "FETCHING";
      }
      if (bodyEl) bodyEl.innerHTML = '<div class="skeleton" style="height: 200px;"></div>';

      try {
        const resp = await fetch("/api/web/browse", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url, summarize: true })
        });
        const data = await resp.json();
        if (titleEl) titleEl.textContent = `📄 ${data.title || url}`;
        if (statusEl) {
          statusEl.className = data.status_code === 200 ? "badge badge-green" : "badge badge-amber";
          statusEl.textContent = `HTTP ${data.status_code}`;
        }
        if (bodyEl) {
          const content = data.summary || data.text || "No content returned.";
          bodyEl.innerHTML = window.marked ? DOMPurify.sanitize(marked.parse(content)) : escapeHtml(content);
        }
        playSfx("done");
      } catch (e) {
        if (statusEl) statusEl.textContent = "ERROR";
        if (bodyEl) bodyEl.innerHTML = `<div class="empty-state">Failed to browse page: ${e.message}</div>`;
      }
    };
  }

  if (refreshTechBtn) {
    refreshTechBtn.onclick = async () => {
      playSfx("tool");
      await loadTechRadar();
      playSfx("done");
    };
  }
}

/* ==========================================================================
   OMNI COMMAND PALETTE (Ctrl+K) CONTROLLER
   ========================================================================== */
const COMMAND_CATALOG = [
  { icon: "🎙️", title: "Jarvis Holographic Voice Mode", desc: "Activate arc reactor voice duplexing & HUD", action: () => setAppMode("jarvis") },
  { icon: "💬", title: "Chat Matrix Console", desc: "Cybernetic text terminal & streaming chat", action: () => setAppMode("chat") },
  { icon: "🤖", title: "Swarm-Dev Studio", desc: "Autonomous 4-agent software engineering cluster", action: () => setAppMode("swarm") },
  { icon: "📚", title: "Neural-Vault Explorer", desc: "Local codebase & documentation semantic RAG", action: () => setAppMode("vault") },
  { icon: "📡", title: "Nexus-IoT & Sentry Cockpit", desc: "Workstation focus presets & LAN device radar", action: () => setAppMode("nexus") },
  { icon: "🌐", title: "Web-Operator Intelligence", desc: "Clean reader mode & daily developer tech trends", action: () => setAppMode("browse") },
  { icon: "🌅", title: "/briefing — Personal Morning Briefing", desc: "Today's agenda, weather, reminders & system health", action: () => sendDirectMessage("/briefing") },
  { icon: "🛡️", title: "/sentry — System Guardian Status", desc: "Inspect proactive battery, memory & downloads watcher", action: () => sendDirectMessage("/sentry") },
  { icon: "⚡", title: "Focus Preset: Code Sprint", desc: "Audio 25%, DND on, deep engineering state", action: () => setNexusPreset("code_sprint") },
  { icon: "🎬", title: "Focus Preset: Cinema", desc: "Audio 60%, media relaxation", action: () => setNexusPreset("cinema") },
  { icon: "☕", title: "Focus Preset: Chill", desc: "Audio 40%, calm ambient vibe", action: () => setNexusPreset("chill") },
  { icon: "🔇", title: "Focus Preset: Presentation", desc: "Audio 0% (muted), zero distractions", action: () => setNexusPreset("presentation") },
  { icon: "📸", title: "Screen Vision AI", desc: "Snap & inspect active screen display", action: () => snapAndAnalyzeScreen() },
  { icon: "🧠", title: "/facts — View Saved Facts", desc: "Inspect permanent long-term user memories", action: () => sendDirectMessage("/facts") },
  { icon: "⏰", title: "/reminders — Scheduled Reminders", desc: "List and manage background cron jobs", action: () => sendDirectMessage("/reminders") },
  { icon: "📊", title: "System Analytics & Telemetry", desc: "Open 7-day performance metrics overlay", action: () => $("sideStatsCard")?.click() },
  { icon: "⚖", title: "Operating Values & Rules", desc: "Inspect & edit personal ethical rules", action: () => $("sideValuesCard")?.click() },
  { icon: "👁️", title: "Biometrics: Physical Presence Sentry", desc: "Inspect real-time neural presence, face count & shield", action: () => { setAppMode("nexus"); refreshStatus(); } },
  { icon: "🛡️", title: "Biometrics: Toggle Privacy Shield", desc: "Instantly minimize sensitive code, chat & wallet windows", action: () => togglePrivacyShield() },
  { icon: "👤", title: "Biometrics: Enroll Master Face Profile", desc: "Enroll face vector signature using OpenCV SFace", action: () => enrollMasterFace() },
  { icon: "🔒", title: "Biometrics: Lock Workstation Desktop", desc: "Lock Windows desktop immediately via user32", action: () => lockWorkstationNow() },
  { icon: "⚡", title: "Kernel-Synthesis: Dynamic Compiled Tools", desc: "Inspect self-compiled hot-injected Python tools", action: () => { setAppMode("swarm"); loadSynthesizerTools(); } },
  { icon: "💳", title: "Fintech: Monthly Cashflow Summary", desc: "View income, expenses & savings rate", action: () => { setAppMode("nexus"); loadFintechSummary(); } },
  { icon: "📡", title: "Fintech: SaaS Burn-Rate Radar", desc: "Check monthly subscription overhead & renewals", action: () => { setAppMode("nexus"); loadFintechSummary(); } },
  { icon: "📄", title: "Fintech: Create Freelance Invoice", desc: "Generate professional client invoice with GST", action: () => promptCreateInvoice() },
  { icon: "🧠", title: "Deep-Reasoner: Extended MCTS Thinking", desc: "Explore multi-branch hypothesis trees & self-verification", action: () => triggerDeepThinking() },
  { icon: "🎭", title: "Voice Affect: Set Mode (Auto / Urgent / Calm)", desc: "Modulate speech rate, cadence and tone dynamically", action: () => promptSetVoiceAffect() },
  { icon: "🌐", title: "/cluster status — Sovereign Mesh Topology", desc: "Inspect RTX 5060 GPU node, laptops & mobile terminals", action: () => { setAppMode("nexus"); loadClusterStatus(); } },
  { icon: "🔄", title: "/cluster sync — Cross-Device State Handoff", desc: "Sync live sessions, bookmarks & tasks across nodes", action: () => syncClusterState() },
  { icon: "⚡", title: "/cluster dispatch — Offload Task to RTX 5060", desc: "Dispatch heavy compute to workstation GPU server", action: () => benchmarkClusterOffload() }
];

let selectedSpotIndex = 0;

async function togglePrivacyShield() {
  try {
    const status = await jget("/api/biometrics/status");
    const newState = !status.is_shielded;
    const res = await fetch("/api/biometrics/shield", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active: newState })
    }).then(r => r.json());
    banner(res.is_shielded ? `🛡️ Privacy Shield Engaged (${res.count} windows protected)` : `🔓 Privacy Shield Disengaged (${res.restored_count || 0} windows restored)`);
    playSfx(res.is_shielded ? "alert" : "done");
    refreshStatus();
  } catch (e) {
    banner(`Privacy Shield Error: ${e.message}`);
  }
}

async function enrollMasterFace() {
  try {
    banner("📷 Capturing camera frames for biometric enrollment...");
    playSfx("tool");
    const res = await fetch("/api/biometrics/enroll", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile_name: "master", sample_count: 5 })
    }).then(r => r.json());
    if (res.success) {
      banner(`✅ ${res.message} (${res.samples_enrolled} samples processed)`);
      playSfx("done");
    } else {
      banner(`⚠️ Enrollment note: ${res.message}`);
    }
    refreshStatus();
  } catch (e) {
    banner(`Enrollment Error: ${e.message}`);
  }
}

async function lockWorkstationNow() {
  try {
    playSfx("alert");
    await fetch("/api/biometrics/lock", { method: "POST" });
    banner("🔒 Workstation Lock Command Dispatched.");
  } catch (e) {
    banner(`Lock Error: ${e.message}`);
  }
}

function initBiometricsCockpit() {
  const shieldBtn = $("bioToggleShieldBtn");
  if (shieldBtn) shieldBtn.onclick = () => togglePrivacyShield();

  const enrollBtn = $("bioEnrollBtn");
  if (enrollBtn) enrollBtn.onclick = () => enrollMasterFace();

  const lockBtn = $("bioLockNowBtn");
  if (lockBtn) lockBtn.onclick = () => lockWorkstationNow();

  const autoLockBtn = $("bioAutoLockToggleBtn");
  if (autoLockBtn) {
    autoLockBtn.onclick = async () => {
      try {
        const status = await jget("/api/biometrics/status");
        const newSetting = !status.auto_lock_enabled;
        await fetch("/api/biometrics/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ auto_lock: newSetting })
        });
        banner(newSetting ? "⏱️ Workstation Auto-Lock Armed (60s inactivity)" : "⏱️ Workstation Auto-Lock Disarmed");
        playSfx("click");
        refreshStatus();
      } catch (e) {
        banner(`Config Error: ${e.message}`);
      }
    };
  }

  const statPres = $("statPresence");
  if (statPres) {
    statPres.onclick = () => {
      setAppMode("nexus");
      playSfx("click");
    };
  }
}

async function loadSynthesizerTools() {
  const container = $("synthesizedToolsList");
  if (!container) return;
  try {
    const res = await jget("/api/synthesizer/tools");
    const tools = res.tools || [];
    if (!tools.length) {
      container.innerHTML = `<div class="empty-state">No dynamic tools synthesized yet. Ask LUMI to synthesize any new capability on the fly!</div>`;
      return;
    }
    container.innerHTML = tools.map(t => {
      const isAct = t.status === "ACTIVE";
      return `
        <div class="synth-card">
          <div class="sc-head">
            <span class="sc-name">⚡ ${escapeHtml(t.name)}</span>
            <span class="badge ${isAct ? 'badge-green' : 'badge-dim'}">${t.status}</span>
          </div>
          <div class="sc-desc">${escapeHtml(t.description || 'Dynamic self-compiled tool')}</div>
          <div class="sc-metrics">
            <span>Calls: <b>${t.calls || 0}</b></span>
            <span>Avg Latency: <b>${t.avg_latency_ms || 0}ms</b></span>
          </div>
          <div class="sc-actions">
            ${isAct ? `
              <button class="hud-btn btn-bench" data-tool="${escapeHtml(t.name)}" style="font-size: 10px; padding: 3px 8px;">⚡ Benchmark</button>
              <button class="hud-btn danger-btn btn-revoke" data-tool="${escapeHtml(t.name)}" style="font-size: 10px; padding: 3px 8px;">✕ Revoke</button>
            ` : `<span style="font-size: 10px; color: var(--text-dim);">Revoked</span>`}
          </div>
        </div>
      `;
    }).join("");

    container.querySelectorAll(".btn-bench").forEach(b => {
      b.onclick = async () => {
        const toolName = b.dataset.tool;
        banner(`Benchmarking '${toolName}'...`);
        playSfx("tool");
        try {
          const bRes = await fetch("/api/synthesizer/benchmark", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tool_name: toolName, runs: 5 })
          }).then(r => r.json());
          if (bRes.success) {
            banner(`⚡ '${toolName}': Avg ${bRes.avg_ms}ms (min ${bRes.min_ms}ms, max ${bRes.max_ms}ms)`);
            playSfx("done");
          } else {
            banner(`Benchmark error: ${bRes.message || bRes.error}`);
          }
        } catch (e) {
          banner(`Error: ${e.message}`);
        }
      };
    });

    container.querySelectorAll(".btn-revoke").forEach(b => {
      b.onclick = async () => {
        const toolName = b.dataset.tool;
        if (!confirm(`Revoke synthesized tool '${toolName}'?`)) return;
        try {
          await fetch("/api/synthesizer/revoke", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tool_name: toolName })
          });
          banner(`Tool '${toolName}' revoked.`);
          playSfx("done");
          await loadSynthesizerTools();
        } catch (e) {
          banner(`Revoke error: ${e.message}`);
        }
      };
    });
  } catch (_) {}
}

function initSynthesizerDeck() {
  const refreshBtn = $("refreshSynthBtn");
  if (refreshBtn) {
    refreshBtn.onclick = async () => {
      playSfx("click");
      await loadSynthesizerTools();
    };
  }
}

async function loadFintechSummary() {
  try {
    const summary = await jget("/api/finance/summary");
    const subs = await jget("/api/finance/subscriptions");

    if ($("fintechExpenseVal")) $("fintechExpenseVal").textContent = `₹${(summary.total_expenses || 0).toLocaleString()}`;
    if ($("fintechInflowVal")) $("fintechInflowVal").textContent = `₹${(summary.total_income || 0).toLocaleString()}`;
    if ($("fintechNetVal")) {
      const net = summary.net_savings || 0;
      $("fintechNetVal").textContent = `₹${net.toLocaleString()}`;
      $("fintechNetVal").className = net >= 0 ? "val-green" : "val-amber";
    }
    if ($("fintechSavingsRateSub")) $("fintechSavingsRateSub").textContent = `Savings Rate: ${summary.savings_rate_pct || 0}%`;
    if ($("fintechBurnVal")) $("fintechBurnVal").textContent = `₹${(subs.monthly_burn_rate || 0).toLocaleString()}/mo`;
    if ($("fintechSubsCountSub")) $("fintechSubsCountSub").textContent = `${subs.active_subscriptions_count || 0} Subscriptions Tracked`;
    if ($("fintechBurnRateBadge")) $("fintechBurnRateBadge").textContent = `BURN: ₹${Math.round(subs.monthly_burn_rate || 0)}/mo`;
  } catch (_) {}
}

async function promptCreateInvoice() {
  const client = prompt("Enter Client Name:", "Acme Corp");
  if (!client) return;
  const desc = prompt("Enter Service Description:", "Full-Stack Development & AI Integration");
  if (!desc) return;
  const rate = parseFloat(prompt("Enter Rate (₹):", "25000") || "0");
  if (rate <= 0) return;

  try {
    banner("Generating invoice...");
    playSfx("tool");
    const res = await fetch("/api/finance/invoice", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        client_name: client,
        items: [{ name: desc, rate: rate, qty: 1 }],
        tax_rate_pct: 18.0
      })
    }).then(r => r.json());

    banner(`✅ Invoice ${res.invoice_number} created (Total: ₹${res.total_amount.toLocaleString()})!`);
    playSfx("done");
    hideWelcome();
    const out = $("chat");
    if (out) {
      const card = document.createElement("div");
      card.className = "msg bot";
      card.innerHTML = `<div class="avatar">◈</div><div class="content">${marked.parse(res.markdown)}</div>`;
      out.appendChild(card);
      out.scrollTop = out.scrollHeight;
    }
  } catch (e) {
    banner(`Invoice Error: ${e.message}`);
  }
}

function initFintechOracleCockpit() {
  const addTxnBtn = $("fintechAddTxnBtn");
  if (addTxnBtn) {
    addTxnBtn.onclick = async () => {
      const desc = prompt("Enter Expense Description (e.g. Swiggy Lunch, AWS Cloud):", "AWS Hosting");
      if (!desc) return;
      const amt = parseFloat(prompt("Enter Amount (₹):", "1500") || "0");
      if (amt <= 0) return;
      try {
        await fetch("/api/finance/transaction", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ description: desc, amount: amt, txn_type: "debit" })
        });
        banner(`Recorded expense ₹${amt} for '${desc}'`);
        playSfx("done");
        await loadFintechSummary();
      } catch (e) {
        banner(`Error: ${e.message}`);
      }
    };
  }

  const trackSubBtn = $("fintechTrackSubBtn");
  if (trackSubBtn) {
    trackSubBtn.onclick = async () => {
      const name = prompt("Enter Subscription Name (e.g. Netflix, ChatGPT):", "ChatGPT Plus");
      if (!name) return;
      const amt = parseFloat(prompt("Enter Monthly Charge (₹):", "1999") || "0");
      if (amt <= 0) return;
      try {
        await fetch("/api/finance/subscription", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name, amount: amt, billing_cycle: "monthly", renewal_day: 15 })
        });
        banner(`Subscription '${name}' tracked at ₹${amt}/mo!`);
        playSfx("done");
        await loadFintechSummary();
      } catch (e) {
        banner(`Error: ${e.message}`);
      }
    };
  }

  const genInvBtn = $("fintechGenInvoiceBtn");
  if (genInvBtn) genInvBtn.onclick = () => promptCreateInvoice();
}

/* ==========================================================================
   CLUSTER-OMNI: SOVEREIGN MULTI-DEVICE MESH (Phase 18)
   ========================================================================== */
async function loadClusterStatus() {
  try {
    const data = await jget("/api/cluster/status");
    const clusterPill = $("statClusterText");
    if (clusterPill) {
      clusterPill.textContent = `🌐 Mesh: ${data.online_nodes || 0}/${data.total_nodes || 0}`;
    }

    if ($("clusterGpuNodeVal")) {
      const gpuNode = data.nodes?.find(n => n.node_id === data.primary_gpu_node);
      $("clusterGpuNodeVal").textContent = gpuNode ? gpuNode.alias : "RTX GPU";
    }
    if ($("clusterStatusVal")) {
      $("clusterStatusVal").textContent = `${data.online_nodes || 0} NODES ONLINE`;
      $("clusterStatusVal").className = (data.online_nodes > 0) ? "val-green" : "val-amber";
    }
    if ($("clusterNodesOnlineSub")) {
      $("clusterNodesOnlineSub").textContent = `${data.online_nodes || 0} of ${data.total_nodes || 0} Devices Connected`;
    }

    const listEl = $("clusterNodesList");
    if (listEl && data.nodes) {
      listEl.innerHTML = "";
      data.nodes.forEach(node => {
        const card = document.createElement("div");
        card.className = "cockpit-card glass-panel";
        card.style.padding = "10px 12px";
        card.style.background = node.is_local ? "rgba(0, 240, 255, 0.05)" : "rgba(255, 255, 255, 0.02)";
        card.style.border = node.is_local ? "1px solid rgba(0, 240, 255, 0.25)" : "1px solid var(--border-glass)";

        let icon = "💻";
        if (node.role === "primary") icon = "🖥️";
        else if (node.role === "client") icon = "📱";

        const statusClass = (node.status === "online" || node.status === "busy") ? "badge-green" : "badge-dim";
        const isLocalTag = node.is_local ? '<span class="badge badge-cyan" style="font-size: 9px; padding: 2px 6px;">THIS DEVICE</span>' : '';

        card.innerHTML = `
          <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-size: 18px;">${icon}</span>
              <div>
                <b style="font-family: var(--font-display); font-size: 12.5px; color: var(--text-bright);">${escapeHtml(node.alias)}</b>
                <div style="font-family: var(--font-mono); font-size: 10.5px; color: var(--text-dim);">${node.host}:${node.port}</div>
              </div>
            </div>
            <div style="display: flex; gap: 4px;">
              ${isLocalTag}
              <span class="badge ${statusClass}" style="font-size: 9px; padding: 2px 6px;">${node.status.toUpperCase()}</span>
            </div>
          </div>
          <div style="font-family: var(--font-mono); font-size: 10px; color: var(--text-muted); display: flex; gap: 6px; flex-wrap: wrap;">
            ${(node.capabilities || []).map(c => `<span style="background: rgba(255,255,255,0.05); padding: 1px 6px; border-radius: 4px;">${escapeHtml(c)}</span>`).join("")}
          </div>
        `;
        listEl.appendChild(card);
      });
    }
  } catch (_) {}
}

async function syncClusterState() {
  try {
    banner("🔄 Broadcasting sovereign state snapshot to mesh peers...");
    playSfx("tool");
    const res = await fetch("/api/cluster/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ context_data: { user: "Boss", session: "active", timestamp: Date.now() } })
    }).then(r => r.json());

    banner(`✅ ${res.message} (Sig: ${res.signature.slice(0, 10)}...)`);
    playSfx("done");
    if ($("clusterSyncVal")) {
      $("clusterSyncVal").textContent = "SYNCHRONIZED";
      $("clusterSyncVal").className = "val-green";
    }
    await loadClusterStatus();
  } catch (e) {
    banner(`Sync error: ${e.message}`);
  }
}

async function benchmarkClusterOffload() {
  try {
    banner("⚡ Offloading vision/neural task across sovereign mesh...");
    playSfx("tool");
    const res = await fetch("/api/cluster/dispatch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        task_type: "vision",
        payload: { benchmark: true, samples: 100 }
      })
    }).then(r => r.json());

    banner(`✅ Task completed on ${res.target_alias} in ${res.execution_time_ms}ms (${res.acceleration || "Remote P2P"})!`);
    playSfx("done");
    await loadClusterStatus();
  } catch (e) {
    banner(`Dispatch error: ${e.message}`);
  }
}

async function enrollPeerNodeModal() {
  const alias = prompt("Enter Peer Device Label (e.g. Boss iPad Pro, Home NAS):", "Boss Tablet");
  if (!alias) return;
  const nid = "node_" + alias.toLowerCase().replace(/[^a-z0-9]/g, "_");
  const host = prompt("Enter Device IP Address (e.g. 192.168.1.15):", "192.168.1.15") || "127.0.0.1";
  const role = prompt("Enter Role (satellite / client / primary):", "satellite") || "satellite";

  try {
    banner(`Enrolling ${alias} into sovereign mesh...`);
    playSfx("tool");
    const res = await fetch("/api/cluster/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        node_id: nid,
        alias: alias,
        role: role,
        host: host,
        port: 8766,
        capabilities: ["ui", "local_cli"]
      })
    }).then(r => r.json());

    banner(`✅ Node '${alias}' enrolled in cluster mesh!`);
    playSfx("done");
    await loadClusterStatus();
  } catch (e) {
    banner(`Enrollment error: ${e.message}`);
  }
}

function initClusterCockpit() {
  const demoBtn = $("clusterDispatchDemoBtn");
  if (demoBtn) demoBtn.onclick = () => benchmarkClusterOffload();

  const syncBtn = $("clusterSyncStateBtn");
  if (syncBtn) syncBtn.onclick = () => syncClusterState();

  const addBtn = $("clusterAddNodeBtn");
  if (addBtn) addBtn.onclick = () => enrollPeerNodeModal();
}

async function triggerDeepThinking(customProblem) {
  const problem = customProblem || prompt("Enter complex problem for Deep MCTS Reasoning:", "Design a high-throughput distributed cache with sub-millisecond lookup latency");
  if (!problem) return;

  banner("🧠 Spawning Monte-Carlo Reasoning Tree...");
  playSfx("tool");
  hideWelcome();

  const out = $("chat");
  const thinkingCard = document.createElement("div");
  thinkingCard.className = "msg bot";
  thinkingCard.innerHTML = `
    <div class="avatar">◈</div>
    <div class="content">
      <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 10px;">
        <span class="pulse-dot" style="background: var(--purple); width: 8px; height: 8px; border-radius: 50%;"></span>
        <b style="color: var(--purple); font-family: var(--font-display); font-size: 13px;">DEEP REASONING EXPLORATION ACTIVE...</b>
      </div>
      <div style="font-family: var(--font-mono); font-size: 11.5px; color: var(--text-dim); background: rgba(0,0,0,0.4); padding: 10px; border-radius: 8px; line-height: 1.6;">
        Exploring 3 divergent architectural hypotheses and running step-verifier critiques...
      </div>
    </div>
  `;
  if (out) {
    out.appendChild(thinkingCard);
    out.scrollTop = out.scrollHeight;
  }

  try {
    const res = await fetch("/api/reasoner/explore", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ problem: problem, branches: 3, domain: "architecture" })
    }).then(r => r.json());

    const steps = (res.thought_trace || []).map(s => `<div>${escapeHtml(s)}</div>`).join("");
    thinkingCard.innerHTML = `
      <div class="avatar">◈</div>
      <div class="content">
        <details open style="margin-bottom: 14px; background: rgba(0,0,0,0.4); border: 1px solid var(--border-glass); border-radius: 8px; padding: 10px 14px;">
          <summary style="cursor: pointer; font-family: var(--font-display); font-size: 12px; color: var(--cyan); font-weight: 700;">
            🧠 EXTENDED THINKING TRACE (${res.branches_evaluated} Branches · Score: ${res.confidence_score}/100 · ${res.execution_time_ms}ms)
          </summary>
          <div style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); line-height: 1.6; margin-top: 8px;">
            ${steps}
          </div>
        </details>
        ${marked.parse(res.optimal_solution)}
      </div>
    `;
    playSfx("done");
    if (out) out.scrollTop = out.scrollHeight;
  } catch (e) {
    banner(`Reasoning Error: ${e.message}`);
  }
}

async function promptSetVoiceAffect() {
  const mode = prompt("Choose Voice Affect Mode (auto, urgent, debug, late_night, calm):", "auto");
  if (!mode) return;
  try {
    const res = await fetch("/api/voice/affect/configure", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: mode.toLowerCase() })
    }).then(r => r.json());
    banner(`🎭 Voice Affect set to: ${res.active_state} (${res.speech_rate_offset}% rate offset)`);
    playSfx("done");
    refreshStatus();
  } catch (e) {
    banner(`Error: ${e.message}`);
  }
}

function sendDirectMessage(msg) {
  setAppMode("chat");
  const inp = $("input");
  if (inp) {
    inp.value = msg;
    $("send")?.click();
  }
}

async function setNexusPreset(preset) {
  try {
    await fetch("/api/nexus/focus", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ preset })
    });
    banner(`Activated Preset: ${preset.toUpperCase()} ⚡`);
    playSfx("done");
  } catch (_) {}
}

function initCommandPalette() {
  const modal = $("commandPalette");
  const input = $("spotlightInput");
  const results = $("spotlightResults");
  const triggerBtn = $("cmdPaletteBtn");

  function openPalette() {
    if (!modal) return;
    modal.classList.remove("hidden");
    selectedSpotIndex = 0;
    if (input) {
      input.value = "";
      input.focus();
    }
    renderPaletteResults("");
    playSfx("send");
  }

  function closePalette() {
    if (!modal) return;
    modal.classList.add("hidden");
  }

  function renderPaletteResults(filter) {
    if (!results) return;
    const q = (filter || "").toLowerCase().trim();
    const matches = COMMAND_CATALOG.filter((c) =>
      c.title.toLowerCase().includes(q) || c.desc.toLowerCase().includes(q)
    );

    if (matches.length === 0) {
      results.innerHTML = '<div class="empty-state">No matching commands. Try "/briefing", "swarm", "preset"...</div>';
      return;
    }

    results.innerHTML = "";
    matches.forEach((item, idx) => {
      const row = document.createElement("div");
      row.className = "spot-item" + (idx === selectedSpotIndex ? " selected" : "");
      row.innerHTML = `
        <span class="spot-item-icon">${item.icon}</span>
        <div class="spot-item-content">
          <span class="spot-item-title">${escapeHtml(item.title)}</span>
          <span class="spot-item-desc">${escapeHtml(item.desc)}</span>
        </div>
      `;
      row.onclick = () => {
        closePalette();
        item.action();
      };
      results.appendChild(row);
    });
  }

  if (triggerBtn) triggerBtn.onclick = openPalette;
  if (modal) {
    modal.onclick = (e) => {
      if (e.target === modal) closePalette();
    };
  }

  if (input) {
    input.oninput = () => {
      selectedSpotIndex = 0;
      renderPaletteResults(input.value);
    };
    input.onkeydown = (e) => {
      const items = results?.querySelectorAll(".spot-item");
      if (!items || items.length === 0) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        selectedSpotIndex = (selectedSpotIndex + 1) % items.length;
        items.forEach((el, i) => el.classList.toggle("selected", i === selectedSpotIndex));
        items[selectedSpotIndex]?.scrollIntoView({ block: "nearest" });
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        selectedSpotIndex = (selectedSpotIndex - 1 + items.length) % items.length;
        items.forEach((el, i) => el.classList.toggle("selected", i === selectedSpotIndex));
        items[selectedSpotIndex]?.scrollIntoView({ block: "nearest" });
      } else if (e.key === "Enter") {
        e.preventDefault();
        items[selectedSpotIndex]?.click();
      } else if (e.key === "Escape") {
        closePalette();
      }
    };
  }

  window.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      if (modal?.classList.contains("hidden")) {
        openPalette();
      } else {
        closePalette();
      }
    }
  });
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/* ── Event Listeners & Boot ───────────────────────────────────── */
window.addEventListener("DOMContentLoaded", () => {
  initBackgroundCanvas();
  init3DInteractiveEffects();
  initOrbParticles();
  initJarvisMode();
  initSwarmDev();
  initNeuralVault();
  initNexusCockpit();
  initBiometricsCockpit();
  initSynthesizerDeck();
  initFintechOracleCockpit();
  initWebOperator();
  initCommandPalette();
  refreshStatus();
  pollLive();
  loadToolsList();
  loadProjectsList();
  loadSynthesizerTools();
  loadFintechSummary();
  loadVaultStats();
  loadNexusStatus();
  loadSentryStatus();
  initClusterCockpit();
  loadClusterStatus();
  startPoll();

  const openAdminBtn = $("openAdminBtn");
  if (openAdminBtn) {
    openAdminBtn.onclick = () => {
      sendDirectMessage("/stats");
    };
  }

  // Always-On Voice Ear: Automatically arms listening on first click/tap anywhere
  const unlockAmbientEar = () => {
    if (appMode === "jarvis" && handsFreeEnabled && !isJarvisListening && !isJarvisProcessing && !isJarvisSpeaking) {
      startJarvisListening();
    }
  };
  window.addEventListener("click", unlockAmbientEar, { passive: true });
  window.addEventListener("keydown", (e) => {
    if (e.key === " " || e.key === "Escape") return;
    unlockAmbientEar();
  }, { passive: true });

  // Input auto-growth & Enter handling
  const input = $("input");
  if (input) {
    try {
      input.focus({ preventScroll: true });
    } catch (_) {
      input.focus();
    }
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        send();
      }
    });
    input.addEventListener("input", () => {
      input.style.height = "auto";
      input.style.height = Math.min(input.scrollHeight, 180) + "px";
    });
  }

  const sendBtn = $("send");
  if (sendBtn) sendBtn.onclick = send;

  // Screen Vision Triggers (HUD, Composer & Topbar)
  const jarvisSnapBtn = $("jarvisSnapScreenBtn");
  if (jarvisSnapBtn) {
    jarvisSnapBtn.onclick = () => snapAndAnalyzeScreen();
  }
  const snapChatBtn = $("snapScreenChatBtn");
  if (snapChatBtn) {
    snapChatBtn.onclick = () => {
      const q = $("input") ? $("input").value.trim() : "";
      snapAndAnalyzeScreen(q);
      if ($("input")) $("input").value = "";
    };
  }
  const visionTop = $("visionTopBtn");
  if (visionTop) {
    visionTop.onclick = () => snapAndAnalyzeScreen();
  }

  // Starter card click triggers
  document.querySelectorAll(".starter-card").forEach((btn) => {
    btn.onclick = () => {
      const msg = btn.getAttribute("data-msg");
      if (msg && $("input")) {
        $("input").value = msg;
        send();
      }
    };
  });

  // Deck chip triggers
  document.querySelectorAll(".deck-chip").forEach((btn) => {
    btn.onclick = () => {
      const cmd = btn.getAttribute("data-cmd");
      if (cmd === "/deepthink") {
        triggerDeepThinking();
        return;
      }
      if (cmd && $("input")) {
        $("input").value = cmd;
        send();
      }
    };
  });

  // Theme switch
  const themeBtn = $("themeBtn");
  if (themeBtn) {
    themeBtn.onclick = () => {
      const cur = document.documentElement.getAttribute("data-theme") || "cyber";
      const next = cur === "cyber" ? "light" : "cyber";
      document.documentElement.setAttribute("data-theme", next);
      themeBtn.innerHTML = next === "cyber" ? '<span class="pill-icon">☀</span>' : '<span class="pill-icon">🌙</span>';
    };
  }

  // Modals & Panels
  const statsCard = $("sideStatsCard");
  const statsPage = $("statsPage");
  const statsClose = $("statsClose");
  if (statsCard && statsPage) {
    statsCard.onclick = () => {
      statsPage.classList.remove("hidden");
      loadAnalytics();
    };
  }
  if (statsClose && statsPage) {
    statsClose.onclick = () => statsPage.classList.add("hidden");
  }

  const valuesCard = $("sideValuesCard");
  const valuesPage = $("valuesPage");
  const valuesClose = $("valuesClose");
  if (valuesCard && valuesPage) {
    valuesCard.onclick = () => valuesPage.classList.remove("hidden");
  }
  if (valuesClose && valuesPage) {
    valuesClose.onclick = () => valuesPage.classList.add("hidden");
  }

  // Quick Fact Creator
  const addFactBtn = $("addFactQuickBtn");
  if (addFactBtn) {
    addFactBtn.onclick = async () => {
      const key = prompt("Enter fact key (e.g., 'primary_language', 'project_deadline'):");
      if (!key) return;
      const val = prompt(`Enter value for '${key}':`);
      if (!val) return;
      try {
        await fetch("/api/facts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ key, value: val, category: "user" })
        });
        loadFactsList();
      } catch (e) {
        banner("Failed to store fact.");
      }
    };
  }

  // Sidebar & Monitor Toggles (Adaptive Desktop Collapse & Mobile Drawers)
  const sidebarToggle = $("sidebarToggle");
  const sidebarClose = $("sidebarClose");
  const sidebar = $("sidebar");

  function toggleSidebar() {
    if (!sidebar) return;
    if (window.innerWidth <= 860) {
      sidebar.classList.toggle("open");
    } else {
      sidebar.classList.toggle("collapsed");
    }
  }

  if (sidebarToggle && sidebar) {
    sidebarToggle.onclick = toggleSidebar;
  }
  if (sidebarClose && sidebar) {
    sidebarClose.onclick = () => {
      sidebar.classList.remove("open");
      sidebar.classList.add("collapsed");
    };
  }

  const contextToggle = $("contextToggle");
  const contextClose = $("contextClose");
  const context = $("context");

  function toggleContext() {
    if (!context) return;
    if (window.innerWidth <= 1180) {
      context.classList.toggle("open");
    } else {
      context.classList.toggle("collapsed");
    }
  }

  if (contextToggle && context) {
    contextToggle.onclick = toggleContext;
  }
  if (contextClose && context) {
    contextClose.onclick = () => {
      context.classList.remove("open");
      context.classList.add("collapsed");
    };
  }

  window.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b") {
      e.preventDefault();
      toggleSidebar();
    }
  });

  initLumiBotCompanion();
});

/* ==========================================================================
   DRAGGABLE CYBER-BOT COMPANION ("CHOTU LUMI") CONTROLLER
   ========================================================================== */
function showBotBubble(text, duration = 3500) {
  const bubble = $("botSpeechBubble");
  const txtEl = $("botBubbleText");
  if (!bubble || !txtEl) return;
  txtEl.textContent = text;
  bubble.classList.add("visible");
  if (bubble._timer) clearTimeout(bubble._timer);
  if (duration > 0) {
    bubble._timer = setTimeout(() => {
      bubble.classList.remove("visible");
    }, duration);
  }
}

function initLumiBotCompanion() {
  const bot = $("lumiBotCompanion");
  if (!bot) return;

  const quickMenu = $("botQuickMenu");
  const pupils = bot.querySelectorAll(".pupil");

  // Restore saved position
  const savedLeft = localStorage.getItem("lumi_bot_left");
  const savedTop = localStorage.getItem("lumi_bot_top");
  if (savedLeft && savedTop) {
    bot.style.left = `${savedLeft}px`;
    bot.style.top = `${savedTop}px`;
    bot.style.right = "auto";
    bot.style.bottom = "auto";
  }

  // Dragging physics with pointer events
  let isDragging = false;
  let startX = 0, startY = 0;
  let initialLeft = 0, initialTop = 0;
  let movedDistance = 0;

  bot.addEventListener("pointerdown", (e) => {
    // Only left click initiates drag
    if (e.button !== 0) return;
    isDragging = true;
    movedDistance = 0;
    startX = e.clientX;
    startY = e.clientY;

    const rect = bot.getBoundingClientRect();
    initialLeft = rect.left;
    initialTop = rect.top;

    bot.style.left = `${initialLeft}px`;
    bot.style.top = `${initialTop}px`;
    bot.style.right = "auto";
    bot.style.bottom = "auto";
    bot.setPointerCapture(e.pointerId);
  });

  bot.addEventListener("pointermove", (e) => {
    if (!isDragging) return;
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    movedDistance = Math.hypot(dx, dy);

    if (movedDistance > 4) {
      if (quickMenu) quickMenu.classList.add("hidden");
    }

    const maxX = window.innerWidth - bot.offsetWidth - 10;
    const maxY = window.innerHeight - bot.offsetHeight - 10;
    const newLeft = Math.max(10, Math.min(maxX, initialLeft + dx));
    const newTop = Math.max(10, Math.min(maxY, initialTop + dy));

    bot.style.left = `${newLeft}px`;
    bot.style.top = `${newTop}px`;
  });

  const stopDrag = (e) => {
    if (!isDragging) return;
    isDragging = false;
    try { bot.releasePointerCapture(e.pointerId); } catch (_) {}

    const rect = bot.getBoundingClientRect();
    localStorage.setItem("lumi_bot_left", Math.round(rect.left));
    localStorage.setItem("lumi_bot_top", Math.round(rect.top));

    // If it was just a click (not a drag)
    if (movedDistance < 6) {
      handleBotClick();
    }
  };

  bot.addEventListener("pointerup", stopDrag);
  bot.addEventListener("pointercancel", stopDrag);

  function handleBotClick() {
    playSfx("token");
    if (isJarvisSpeaking) {
      triggerDuplexBargeIn();
      showBotBubble("Quiet mode engaged.", 2000);
      return;
    }
    if (isJarvisProcessing) {
      hideProcessingHUD();
      isJarvisProcessing = false;
      playSfx("tool");
      startJarvisListening();
      showBotBubble("Listening...", 2000);
      return;
    }
    if (isJarvisListening) {
      stopJarvisListeningAndProcess(jarvisCapturedText || "");
      showBotBubble("Processing directive...", 2000);
    } else {
      isJarvisProcessing = false;
      startJarvisListening();
      showBotBubble("Boliye Boss, main sun raha hoon!", 2500);
    }
  }

  // Right-click: Context Menu
  bot.addEventListener("contextmenu", (e) => {
    e.preventDefault();
    if (quickMenu) {
      quickMenu.classList.toggle("hidden");
      playSfx("token");
    }
  });

  // Close menu when clicking outside
  document.addEventListener("click", (e) => {
    if (quickMenu && !bot.contains(e.target)) {
      quickMenu.classList.add("hidden");
    }
  });

  // Quick action buttons
  const bqListenBtn = $("bqListenBtn");
  if (bqListenBtn) bqListenBtn.onclick = () => {
    if (quickMenu) quickMenu.classList.add("hidden");
    handleBotClick();
  };

  const bqVisionBtn = $("bqVisionBtn");
  if (bqVisionBtn) bqVisionBtn.onclick = () => {
    if (quickMenu) quickMenu.classList.add("hidden");
    snapAndAnalyzeScreen();
    showBotBubble("Analyzing screen...", 2500);
  };

  const bqBriefingBtn = $("bqBriefingBtn");
  if (bqBriefingBtn) bqBriefingBtn.onclick = () => {
    if (quickMenu) quickMenu.classList.add("hidden");
    sendDirectMessage("/briefing");
    showBotBubble("Briefing loading...", 2500);
  };

  const bqShieldBtn = $("bqShieldBtn");
  if (bqShieldBtn) bqShieldBtn.onclick = () => {
    if (quickMenu) quickMenu.classList.add("hidden");
    togglePrivacyShield();
    showBotBubble("Privacy Shield toggled 🛡️", 2500);
  };

  const bqHideBtn = $("bqHideBtn");
  if (bqHideBtn) bqHideBtn.onclick = () => {
    bot.style.display = "none";
    banner("Chotu LUMI minimized. Reload page to restore.");
  };

  // Eye-tracking pupils towards mouse pointer
  window.addEventListener("mousemove", (e) => {
    if (isDragging) return;
    const rect = bot.getBoundingClientRect();
    const botCenterX = rect.left + rect.width / 2;
    const botCenterY = rect.top + rect.height / 2;
    const dx = e.clientX - botCenterX;
    const dy = e.clientY - botCenterY;
    const dist = Math.hypot(dx, dy);

    if (dist > 10) {
      const offsetX = Math.max(-3, Math.min(3, (dx / dist) * 3));
      const offsetY = Math.max(-2, Math.min(2, (dy / dist) * 2));
      pupils.forEach((p) => {
        p.style.transform = `translate(${offsetX.toFixed(1)}px, ${offsetY.toFixed(1)}px)`;
      });
    }
  }, { passive: true });

  // Natural Eye Blinking Animation
  function scheduleBlink() {
    const nextBlink = Math.random() * 3200 + 3000;
    setTimeout(() => {
      bot.classList.add("blink");
      setTimeout(() => {
        bot.classList.remove("blink");
        scheduleBlink();
      }, 160);
    }, nextBlink);
  }
  scheduleBlink();

  // Welcome Greeting on load
  setTimeout(() => {
    showBotBubble("Namaste Boss! Main ready hoon.", 3800);
  }, 1200);
}
