// Page « Tâches » : fonctionnalités 4 à 9 (utilitaires dans common.js).
const STATUSES = [["A faire", "À faire"], ["En cours", "En cours"], ["Terminee", "Terminée"]];
const PRIORITIES = ["Haute", "Normale", "Basse"];
const ACTIONS = { creation: "Création", statut: "Statut", modification: "Modification", suppression: "Suppression" };
const today = new Date().toISOString().slice(0, 10);

function options(select, values, current) {
  for (const v of values) {
    const [value, label] = Array.isArray(v) ? v : [v, v];
    select.append(el("option", { value, textContent: label, selected: value === current }));
  }
  return select;
}

async function refreshAll() {
  await Promise.all([loadTasks(), loadStats(), loadActivity()]);
}

async function mutate(action, errorEl = $("list-error")) {
  try {
    await action();
    showError(errorEl, null);
    await refreshAll();
    return true;
  } catch (err) {
    showError(errorEl, err);
    return false;
  }
}

/* ---------- 4. Création ---------- */

$("task-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    title: $("title").value,
    description: $("description").value,
    priority: $("priority").value,
    due_date: $("due-date").value || null,
  };
  if (await mutate(() => api("/tasks", { method: "POST", body: payload }), $("form-error"))) {
    event.target.reset();
    $("title").focus();
  }
});

/* ---------- 5. Liste, recherche et filtres ---------- */

function taskView(task) {
  const late = task.due_date && task.due_date < today && task.status !== "Terminee";
  const meta = el("div", { className: "task-meta" },
    el("span", { className: `pill ${task.priority}`, textContent: `Priorité ${task.priority.toLowerCase()}` }),
    task.due_date
      ? el("span", { className: `pill${late ? " late" : ""}`, textContent: `${late ? "En retard · " : "Échéance "}${fmtDay.format(new Date(task.due_date))}` })
      : null,
  );
  const main = el("div", { className: "task-main" },
    el("div", { className: "task-title", textContent: task.title }),
    task.description ? el("p", { className: "task-desc", textContent: task.description }) : null,
    meta,
  );

  // 6. Changement de statut
  const status = options(el("select", { ariaLabel: "Statut" }), STATUSES, task.status);
  status.addEventListener("change", () =>
    mutate(() => api(`/tasks/${task.id}`, { method: "PATCH", body: { status: status.value } })));

  // 7. Modification / suppression
  const edit = el("button", { className: "btn small", type: "button", textContent: "Modifier" });
  const del = el("button", { className: "btn small danger", type: "button", textContent: "Supprimer" });
  del.addEventListener("click", () => {
    if (confirm(`Supprimer « ${task.title} » ?`)) mutate(() => api(`/tasks/${task.id}`, { method: "DELETE" }));
  });

  const item = el("article", { className: `task${task.status === "Terminee" ? " done" : ""}` }, main, status, edit, del);
  edit.addEventListener("click", () => toggleEditor(item, task));
  return item;
}

function toggleEditor(item, task) {
  const existing = item.querySelector(".task-edit");
  if (existing) return existing.remove();
  const title = el("input", { value: task.title, maxLength: 200, required: true, ariaLabel: "Titre" });
  const description = el("input", { value: task.description, placeholder: "Description", ariaLabel: "Description" });
  const priority = options(el("select", { ariaLabel: "Priorité" }), PRIORITIES, task.priority);
  const due = el("input", { type: "date", value: task.due_date || "", ariaLabel: "Échéance" });
  const form = el("form", { className: "form task-edit" },
    title, description,
    el("div", { className: "form-row" }, priority, due,
      el("button", { className: "btn primary", type: "submit", textContent: "Enregistrer" })),
  );
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    mutate(() => api(`/tasks/${task.id}`, {
      method: "PATCH",
      body: { title: title.value, description: description.value, priority: priority.value, due_date: due.value || null },
    }));
  });
  item.append(form);
  title.focus();
}

async function loadTasks() {
  const params = new URLSearchParams({ sort: $("sort").value });
  if ($("search").value.trim()) params.set("q", $("search").value.trim());
  if ($("filter-status").value) params.set("status", $("filter-status").value);
  if ($("filter-priority").value) params.set("priority", $("filter-priority").value);
  const list = $("tasks");
  try {
    const tasks = await api(`/tasks?${params}`);
    const filtered = params.has("q") || params.has("status") || params.has("priority");
    list.replaceChildren(...(tasks.length
      ? tasks.map(taskView)
      : [el("p", { className: "empty", textContent: filtered ? "Aucune tâche ne correspond aux filtres." : "Aucune tâche pour le moment." })]));
    showError($("list-error"), null);
  } catch (err) {
    list.replaceChildren();
    showError($("list-error"), err);
  }
}

let searchTimer;
$("search").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadTasks, 250); });
["filter-status", "filter-priority", "sort"].forEach((id) => $(id).addEventListener("change", loadTasks));

/* ---------- 8. Statistiques ---------- */

async function loadStats() {
  try {
    const s = await api("/tasks/stats");
    for (const key of ["total", "todo", "doing", "done", "urgent", "overdue"]) $(`st-${key}`).textContent = fmtInt.format(s[key]);
    $("completion").textContent = `${s.completion} % terminées`;
    $("progress-bar").style.width = `${s.completion}%`;
  } catch {
    $("completion").textContent = "Indisponible";
  }
}

/* ---------- 9. Journal d'activité ---------- */

async function loadActivity() {
  const list = $("activity");
  try {
    const events = await api("/activity?limit=15");
    list.replaceChildren(...(events.length
      ? events.map((e) => el("li", { className: e.action },
          el("span", { className: "dot" }),
          el("p", {}, el("strong", { textContent: `${ACTIONS[e.action] || e.action} · ` }), e.detail),
          el("time", { dateTime: e.at, textContent: `${fmtDate.format(new Date(e.at))} · ${timeAgo(new Date(e.at))}` })))
      : [el("li", { className: "empty", textContent: "Aucune activité pour le moment." })]));
  } catch {
    list.replaceChildren(el("li", { className: "empty", textContent: "Journal indisponible." }));
  }
}

$("activity-btn").addEventListener("click", loadActivity);

refreshAll();
