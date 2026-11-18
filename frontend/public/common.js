// Utilitaires partagés par les deux pages. Toutes les requêtes passent par nginx (/api/* -> API).
const API = "/api";

const $ = (id) => document.getElementById(id);
const fmtInt = new Intl.NumberFormat("fr-FR");
const fmtDate = new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", timeStyle: "medium" });
const fmtDay = new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium" });
const fmtRel = new Intl.RelativeTimeFormat("fr", { numeric: "auto" });

async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(API + path, {
    method,
    cache: "no-store",
    headers: body ? { "Content-Type": "application/json", Accept: "application/json" } : { Accept: "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") detail = data.detail;
      else if (Array.isArray(data.detail)) detail = data.detail.map((d) => d.msg).join(", ");
    } catch { /* réponse non JSON (ex. 502 nginx) */ }
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}

function showError(el, err) {
  el.textContent = err ? `Erreur : ${err.message}` : "";
  el.hidden = !err;
}

function timeAgo(date) {
  const seconds = Math.round((date - Date.now()) / 1000);
  for (const [unit, size] of [["day", 86400], ["hour", 3600], ["minute", 60]]) {
    if (Math.abs(seconds) >= size) return fmtRel.format(Math.round(seconds / size), unit);
  }
  return fmtRel.format(seconds, "second");
}

function el(tag, props = {}, ...children) {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children.filter((c) => c !== null && c !== undefined));
  return node;
}

// Badge de version commun aux deux pages.
api("/health").then((d) => { $("version").textContent = `version ${d.version}`; }).catch(() => {});
