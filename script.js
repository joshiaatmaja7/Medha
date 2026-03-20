(() => {
  // ---------- Theme ----------
  const themeButtons = Array.from(document.querySelectorAll("[data-theme-btn]"));
  const applyTheme = (theme) => {
    const t = theme || "stripe";
    document.documentElement.setAttribute("data-theme", t);
    try { localStorage.setItem("medha_theme", t); } catch (_) {}
  };
  try {
    const saved = localStorage.getItem("medha_theme");
    applyTheme(saved || "stripe");
  } catch (_) {
    applyTheme("stripe");
  }
  themeButtons.forEach((btn) => {
    btn.addEventListener("click", () => applyTheme(btn.getAttribute("data-theme-btn")));
  });

  // ---------- Chat autoscroll ----------
  const chatLog = document.querySelector("[data-chat-log]");
  if (chatLog) chatLog.scrollTop = chatLog.scrollHeight;

  // ---------- Mic (speech recognition placeholder) ----------
  const micBtn = document.querySelector("[data-mic]");
  const chatInput = document.querySelector(".chatComposer input[name='message']");
  if (micBtn && chatInput) {
    micBtn.addEventListener("click", () => {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SpeechRecognition) {
        alert("Speech input not supported in this browser.");
        return;
      }
      const rec = new SpeechRecognition();
      rec.lang = "en-US";
      rec.interimResults = false;
      rec.maxAlternatives = 1;
      micBtn.classList.add("listening");
      rec.onresult = (e) => {
        const t = e.results?.[0]?.[0]?.transcript;
        if (t) chatInput.value = (chatInput.value ? (chatInput.value + " ") : "") + t;
      };
      rec.onend = () => micBtn.classList.remove("listening");
      rec.onerror = () => micBtn.classList.remove("listening");
      rec.start();
    });
  }

  // ---------- Focus timer ----------
  const focusRoot = document.querySelector("[data-focus]");
  if (focusRoot) {
    const display = focusRoot.querySelector("[data-focus-display]");
    const minutesInput = focusRoot.querySelector("[data-focus-minutes]");
    const startBtn = focusRoot.querySelector("[data-focus-start]");
    const pauseBtn = focusRoot.querySelector("[data-focus-pause]");
    const resetBtn = focusRoot.querySelector("[data-focus-reset]");

    let total = 25 * 60;
    let remaining = total;
    let running = false;
    let tId = null;

    const fmt = (s) => {
      const m = Math.floor(s / 60);
      const ss = String(s % 60).padStart(2, "0");
      return `${m}:${ss}`;
    };
    const render = () => {
      if (display) display.textContent = fmt(remaining);
      if (pauseBtn) pauseBtn.textContent = running ? "Pause" : "Resume";
    };
    const tick = () => {
      if (!running) return;
      remaining = Math.max(0, remaining - 1);
      render();
      if (remaining === 0) {
        running = false;
        clearInterval(tId);
        tId = null;
        try { new Audio("data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAgLsAAAB3AQACABAAZGF0YQAAAAA=").play(); } catch (_) {}
      }
    };
    const start = () => {
      running = true;
      if (!tId) tId = setInterval(tick, 1000);
      render();
    };
    const pause = () => {
      running = !running;
      render();
    };
    const reset = () => {
      running = false;
      clearInterval(tId);
      tId = null;
      const mins = Math.max(1, Math.min(180, parseInt(minutesInput?.value || "25", 10) || 25));
      total = mins * 60;
      remaining = total;
      render();
    };
    if (startBtn) startBtn.addEventListener("click", start);
    if (pauseBtn) pauseBtn.addEventListener("click", pause);
    if (resetBtn) resetBtn.addEventListener("click", reset);
    if (minutesInput) minutesInput.addEventListener("change", reset);
    render();
  }

  // ---------- Notes preview (if present) ----------
  const mdPreview = document.querySelector("[data-md-preview]");
  const mdTextarea = document.querySelector("#noteBody");
  const renderBasicMarkdown = (src) => {
    const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    const lines = (src || "").split(/\r?\n/);
    let html = "";
    let inList = false;
    for (const raw of lines) {
      const line = raw.trimEnd();
      if (/^\s*###\s+/.test(line)) { if (inList) { html += "</ul>"; inList = false; } html += `<h3>${esc(line.replace(/^\s*###\s+/, ""))}</h3>`; continue; }
      if (/^\s*##\s+/.test(line)) { if (inList) { html += "</ul>"; inList = false; } html += `<h2>${esc(line.replace(/^\s*##\s+/, ""))}</h2>`; continue; }
      if (/^\s*#\s+/.test(line)) { if (inList) { html += "</ul>"; inList = false; } html += `<h1>${esc(line.replace(/^\s*#\s+/, ""))}</h1>`; continue; }
      if (/^\s*-\s+/.test(line)) { if (!inList) { html += "<ul>"; inList = true; } html += `<li>${esc(line.replace(/^\s*-\s+/, ""))}</li>`; continue; }
      if (line === "") { if (inList) { html += "</ul>"; inList = false; } continue; }
      if (inList) { html += "</ul>"; inList = false; }
      const safe = esc(line).replace(/`([^`]+)`/g, "<code>$1</code>");
      html += `<p>${safe}</p>`;
    }
    if (inList) html += "</ul>";
    return html;
  };
  if (mdPreview && mdTextarea) {
    const refresh = () => { mdPreview.innerHTML = renderBasicMarkdown(mdTextarea.value); };
    mdTextarea.addEventListener("input", refresh);
    refresh();
  }

  // ---------- Tasks shortcuts ----------
  const tasksSearch = document.querySelector(".tasksSearch input[name='q']");
  const addTaskInput = document.querySelector("input#title[name='title']");
  document.addEventListener("keydown", (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const tag = (document.activeElement && document.activeElement.tagName) || "";
    const isTyping = ["INPUT", "TEXTAREA", "SELECT"].includes(tag);

    if (e.key === "/" && tasksSearch) {
      e.preventDefault();
      tasksSearch.focus();
      tasksSearch.select?.();
      return;
    }
    if (e.key.toLowerCase() === "n" && addTaskInput && !isTyping) {
      e.preventDefault();
      addTaskInput.focus();
      return;
    }
    if (e.key === "Escape" && document.activeElement) {
      document.activeElement.blur?.();
    }
  });
})();
