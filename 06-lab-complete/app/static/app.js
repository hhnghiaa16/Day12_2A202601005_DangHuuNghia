const state = {
  requestCount: 0,
};

const $ = (id) => document.getElementById(id);

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function setPill(id, label, ok) {
  const el = $(id);
  el.textContent = label;
  el.classList.toggle("ok", ok === true);
  el.classList.toggle("bad", ok === false);
}

function addMessage(kind, title, text) {
  const wrap = document.createElement("article");
  wrap.className = `message ${kind}`;

  const small = document.createElement("small");
  small.textContent = title;

  const body = document.createElement("p");
  body.textContent = text;

  wrap.append(small, body);
  $("messages").appendChild(wrap);
  $("messages").scrollTop = $("messages").scrollHeight;
}

async function fetchJson(path, options = {}) {
  const response = await fetch(path, options);
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : { detail: await response.text() };

  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : pretty(data.detail || data);
    throw new Error(`${response.status} ${detail}`);
  }
  return data;
}

async function refreshStatus() {
  try {
    const health = await fetchJson("/health");
    setPill("healthPill", "Health: ok", true);
    $("environment").textContent = health.environment || "unknown";
    $("version").textContent = health.version || "unknown";
    $("uptime").textContent = `${health.uptime_seconds || 0}s`;
    $("requestCount").textContent = health.total_requests || 0;
    $("rawOutput").textContent = pretty(health);
  } catch (error) {
    setPill("healthPill", "Health: down", false);
    $("rawOutput").textContent = error.message;
  }

  try {
    const ready = await fetchJson("/ready");
    setPill("readyPill", "Ready: yes", true);
    $("redisState").textContent = ready.redis || "ok";
  } catch (error) {
    setPill("readyPill", "Ready: no", false);
    $("redisState").textContent = "unavailable";
  }
}

async function loadMetrics() {
  try {
    const metrics = await fetchJson("/metrics", {
      headers: { "X-API-Key": $("apiKey").value },
    });
    $("rateLimit").textContent = `${metrics.rate_limit_per_minute}/min`;
    $("budget").textContent = `$${metrics.monthly_budget_usd}`;
    $("rawOutput").textContent = pretty(metrics);
  } catch (error) {
    addMessage("error", "Metrics", error.message);
  }
}

async function askAgent(event) {
  event.preventDefault();
  const question = $("question").value.trim();
  const userId = $("userId").value.trim() || "demo-user";
  const apiKey = $("apiKey").value;

  if (!question) return;

  $("askBtn").disabled = true;
  addMessage("user", userId, question);

  try {
    const data = await fetchJson("/ask", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": apiKey,
      },
      body: JSON.stringify({ user_id: userId, question }),
    });
    state.requestCount += 1;
    $("historyCount").textContent = data.history_length;
    $("rawOutput").textContent = pretty(data);
    addMessage("agent", data.model, data.answer);
    await refreshStatus();
  } catch (error) {
    addMessage("error", "Request failed", error.message);
  } finally {
    $("askBtn").disabled = false;
  }
}

$("askForm").addEventListener("submit", askAgent);
$("refreshBtn").addEventListener("click", refreshStatus);
$("metricsBtn").addEventListener("click", loadMetrics);

addMessage("agent", "Production AI Agent", "Ready for a deployment smoke test.");
refreshStatus();
