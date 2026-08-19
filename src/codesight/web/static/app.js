(function () {
  const STORAGE_KEY = "codesight_api_key";
  const messagesEl = document.getElementById("messages");
  const queryForm = document.getElementById("query-form");
  const queryInput = document.getElementById("query-input");
  const apiKeyInput = document.getElementById("api-key");
  const saveKeyBtn = document.getElementById("save-key");
  const indexBtn = document.getElementById("index-btn");
  const statusPill = document.getElementById("status-pill");
  const modeHint = document.getElementById("mode-hint");
  const fileGlobInput = document.getElementById("file-glob");
  const sourceFilter = document.getElementById("source-filter");

  let publicConfig = { auth_required: true, llm_backend: "claude" };

  function getApiKey() {
    return sessionStorage.getItem(STORAGE_KEY) || "";
  }

  function headers() {
    const h = { "Content-Type": "application/json" };
    const key = getApiKey();
    if (key) h["X-API-Key"] = key;
    return h;
  }

  function getMode() {
    const checked = document.querySelector('input[name="mode"]:checked');
    return checked ? checked.value : "search";
  }

  function locationLabel(source) {
    const scope = source.scope || "";
    if (scope.startsWith("slide ")) {
      return `slide ${source.start_line}-${source.end_line}`;
    }
    if (scope.startsWith("page ") || scope.startsWith("section ")) {
      return `page ${source.start_line}-${source.end_line}`;
    }
    return `lines ${source.start_line}-${source.end_line}`;
  }

  function appendMessage(html, className) {
    const div = document.createElement("div");
    div.className = "msg " + (className || "");
    div.innerHTML = html;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function renderSources(sources) {
    if (!sources || !sources.length) return "";
    return sources
      .map((s, i) => {
        const loc = locationLabel(s);
        const snippet = (s.snippet || "").slice(0, 600);
        const sourceLabel = s.source_label || (s.source === "holus" ? "Holus lineage" : "Indexed files");
        const lineage = s.lineage_node_id ? ` · ${escapeHtml(s.lineage_node_id)}` : "";
        return `<details class="source-card">
          <summary>[${i + 1}] ${escapeHtml(sourceLabel)} · ${escapeHtml(s.file_path)} (${loc}) — ${escapeHtml(s.scope)}${lineage}</summary>
          <pre>${escapeHtml(snippet)}</pre>
        </details>`;
      })
      .join("");
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function apiFetch(path, options) {
    const res = await fetch(path, options);
    let body = null;
    try {
      body = await res.json();
    } catch (_) {
      body = null;
    }
    if (!res.ok) {
      const detail = body && body.detail ? body.detail : res.statusText;
      const msg = typeof detail === "object" ? JSON.stringify(detail) : detail;
      throw new Error(msg || `HTTP ${res.status}`);
    }
    return body;
  }

  async function refreshHealth() {
    try {
      const health = await apiFetch("/api/health");
      if (health.indexed) {
        statusPill.textContent = "indexed";
        statusPill.className = "pill pill-ok";
      } else {
        statusPill.textContent = "not indexed";
        statusPill.className = "pill pill-warn";
      }
    } catch (e) {
      statusPill.textContent = "offline";
      statusPill.className = "pill pill-muted";
    }
  }

  async function loadConfig() {
    try {
      publicConfig = await apiFetch("/api/config");
      if (!publicConfig.auth_required) {
        modeHint.textContent +=
          " Authentication is disabled on this dev deployment.";
      }
    } catch (_) {
      /* health will show offline */
    }
  }

  document.querySelectorAll('input[name="mode"]').forEach((el) => {
    el.addEventListener("change", () => {
      if (getMode() === "ask") {
        modeHint.textContent =
          `Ask sends retrieved chunks to the configured LLM (${publicConfig.llm_backend}). Search works without any LLM key.`;
      } else {
        modeHint.textContent =
          "Search uses hybrid BM25 + vector retrieval on this server. No LLM required.";
      }
    });
  });

  saveKeyBtn.addEventListener("click", () => {
    sessionStorage.setItem(STORAGE_KEY, apiKeyInput.value.trim());
    appendMessage("<div class='msg-meta'>API key saved for this browser session.</div>", "msg-user");
  });

  indexBtn.addEventListener("click", async () => {
    indexBtn.disabled = true;
    try {
      const result = await apiFetch("/api/index", {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ force_rebuild: false }),
      });
      appendMessage(
        `<div class="msg-meta">Index complete</div>
         <p>${result.total_files} files, ${result.total_chunks} chunks (${result.duration_seconds.toFixed(1)}s)</p>`,
        ""
      );
      await refreshHealth();
    } catch (e) {
      appendMessage(`<div class="msg-meta">Index failed</div><p>${escapeHtml(e.message)}</p>`, "msg-error");
    } finally {
      indexBtn.disabled = false;
    }
  });

  queryForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = queryInput.value.trim();
    if (!text) return;
    appendMessage(`<p>${escapeHtml(text)}</p>`, "msg-user");
    queryInput.value = "";
    queryInput.disabled = true;

    const mode = getMode();
    const glob = fileGlobInput.value.trim() || null;
    const source = sourceFilter.value || null;

    try {
      if (mode === "search") {
        const data = await apiFetch("/api/search", {
          method: "POST",
          headers: headers(),
          body: JSON.stringify({ query: text, top_k: 8, file_glob: glob, source }),
        });
        const results = data.results || [];
        if (!results.length) {
          appendMessage("<p>No results. Try re-indexing or broadening your query.</p>", "");
        } else {
          appendMessage(
            `<div class="msg-meta">Search — ${results.length} result(s), local retrieval</div>
             ${renderSources(results)}`,
            ""
          );
        }
      } else {
        const data = await apiFetch("/api/ask", {
          method: "POST",
          headers: headers(),
          body: JSON.stringify({ question: text, top_k: 5, file_glob: glob, source }),
        });
        appendMessage(
          `<div class="msg-meta">Ask — synthesized by ${escapeHtml(data.model || "LLM")}</div>
           <p>${escapeHtml(data.text || "")}</p>
           ${renderSources(data.sources)}`,
          ""
        );
      }
    } catch (err) {
      appendMessage(`<div class="msg-meta">Error</div><p>${escapeHtml(err.message)}</p>`, "msg-error");
    } finally {
      queryInput.disabled = false;
      queryInput.focus();
    }
  });

  apiKeyInput.value = getApiKey();
  loadConfig().then(refreshHealth);
})();
