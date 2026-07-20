const $ = (id) => document.getElementById(id);

// Mode Toggle Handler
const toggleBtn = $("toggle-mode");
toggleBtn.addEventListener("click", () => {
  const isExpert = document.body.classList.toggle("expert-mode");
  toggleBtn.textContent = `Expert Mode: ${isExpert ? "ON" : "OFF"}`;
  addTimelineEntry(`Interface toggled to ${isExpert ? "Expert" : "User"} Mode`);
});

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function createMessageNode(text, sender = "assistant") {
  const node = document.createElement("div");
  node.className = `msg-bubble ${sender}`;
  
  const meta = document.createElement("div");
  meta.className = "msg-meta";
  meta.textContent = sender === "user" ? "Commander Object" : "Kattappa Core";
  
  const content = document.createElement("div");
  content.textContent = text;
  
  node.appendChild(meta);
  node.appendChild(content);
  return node;
}

// User View Components
function addTimelineEntry(description) {
  const container = $("user-timeline");
  
  // Clear placeholder if first entry
  if (container.children.length === 1 && container.children[0].querySelector(".timeline-time").textContent === "--:--") {
    container.replaceChildren();
  }
  
  const now = new Date();
  const timeStr = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;
  
  const entry = document.createElement("div");
  entry.className = "timeline-entry";
  
  const timeSpan = document.createElement("span");
  timeSpan.className = "timeline-time";
  timeSpan.textContent = timeStr;
  
  const descSpan = document.createElement("span");
  descSpan.className = "timeline-desc";
  descSpan.textContent = description;
  
  entry.appendChild(timeSpan);
  entry.appendChild(descSpan);
  
  // Prepend to show newest logs at the top
  container.insertBefore(entry, container.firstChild);
}

function updateTaskTree(steps = []) {
  const container = $("user-task-tree");
  container.replaceChildren();
  
  if (steps.length === 0) {
    const node = document.createElement("div");
    node.className = "task-tree-node";
    node.innerHTML = `
      <span class="task-node-status pending">○</span>
      <span class="task-node-desc">No active execution scheduled.</span>
    `;
    container.appendChild(node);
    return;
  }
  
  steps.forEach((step) => {
    const node = document.createElement("div");
    node.className = "task-tree-node";
    
    const statusSpan = document.createElement("span");
    statusSpan.className = `task-node-status ${step.status}`;
    
    let bullet = "○";
    if (step.status === "completed") bullet = "✓";
    else if (step.status === "active" || step.status === "in_progress") bullet = "•";
    
    statusSpan.textContent = bullet;
    
    const descSpan = document.createElement("span");
    descSpan.className = "task-node-desc";
    descSpan.textContent = step.title || step.description || "Subtask";
    
    node.appendChild(statusSpan);
    node.appendChild(descSpan);
    container.appendChild(node);
  });
}

function updateActivityGear(stageName, status = "active") {
  const container = $("chat-activity");
  // Clear default text if adding gears
  if (container.children.length === 1 && container.children[0].id === "gear-input") {
    container.replaceChildren();
  }
  
  let gear = document.getElementById(`gear-${stageName.replace(/\s+/g, "-")}`);
  if (!gear) {
    gear = document.createElement("div");
    gear.id = `gear-${stageName.replace(/\s+/g, "-")}`;
    container.appendChild(gear);
  }
  
  gear.className = `activity-gear ${status}`;
  gear.textContent = stageName;
}

function resetActivityGears() {
  const container = $("chat-activity");
  container.replaceChildren();
  const def = document.createElement("div");
  def.id = "gear-input";
  def.className = "activity-gear";
  def.textContent = "Awaiting next objective...";
  container.appendChild(def);
}

async function refreshStatus() {
  try {
    const data = await api("/api/status");
    
    // Left Telemetry Box
    $("quick-telemetry").textContent = [
      `Ollama  : ${data.ollama_ok ? "ONLINE" : "OFFLINE"}`,
      `Memory  : ${data.memory_count} nodes`,
      `Shell   : ${data.shell_enabled ? "ENABLED" : "SANDBOXED"}`
    ].join("\n");

    // Right Sidebar Cognitive Lights
    $("cog-planner").className = "telemetry-val " + (data.active_tasks_count > 0 ? "active" : "idle");
    $("cog-planner").textContent = data.active_tasks_count > 0 ? "ACTIVE" : "IDLE";

    $("cog-coder").className = "telemetry-val " + (data.models.coder ? "active" : "idle");
    $("cog-coder").textContent = data.models.coder ? "READY" : "IDLE";
    
    $("cog-researcher").className = "telemetry-val " + (data.ollama_ok ? "active" : "idle");
    $("cog-researcher").textContent = data.ollama_ok ? "READY" : "IDLE";

    // System bars
    $("cpu-bar").style.width = data.ollama_ok ? "12%" : "3%";
    $("sub-cpu").textContent = data.ollama_ok ? "12%" : "3%";

    // Models List in Settings
    $("models-list").replaceChildren();
    for (const [key, val] of Object.entries(data.models || {})) {
      const line = document.createElement("div");
      line.textContent = `${key.toUpperCase()}: ${val}`;
      $("models-list").appendChild(line);
    }
  } catch (err) {
    console.error("Status check failed", err);
  }
}

async function refreshTasks() {
  try {
    const data = await api("/api/tasks");
    const container = $("task-list");
    container.replaceChildren();
    
    data.tasks.forEach((task) => {
      const card = document.createElement("div");
      card.className = "card-panel";
      
      const title = document.createElement("div");
      title.style.fontWeight = "700";
      title.style.fontSize = "15px";
      title.textContent = `MISSION: ${task.goal}`;
      
      const statusLine = document.createElement("div");
      statusLine.style.fontFamily = "var(--font-mono)";
      statusLine.style.fontSize = "12px";
      statusLine.style.color = task.status === "completed" ? "var(--accent-teal)" : "var(--accent-orange)";
      statusLine.textContent = `STATUS: ${task.status.toUpperCase()}`;
      
      const stepsList = document.createElement("div");
      stepsList.style.marginTop = "8px";
      stepsList.style.fontSize = "13px";
      stepsList.style.lineHeight = "1.6";
      stepsList.textContent = task.steps.map((s) => `[${s.status === "completed" ? "✔" : "⟳"}] ${s.title}`).join("\n");
      
      card.appendChild(title);
      card.appendChild(statusLine);
      card.appendChild(stepsList);
      
      if (task.final_answer) {
        const ans = document.createElement("div");
        ans.style.marginTop = "10px";
        ans.style.padding = "10px";
        ans.style.background = "var(--bg-primary)";
        ans.style.border = "1px solid var(--border-color)";
        ans.style.borderRadius = "6px";
        ans.style.fontSize = "13.5px";
        ans.textContent = task.final_answer;
        card.appendChild(ans);
      }
      
      container.appendChild(card);
      
      // Update Task Tree for User mode if this is the active/newest task
      updateTaskTree(task.steps);
    });
  } catch (err) {
    console.error("Tasks refresh failed", err);
  }
}

// Nav link selectors
document.querySelectorAll(".nav-links button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".nav-links button, .view").forEach((node) => node.classList.remove("active"));
    button.classList.add("active");
    
    const viewName = button.dataset.view;
    $(viewName).classList.add("active");
    
    // Set headers
    $("view-title").textContent = button.textContent.toUpperCase() + " MODE";
    
    if (viewName === "missions") refreshTasks();
  });
});

// Chat Form submit
$("ask-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const prompt = $("prompt").value.trim();
  if (!prompt) return;
  
  $("messages").appendChild(createMessageNode(prompt, "user"));
  $("prompt").value = "";
  
  // Observability triggers
  addTimelineEntry(`Analyzing intent: "${prompt.slice(0, 30)}..."`);
  updateActivityGear("Deliberating intent", "active");
  updateActivityGear("Planner routing", "active");
  
  const waiting = createMessageNode("Deliberating decision in consensus council...", "assistant");
  $("messages").appendChild(waiting);
  
  try {
    const data = await api("/api/ask", {
      method: "POST",
      body: JSON.stringify({ prompt, mode: "planner" }),
    });
    
    updateActivityGear("Deliberating intent", "complete");
    updateActivityGear("Planner routing", "complete");
    updateActivityGear("Consensus verification", "complete");
    addTimelineEntry("Consensus verified, intent resolved successfully");
    
    waiting.replaceChildren();
    waiting.textContent = data.response || data.answer || "Execute completed.";
    
    const state = data.state || {};
    if (state.selected_agent) {
      $("consensus-indicator").textContent = `Consensus: ${state.selected_agent.toUpperCase()}`;
    }
  } catch (err) {
    waiting.textContent = `Security/execution error encountered: ${err.message}`;
    addTimelineEntry(`Execution error: ${err.message}`);
  }
  
  setTimeout(resetActivityGears, 4000);
  refreshStatus();
});

// Task Form submit
$("task-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const goal = $("goal").value.trim();
  if (!goal) return;
  
  addTimelineEntry(`Mission initialized: "${goal.slice(0, 30)}..."`);
  
  try {
    await api("/api/task", {
      method: "POST",
      body: JSON.stringify({ goal, execute_tools: $("execute-tools").checked }),
    });
    $("goal").value = "";
    await refreshTasks();
  } catch (err) {
    console.error("Mission initiation failed", err);
    addTimelineEntry(`Mission setup failed: ${err.message}`);
  }
});

// Memory Form submit
$("memory-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = $("memory-text").value.trim();
  if (!text) return;
  try {
    await api("/api/memory", { method: "POST", body: JSON.stringify({ text }) });
    $("memory-text").value = "";
    alert("Knowledge committed to memory vault.");
    addTimelineEntry("Knowledge committed to permanent Memory Vault");
    refreshStatus();
  } catch (err) {
    console.error("Memory store failed", err);
  }
});

// Memory Search submit
$("recall-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = encodeURIComponent($("memory-query").value.trim());
  try {
    const data = await api(`/api/memory/search?q=${query}`);
    const results = $("memory-results");
    results.replaceChildren();
    
    data.items.forEach((text) => {
      const bubble = document.createElement("div");
      bubble.className = "msg-bubble assistant";
      bubble.textContent = text;
      results.appendChild(bubble);
    });
    addTimelineEntry(`Queried Memory Vault for: "${query}"`);
  } catch (err) {
    console.error("Memory search failed", err);
  }
});

// WebSocket Connection Status
function connectWebSocket() {
  const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsHost = window.location.host;
  const socket = new WebSocket(`${wsProto}//${wsHost}/ws/events`);

  socket.onopen = () => {
    document.querySelector(".status-dot").style.background = "var(--accent-teal)";
    document.querySelector(".status-dot").style.boxShadow = "0 0 8px var(--accent-teal)";
    addTimelineEntry("WebSocket session connected successfully");
  };

  socket.onclose = () => {
    document.querySelector(".status-dot").style.background = "var(--accent-orange)";
    document.querySelector(".status-dot").style.boxShadow = "0 0 8px var(--accent-orange)";
    addTimelineEntry("WebSocket session disconnected, retrying...");
    setTimeout(connectWebSocket, 5000); // Auto reconnect
  };

  socket.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "WORKSPACE_UPDATED" || msg.type === "WORKSPACE_CREATED") {
        addTimelineEntry(`State updated: ${msg.type}`);
        refreshStatus();
        refreshTasks();
      }
    } catch (e) {
      console.error("Error parsing WS message", e);
    }
  };
}

// Initial status loads
refreshStatus();
connectWebSocket();
resetActivityGears();
