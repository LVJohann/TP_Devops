const API = '/api/tasks';
const tasksEl = document.getElementById('tasks');
const messageEl = document.getElementById('message');

async function loadTasks() {
  try {
    const response = await fetch(API);
    if (!response.ok) throw new Error('API indisponible');
    const tasks = await response.json();
    tasksEl.innerHTML = '';
    if (!tasks.length) { tasksEl.innerHTML = '<p>Aucune tâche pour le moment.</p>'; return; }
    tasks.forEach(task => {
      const item = document.createElement('article');
      item.className = `task ${task.status === 'Terminee' ? 'done' : ''}`;
      const main = document.createElement('div'); main.className = 'task-main';
      const title = document.createElement('div'); title.className = 'task-title'; title.textContent = task.title;
      const meta = document.createElement('div'); meta.className = 'task-meta';
      meta.textContent = `${task.description || 'Sans description'} · Priorité ${task.priority}${task.due_date ? ' · Échéance ' + task.due_date : ''}`;
      main.append(title, meta);
      const status = document.createElement('select');
      ['A faire', 'En cours', 'Terminee'].forEach(value => { const option=document.createElement('option'); option.value=value; option.textContent=value; status.append(option); });
      status.value = task.status; status.addEventListener('change', () => updateTask(task.id, {status:status.value}));
      const del = document.createElement('button'); del.className='delete'; del.textContent='Supprimer'; del.addEventListener('click', () => deleteTask(task.id));
      item.append(main, status, del); tasksEl.append(item);
    });
  } catch (error) { tasksEl.innerHTML = '<p>Impossible de contacter le serveur. Vérifiez les services.</p>'; }
}

async function updateTask(id, data) {
  await fetch(`${API}/${id}`, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
  loadTasks();
}
async function deleteTask(id) {
  await fetch(`${API}/${id}`, {method:'DELETE'}); loadTasks();
}
document.getElementById('task-form').addEventListener('submit', async event => {
  event.preventDefault(); messageEl.textContent='';
  const payload = {title:document.getElementById('title').value, description:document.getElementById('description').value, priority:document.getElementById('priority').value, due_date:document.getElementById('due-date').value || null};
  const response = await fetch(API, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
  if (!response.ok) { messageEl.textContent='Erreur lors de la création de la tâche.'; return; }
  event.target.reset(); loadTasks();
});
document.getElementById('refresh').addEventListener('click', loadTasks);
loadTasks();