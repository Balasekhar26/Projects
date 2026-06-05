const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function item(text, cls = "item") {
  const node = document.createElement("div");
  node.className = cls;
  node.textContent = text;
  return node;
}

async function refreshStatus() {
  const data = await api("/api/status");
  $("status").textContent = [
    `Ollama: ${data.ollama_ok ? "OK" : "Not ready"}`,
    `Planner: ${data.models.planner}`,
    `Coder: ${data.models.coder}`,
    `Fast: ${data.models.fast}`,
    `Memory: ${data.memory_count}`,
    `Shell: ${data.shell_enabled ? "enabled" : "off"}`,
  ].join("\n");
}

async function refreshTasks() {
  const data = await api("/api/tasks");
  $("task-list").replaceChildren(
    ...data.tasks.map((task) =>
      item(`${task.status.toUpperCase()} ${task.goal}\n\n${task.steps.map((s) => `- ${s.status}: ${s.title}`).join("\n")}\n\n${task.final_answer || ""}`)
    )
  );
}

async function refreshEvents() {
  const data = await api("/api/events");
  $("event-list").replaceChildren(
    ...data.events.reverse().map((event) => item(`${event.timestamp}\n${event.kind}: ${event.message}`))
  );
}

document.querySelectorAll("nav button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("nav button, .view").forEach((node) => node.classList.remove("active"));
    button.classList.add("active");
    $(button.dataset.view).classList.add("active");
    if (button.dataset.view === "tasks") refreshTasks();
    if (button.dataset.view === "events") refreshEvents();
  });
});

$("ask-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const prompt = $("prompt").value.trim();
  if (!prompt) return;
  $("messages").appendChild(item(prompt, "message user"));
  $("prompt").value = "";
  const waiting = item("Thinking...", "message");
  $("messages").appendChild(waiting);
  const data = await api("/api/ask", {
    method: "POST",
    body: JSON.stringify({ prompt, mode: $("mode").value }),
  });
  waiting.textContent = data.answer;
  refreshStatus();
});

$("task-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const goal = $("goal").value.trim();
  if (!goal) return;
  $("task-list").prepend(item("Running task..."));
  const data = await api("/api/task", {
    method: "POST",
    body: JSON.stringify({ goal, execute_tools: $("execute-tools").checked }),
  });
  $("goal").value = "";
  await refreshTasks();
  await refreshEvents();
  refreshStatus();
});

$("memory-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = $("memory-text").value.trim();
  if (!text) return;
  await api("/api/memory", { method: "POST", body: JSON.stringify({ text }) });
  $("memory-text").value = "";
  refreshStatus();
});

$("recall-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = encodeURIComponent($("memory-query").value.trim());
  const data = await api(`/api/memory/search?q=${query}`);
  $("memory-results").replaceChildren(...data.items.map((text) => item(text)));
});

refreshStatus();
