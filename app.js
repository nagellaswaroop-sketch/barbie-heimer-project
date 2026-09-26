(() => {
  "use strict";

  // Change this if the backend runs somewhere other than localhost:8000.
const API_BASE = window.HACKFUSION_API_BASE || "https://barbie-heimer-project.onrender.com";  const WS_URL = API_BASE.replace(/^http/, "ws") + "/ws";

  const canvas = document.getElementById("floorCanvas");
  const ctx = canvas.getContext("2d");

  const stepCountEl = document.getElementById("stepCount");
  const statGridEl = document.getElementById("statGrid");
  const feedListEl = document.getElementById("feedList");
  const connDot = document.getElementById("connDot");
  const connLabel = document.getElementById("connLabel");

  const COLORS = {
    I: "#4a5568", // idle
    P: "#3ddc97", // to pickup
    D: "#4fa8e0", // to drop
    C: "#f2b84b", // charging
    L: "#9b7ede", // comm loss
    F: "#e5484d", // failed
  };

  let warehouse = null;   // { width, height, obstacles, charging_stations }
  let cellSize = 10;
  let latestFrame = null;

  // ---------------- Canvas sizing ----------------

  function resizeCanvas() {
    const rect = canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    canvas.style.width = rect.width + "px";
    canvas.style.height = rect.height + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    if (warehouse) {
      cellSize = Math.max(
        2,
        Math.min(rect.width / warehouse.width, rect.height / warehouse.height)
      );
    }

    if (latestFrame) draw(latestFrame);
  }

  window.addEventListener("resize", resizeCanvas);

  // ---------------- Drawing ----------------

  function draw(frame) {
    const rect = canvas.parentElement.getBoundingClientRect();
    ctx.clearRect(0, 0, rect.width, rect.height);

    if (!warehouse) return;

    const offsetX = (rect.width - warehouse.width * cellSize) / 2;
    const offsetY = (rect.height - warehouse.height * cellSize) / 2;

    // Floor
    ctx.fillStyle = "#0d131b";
    ctx.fillRect(offsetX, offsetY, warehouse.width * cellSize, warehouse.height * cellSize);

    // Obstacles (shelving)
    ctx.fillStyle = "#1c2531";
    for (const [x, y] of warehouse.obstacles) {
      ctx.fillRect(offsetX + x * cellSize, offsetY + y * cellSize, cellSize, cellSize);
    }

    // Charging stations
    ctx.fillStyle = "#f2b84b";
    for (const [x, y] of warehouse.charging_stations) {
      const cx = offsetX + x * cellSize + cellSize / 2;
      const cy = offsetY + y * cellSize + cellSize / 2;
      ctx.beginPath();
      ctx.rect(cx - cellSize * 0.35, cy - cellSize * 0.35, cellSize * 0.7, cellSize * 0.7);
      ctx.globalAlpha = 0.35;
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.strokeStyle = "#f2b84b";
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // Task markers
    if (frame.tasks) {
      for (const [, px, py, dx, dy, status] of frame.tasks) {
        // pickup marker
        ctx.strokeStyle = status === "W" ? "#3ddc97" : "#2a3542";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(
          offsetX + px * cellSize + cellSize / 2,
          offsetY + py * cellSize + cellSize / 2,
          cellSize * 0.3, 0, Math.PI * 2
        );
        ctx.stroke();

        // drop marker
        ctx.strokeStyle = status === "P" ? "#4fa8e0" : "#2a3542";
        ctx.strokeRect(
          offsetX + dx * cellSize + cellSize * 0.2,
          offsetY + dy * cellSize + cellSize * 0.2,
          cellSize * 0.6, cellSize * 0.6
        );
      }
    }

    // Robots
    if (frame.robots) {
      const radius = Math.max(1, cellSize * 0.32);
      for (const [, x, y, status] of frame.robots) {
        ctx.fillStyle = COLORS[status] || COLORS.I;
        ctx.beginPath();
        ctx.arc(
          offsetX + x * cellSize + cellSize / 2,
          offsetY + y * cellSize + cellSize / 2,
          radius, 0, Math.PI * 2
        );
        ctx.fill();
      }
    }
  }

  // ---------------- Stats / feed ----------------

  const STAT_LABELS = [
    ["completed", "tasks completed"],
    ["waiting", "tasks waiting"],
    ["picked_up", "in transit"],
    ["failed_robots", "robots failed"],
    ["comm_loss_robots", "comm loss now"],
    ["total_deadlocks_resolved", "deadlocks resolved"],
    ["total_conflicts_blocked", "conflicts blocked"],
    ["total_recoveries", "self-recoveries"],
  ];

  function renderStats(stats) {
    statGridEl.innerHTML = STAT_LABELS.map(([key, label]) => `
      <div class="stat">
        <div class="value">${stats[key] ?? 0}</div>
        <div class="label">${label}</div>
      </div>
    `).join("");
  }

  function renderFeed(events) {
    if (!events || events.length === 0) return;
    feedListEl.innerHTML = events.map(e =>
      `<li>robot <span>#${e.robot_id}</span> won task <span>#${e.task_id}</span> (cost ${e.cost})</li>`
    ).join("");
  }

  // ---------------- WebSocket ----------------

  function setConnStatus(state) {
    connDot.className = "dot " + (state === "live" ? "live" : state === "down" ? "down" : "");
    connLabel.textContent = state === "live" ? "live" : state === "down" ? "disconnected" : "connecting";
  }

  function connect() {
    setConnStatus("connecting");
    const ws = new WebSocket(WS_URL);

    ws.onopen = () => setConnStatus("live");

    ws.onmessage = (event) => {
      const frame = JSON.parse(event.data);

      if (frame.type === "init") {
        warehouse = frame.warehouse;
        resizeCanvas();
      }

      latestFrame = frame;
      stepCountEl.textContent = frame.step;
      renderStats(frame.stats);
      renderFeed(frame.events);
      draw(frame);
    };

    ws.onclose = () => {
      setConnStatus("down");
      setTimeout(connect, 1500);
    };

    ws.onerror = () => ws.close();
  }

  // ---------------- Controls ----------------

  async function post(path, body) {
    const res = await fetch(API_BASE + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    return res.json();
  }

  document.getElementById("btnStart").addEventListener("click", () => post("/api/start"));
  document.getElementById("btnStop").addEventListener("click", () => post("/api/stop"));
  document.getElementById("btnStep").addEventListener("click", () => post("/api/step"));

  document.getElementById("btnFail").addEventListener("click", () => post("/api/inject/failure"));
  document.getElementById("btnComm").addEventListener("click", () => post("/api/inject/comm-loss"));

  document.getElementById("btnReset").addEventListener("click", async () => {
    const cfg = {
      robot_count: parseInt(document.getElementById("cfgRobots").value, 10),
      task_count: parseInt(document.getElementById("cfgTasks").value, 10),
      rows: parseInt(document.getElementById("cfgRows").value, 10),
      cols: parseInt(document.getElementById("cfgCols").value, 10),
      num_charging_stations: parseInt(document.getElementById("cfgStations").value, 10),
    };
    const frame = await post("/api/reset", cfg);
    warehouse = frame.warehouse;
    resizeCanvas();
    latestFrame = frame;
    stepCountEl.textContent = frame.step;
    renderStats(frame.stats);
    draw(frame);
  });

  // ---------------- Boot ----------------

  resizeCanvas();
  connect();
})();
