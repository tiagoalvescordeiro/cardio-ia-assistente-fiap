/**
 * Widget CardioIA + ECO (vanilla JS).
 * Consome POST /api/chat (alias /api/message). Ideação nunca depende do Watson.
 */
(() => {
  const API_BASE = window.location.protocol === "file:" ? "http://127.0.0.1:5000" : "";

  const transcript = document.getElementById("transcript");
  const form = document.getElementById("composer");
  const input = document.getElementById("composer-input");
  const sendBtn = document.getElementById("send-btn");
  const healthPill = document.getElementById("health-pill");
  const themeToggle = document.getElementById("theme-toggle");
  const resetSessionBtn = document.getElementById("reset-session");
  const extractCard = document.getElementById("extract-card");
  const extractBody = document.getElementById("extract-body");
  const extractError = document.getElementById("extract-error");
  const extractClose = document.getElementById("extract-close");
  const extractChip = document.getElementById("extract-chip");
  const breathingPanel = document.getElementById("breathing-panel");
  const ecoSocial = document.getElementById("eco-social");
  const ecoPulse = document.getElementById("eco-pulse");
  const ecoHeatmap = document.getElementById("eco-heatmap");
  const ecoNarrative = document.getElementById("eco-narrative");
  const breathCircle = document.getElementById("breath-circle");
  const breathPhase = document.getElementById("breath-phase");
  const breathCount = document.getElementById("breath-count");
  const breathStart = document.getElementById("breath-start");
  const breathStop = document.getElementById("breath-stop");
  const crisisModal = document.getElementById("crisis-modal");
  const crisisAck = document.getElementById("crisis-ack");
  const crisisClose = document.getElementById("crisis-close");
  const crisisText = document.getElementById("crisis-text");

  let sessionId = null;
  let sending = false;
  let lastUserText = "";
  let breathTimer = null;
  let breathPhaseIdx = 0;
  let breathLeft = 0;

  const WELCOME =
    "Oi. Eu sou a CardioIA — acolhimento inicial, sem diagnosticar e sem receitar. Conte o que está sentindo.\n\nNa dúvida entre estresse e coração, o atendimento presencial sempre vem primeiro. Emergência: 192. Crise emocional com ideação: 188.";

  const EMPTY_COMPOSER = "Escreva uma mensagem para enviar.";

  const PHASES = [
    { name: "Inspire", seconds: 4, cls: "inhale" },
    { name: "Segure", seconds: 7, cls: "hold" },
    { name: "Expire", seconds: 8, cls: "exhale" },
  ];

  function setTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("cardioia-theme", theme);
    themeToggle.textContent = theme === "dark" ? "Modo claro" : "Modo escuro";
    themeToggle.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
  }

  setTheme(localStorage.getItem("cardioia-theme") || "dark");
  themeToggle.addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    setTheme(next);
  });

  function appendBubble(role, text, extraClass) {
    const wrap = document.createElement("div");
    wrap.className = `bubble ${role}${extraClass ? ` ${extraClass}` : ""}`;
    const who = document.createElement("span");
    who.className = "who";
    who.textContent = role === "user" ? "Você" : "CardioIA";
    wrap.appendChild(who);
    wrap.appendChild(document.createTextNode(text));
    transcript.appendChild(wrap);
    transcript.scrollTop = transcript.scrollHeight;
    return wrap;
  }

  function setTyping(on) {
    const existing = transcript.querySelector(".bubble.typing");
    if (existing) existing.remove();
    if (on) appendBubble("assistant", "digitando…", "typing");
  }

  function showBreathing(show) {
    breathingPanel.classList.toggle("hidden", !show);
  }

  function hideEcoSocial() {
    ecoSocial.classList.add("hidden");
  }

  function hideExtractCard() {
    extractCard.classList.add("hidden");
    extractError.classList.add("hidden");
    extractError.textContent = "";
    extractBody.innerHTML = "";
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function showExtractError(message) {
    extractCard.classList.remove("hidden");
    extractError.classList.remove("hidden");
    extractError.textContent = message;
    extractBody.innerHTML = "";
    extractCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function showExtractResult(data) {
    extractError.classList.add("hidden");
    extractError.textContent = "";
    const vitals = data.sinais_vitais || {};
    const spo2 = vitals.spo2 == null ? "—" : `${vitals.spo2}%`;
    const pa =
      vitals.pressao_sistolica != null && vitals.pressao_diastolica != null
        ? `${vitals.pressao_sistolica}/${vitals.pressao_diastolica} mmHg`
        : "—";
    const fc = vitals.frequencia_cardiaca != null ? `${vitals.frequencia_cardiaca} bpm` : "—";
    const rows = [
      ["Risco", data.classificacao_risco || data.risco_estratificado || "—"],
      ["Vitais", `PA ${pa} · FC ${fc} · SpO2 ${spo2}`],
      ["Conduta", data.conduta_sugerida || "—"],
      ["Aviso", data.disclaimer || "Este assistente não substitui atendimento médico."],
    ];
    extractBody.innerHTML = rows
      .map(([dt, dd]) => `<div class="extract-row"><dt>${escapeHtml(dt)}</dt><dd>${escapeHtml(dd)}</dd></div>`)
      .join("");
    extractCard.classList.remove("hidden");
    extractCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function looksLikeClinicalNarrative(text) {
    const raw = text || "";
    const n = raw.toLowerCase();
    const hasPa = /\b\d{2,3}\s*[x/]\s*\d{2,3}\b/.test(n) || /\bpa\b/.test(n);
    const hasFc = /\bbpm\b/.test(n) || /\bfc\b/.test(n) || /frequ[eê]ncia/.test(n);
    const hasId = /pac[-_][a-z0-9]+/i.test(raw);
    return Boolean((hasPa && hasFc) || hasId);
  }

  async function extractNarrative(text) {
    const source = (text || "").trim();
    if (!source) {
      showExtractError("Envie um relato com PA, FC e, se possível, SpO2 para montar o resumo.");
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/api/extract`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: source }),
      });
      const data = await res.json();
      if (!res.ok) {
        showExtractError(data.error || "Não consegui extrair o relato. Inclua idade, PA e FC.");
        return;
      }
      showExtractResult(data);
    } catch (err) {
      showExtractError("Falha de rede ao extrair o relato. Confirme se o serviço está no ar.");
    }
  }

  function renderHeatmap(points) {
    const blobs = (points || [])
      .map((p) => {
        const fill = `rgba(61, 139, 132, ${0.25 + (p.intensity || 0.3) * 0.7})`;
        return `<circle cx="${p.cx}" cy="${p.cy}" r="${p.r}" fill="${fill}" />`;
      })
      .join("");
    ecoHeatmap.innerHTML = `<svg viewBox="0 0 100 70" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
      <defs>
        <radialGradient id="ecoFog" cx="50%" cy="50%">
          <stop offset="0%" stop-color="#3d8b84" stop-opacity="0.35" />
          <stop offset="100%" stop-color="#10181d" stop-opacity="0" />
        </radialGradient>
      </defs>
      <rect width="100" height="70" fill="url(#ecoFog)" />
      ${blobs}
    </svg>`;
  }

  function showEcoSocial(payload) {
    if (!payload) {
      hideEcoSocial();
      return;
    }
    ecoPulse.textContent = payload.headline || "";
    ecoNarrative.textContent = payload.narrative || (payload.narratives && payload.narratives[0]) || "";
    renderHeatmap(payload.heatmap);
    ecoSocial.classList.remove("hidden");
  }

  async function loadEcoPulseFallback() {
    try {
      const res = await fetch(`${API_BASE}/api/eco-pulse`);
      if (!res.ok) return null;
      return await res.json();
    } catch (err) {
      return null;
    }
  }

  function applyPhase() {
    const phase = PHASES[breathPhaseIdx];
    breathLeft = phase.seconds;
    breathCircle.className = `breath-circle ${phase.cls}`;
    breathPhase.textContent = `${phase.name} · ${phase.seconds}`;
    breathCount.textContent = String(breathLeft);
  }

  function tickBreath() {
    breathLeft -= 1;
    if (breathLeft <= 0) {
      breathPhaseIdx = (breathPhaseIdx + 1) % PHASES.length;
      applyPhase();
      return;
    }
    breathCount.textContent = String(breathLeft);
  }

  function startBreathing() {
    stopBreathing(false);
    showBreathing(true);
    breathPhaseIdx = 0;
    applyPhase();
    breathTimer = window.setInterval(tickBreath, 1000);
  }

  function stopBreathing(hide) {
    if (breathTimer) {
      window.clearInterval(breathTimer);
      breathTimer = null;
    }
    breathCircle.className = "breath-circle";
    if (hide) showBreathing(false);
  }

  breathStart.addEventListener("click", startBreathing);
  breathStop.addEventListener("click", () => stopBreathing(false));

  function openCrisis(kind) {
    crisisText.textContent =
      "Há risco que pede presença humana agora. Ligue 188 (CVV) e 192 (SAMU). ABRATA e o CAPS do município são rede de apoio — não substituem o telefone. Este aviso só fecha depois do reconhecimento.";
    crisisAck.checked = false;
    crisisClose.disabled = true;
    crisisModal.classList.remove("hidden");
  }

  crisisAck.addEventListener("change", () => {
    crisisClose.disabled = !crisisAck.checked;
  });
  crisisClose.addEventListener("click", () => {
    if (!crisisAck.checked) return;
    crisisModal.classList.add("hidden");
  });

  function applyUi(ui) {
    if (!ui) return;
    if (ui.show_breathing) {
      showBreathing(true);
      if (ui.eco_social) showEcoSocial(ui.eco_social);
      else loadEcoPulseFallback().then((pulse) => pulse && showEcoSocial(pulse));
    }
    if (ui.emergency_dial === "192" && !ui.show_breathing) {
      showBreathing(false);
      hideEcoSocial();
      stopBreathing(true);
    }
    if (ui.crisis_modal === "188" || ui.crisis_modal === "188_192") {
      openCrisis(ui.crisis_modal);
      hideEcoSocial();
      showBreathing(false);
    }
  }

  async function checkHealth() {
    try {
      const res = await fetch(`${API_BASE}/api/health`);
      if (!res.ok) throw new Error("health down");
      await res.json();
      healthPill.textContent = "Serviço disponível";
      healthPill.classList.remove("is-down");
    } catch (err) {
      healthPill.textContent = "API indisponível";
      healthPill.classList.add("is-down");
    }
  }

  async function ensureSession() {
    if (sessionId) return sessionId;
    try {
      const res = await fetch(`${API_BASE}/api/session`, { method: "POST" });
      const data = await res.json();
      sessionId = data.session_id || null;
    } catch (err) {
      sessionId = null;
    }
    return sessionId;
  }

  async function startNewSession() {
    const previous = sessionId;
    sessionId = null;
    lastUserText = "";
    sending = false;
    sendBtn.disabled = false;
    transcript.innerHTML = "";
    hideExtractCard();
    hideEcoSocial();
    stopBreathing(true);
    crisisModal.classList.add("hidden");
    if (previous) {
      try {
        await fetch(`${API_BASE}/api/session/${encodeURIComponent(previous)}`, { method: "DELETE" });
      } catch (err) {
        /* sessão local some no próximo POST */
      }
    }
    await ensureSession();
    appendBubble("assistant", WELCOME);
    input.value = "";
    input.setCustomValidity("");
    input.focus();
  }

  async function sendMessage(text) {
    if (!text || sending) return;
    lastUserText = text;
    sending = true;
    sendBtn.disabled = true;
    appendBubble("user", text);
    setTyping(true);
    try {
      await ensureSession();
      const minTyping = new Promise((resolve) => window.setTimeout(resolve, 400));
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      });
      await minTyping;
      const data = await res.json();
      setTyping(false);
      if (!res.ok) {
        appendBubble("assistant", data.error || "Não foi possível concluir o acolhimento.");
        return;
      }
      sessionId = data.session_id || sessionId;
      appendBubble("assistant", data.reply || data.disclaimer);
      applyUi(data.ui);
      if ((data.reply || "").includes("4-7-8")) {
        showBreathing(true);
        if (data.ui && data.ui.eco_social) showEcoSocial(data.ui.eco_social);
      }
      if (looksLikeClinicalNarrative(text)) {
        extractNarrative(text);
      }
    } catch (err) {
      setTyping(false);
      appendBubble(
        "assistant",
        "Falha de rede ao falar com o backend. Confirme se o Flask está em execução.\n\nEste assistente não substitui atendimento médico. Em emergências cardíacas, ligue 192 (SAMU). Em crise emocional com ideação, ligue 188 (CVV)."
      );
    } finally {
      sending = false;
      sendBtn.disabled = false;
      input.focus();
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text) {
      input.setCustomValidity(EMPTY_COMPOSER);
      input.reportValidity();
      return;
    }
    input.setCustomValidity("");
    input.value = "";
    sendMessage(text);
  });

  input.addEventListener("invalid", () => {
    input.setCustomValidity(EMPTY_COMPOSER);
  });
  input.addEventListener("input", () => {
    input.setCustomValidity("");
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  document.querySelectorAll("[data-chip]").forEach((btn) => {
    btn.addEventListener("click", () => sendMessage(btn.getAttribute("data-chip")));
  });

  extractChip.addEventListener("click", () => {
    const draft = input.value.trim();
    extractNarrative(draft || lastUserText);
  });
  extractClose.addEventListener("click", hideExtractCard);
  resetSessionBtn.addEventListener("click", () => {
    startNewSession();
  });

  appendBubble("assistant", WELCOME);
  checkHealth();
})();
