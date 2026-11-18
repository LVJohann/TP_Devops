// Page « Visites & services » : fonctionnalités 1 à 3 (utilitaires dans common.js).
const STATUS_REFRESH_MS = 10_000;

/* ---------- 1. Compteur de visites ---------- */

const podsSeen = new Map();

function renderPods() {
  const list = $("pods");
  list.replaceChildren();
  if (podsSeen.size === 0) {
    list.append(el("li", { className: "empty", textContent: "Aucun pour l'instant" }));
    return;
  }
  for (const [pod, hits] of podsSeen) list.append(el("li", {}, pod, el("b", { textContent: `×${hits}` })));
}

async function loadCount() {
  try {
    const data = await api("/visits/count");
    $("visits-count").textContent = fmtInt.format(data.visits);
  } catch {
    // Pas bloquant : le compteur s'affichera au premier clic.
  }
}

async function recordVisits(times) {
  const buttons = [$("visit-btn"), $("burst-btn")];
  buttons.forEach((b) => (b.disabled = true));
  try {
    for (let i = 0; i < times; i++) {
      const data = await api("/");
      const pod = data.pod || "inconnu";
      $("visits-count").textContent = fmtInt.format(data.visits);
      $("last-pod").textContent = pod;
      podsSeen.set(pod, (podsSeen.get(pod) || 0) + 1);
      renderPods();
    }
    showError($("visit-error"), null);
    await loadHistory({ highlight: times });
  } catch (err) {
    showError($("visit-error"), err);
  } finally {
    buttons.forEach((b) => (b.disabled = false));
  }
}

/* ---------- 2. Historique des visites ---------- */

async function loadHistory({ highlight = 0 } = {}) {
  const body = $("history-body");
  try {
    const data = await api(`/visits?limit=${$("limit").value}`);
    $("history-total").textContent = fmtInt.format(data.total);
    body.replaceChildren();
    if (data.items.length === 0) {
      const td = body.insertRow().insertCell();
      td.colSpan = 3;
      td.className = "empty";
      td.textContent = "Aucune visite pour l'instant — cliquez sur « Enregistrer une visite ».";
    }
    data.items.forEach((item, index) => {
      const at = new Date(item.at);
      const tr = body.insertRow();
      if (index < highlight) tr.className = "fresh";
      tr.insertCell().textContent = `#${item.id}`;
      tr.insertCell().textContent = fmtDate.format(at);
      tr.insertCell().textContent = timeAgo(at);
    });
    showError($("history-error"), null);
  } catch (err) {
    showError($("history-error"), err);
  }
}

/* ---------- 3. État des services ---------- */

function setService(name, state) {
  const li = document.querySelector(`#services li[data-service="${name}"]`);
  li.classList.remove("ok", "down");
  if (state === "ok" || state === "down") li.classList.add(state);
  li.querySelector(".state").textContent =
    state === "ok" ? "Opérationnel" : state === "down" ? "Indisponible" : "Inconnu";
}

async function loadStatus() {
  const overall = $("overall");
  try {
    const data = await api("/status");
    for (const [name, state] of Object.entries(data.services)) setService(name, state);
    overall.className = `overall ${data.status}`;
    overall.textContent = data.status === "ok"
      ? "Tous les services sont opérationnels."
      : "Service dégradé : au moins une dépendance est indisponible.";
  } catch (err) {
    setService("api", "down");
    setService("redis", "unknown");
    setService("postgres", "unknown");
    overall.className = "overall down";
    overall.textContent = `API injoignable (${err.message}).`;
  }
  $("status-updated").textContent = `Vérifié à ${new Date().toLocaleTimeString("fr-FR")}`;
}

/* ---------- Initialisation ---------- */

$("visit-btn").addEventListener("click", () => recordVisits(1));
$("burst-btn").addEventListener("click", () => recordVisits(10));
$("history-btn").addEventListener("click", () => loadHistory());
$("limit").addEventListener("change", () => loadHistory());
$("status-btn").addEventListener("click", loadStatus);

loadCount();
loadHistory();
loadStatus();
setInterval(loadStatus, STATUS_REFRESH_MS);
