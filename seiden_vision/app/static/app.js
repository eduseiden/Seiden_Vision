const $ = (selector) => document.querySelector(selector);

function basePath(path) {
  const current = window.location.pathname;
  const root = current.endsWith("/") ? current : `${current}/`;
  return new URL(path.replace(/^\//, ""), `${window.location.origin}${root}`).toString();
}

async function api(path, options = {}) {
  const response = await fetch(basePath(path), {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) }
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.message || `Erro HTTP ${response.status}`);
  return data;
}

function showMessage(text, isError = false) {
  const box = $("#message");
  box.textContent = text;
  box.classList.remove("hidden");
  box.style.background = isError ? "rgba(159,47,47,.15)" : "rgba(46,76,94,.12)";
}

function formatDate(value) {
  if (!value) return "—";
  return new Date(value).toLocaleString("pt-BR");
}

async function loadDashboard() {
  try {
    const [health, stats, analyses] = await Promise.all([
      api("api/v1/health"),
      api("api/v1/stats"),
      api("api/v1/analyses?limit=100")
    ]);
    $("#healthStatus").textContent = health.status === "ok" ? "Online" : health.status;
    $("#todayCount").textContent = stats.today;
    $("#queueSize").textContent = health.queue_size;

    const body = $("#historyBody");
    if (!analyses.items.length) {
      body.innerHTML = '<tr><td colspan="7">Nenhuma análise registrada.</td></tr>';
      return;
    }
    body.innerHTML = analyses.items.map(item => {
      const statusClass = item.status === "success" ? "success" :
                          item.status === "duplicate" ? "duplicate" : "error";
      const confidence = item.confidence == null ? "—" : `${Number(item.confidence).toFixed(2)}%`;
      const time = item.processing_ms == null ? "—" : `${item.processing_ms} ms`;
      return `<tr>
        <td>${formatDate(item.created_at)}</td>
        <td>${escapeHtml(item.source || "—")}</td>
        <td>${escapeHtml(item.person || "—")}</td>
        <td><span class="badge badge-${statusClass}">${escapeHtml(item.status)}</span></td>
        <td>${escapeHtml(item.dominant_emotion || item.error || "—")}</td>
        <td>${confidence}</td>
        <td>${time}</td>
      </tr>`;
    }).join("");
  } catch (error) {
    $("#healthStatus").textContent = "Erro";
    console.error(error);
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

$("#analyzeForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  try {
    const result = await api("api/v1/analyze", {
      method: "POST",
      body: JSON.stringify({
        source: $("#source").value,
        image_url: $("#imageUrl").value,
        person: $("#person").value || null
      })
    });
    showMessage(`Imagem colocada na fila. Itens na fila: ${result.queue_size}.`);
    setTimeout(loadDashboard, 1200);
  } catch (error) {
    showMessage(error.message, true);
  } finally {
    button.disabled = false;
  }
});

$("#refresh").addEventListener("click", loadDashboard);

$("#clearHistory").addEventListener("click", async () => {
  if (!confirm("Deseja apagar todo o histórico local?")) return;
  try {
    const result = await api("api/v1/analyses", { method: "DELETE" });
    showMessage(`${result.deleted} registro(s) removido(s).`);
    loadDashboard();
  } catch (error) {
    showMessage(error.message, true);
  }
});

$("#publishTest").addEventListener("click", async () => {
  try {
    await api("api/v1/publish-test", { method: "POST", body: "{}" });
    showMessage("Sensor de teste publicado no Home Assistant.");
  } catch (error) {
    showMessage(error.message, true);
  }
});

loadDashboard();
setInterval(loadDashboard, 5000);
