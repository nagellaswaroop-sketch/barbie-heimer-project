import asyncio
import random

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import RANDOM_SEED
from main import build_warehouse, create_robots, create_tasks, step_simulation


class ResetRequest(BaseModel):
    robot_count: int = Field(default=200, ge=10, le=2000)
    task_count: int = Field(default=100, ge=10, le=1000)
    rows: int = Field(default=30, ge=10, le=120)
    cols: int = Field(default=40, ge=10, le=160)
    num_charging_stations: int = Field(default=6, ge=2, le=40)


def _new_simulation(settings=None):
    settings = settings or ResetRequest()
    random.seed(RANDOM_SEED)

    warehouse = build_warehouse(
        rows=settings.rows,
        cols=settings.cols,
        station_count=settings.num_charging_stations,
    )
    free_cells = sum(cell == "." for row in warehouse.grid for cell in row)
    required_cells = (
        settings.num_charging_stations
        + settings.robot_count
        + 2 * settings.task_count
    )
    if free_cells < required_cells:
        raise ValueError(
            f"This warehouse has {free_cells} free cells, but the selected "
            f"configuration needs {required_cells}. Increase the grid size "
            "or reduce robots/tasks/stations."
        )

    robots = create_robots(warehouse, settings.robot_count)
    tasks = create_tasks(warehouse, robots, settings.task_count)
    return {
        "warehouse": warehouse,
        "robots": robots,
        "tasks": tasks,
        "step": 0,
        "running": False,
        "comm_loss_until": {},
        "events": [],
        "totals": {
            "deadlocks_resolved": 0,
            "conflicts_blocked": 0,
            "recoveries": 0,
        },
    }


simulation = _new_simulation()
state_lock = asyncio.Lock()
clients = set()
runner_task = None

app = FastAPI(title="Warehouse Simulation API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _frame(frame_type="update"):
    warehouse = simulation["warehouse"]
    step = simulation["step"]
    comm_loss_until = simulation["comm_loss_until"]

    status_codes = {
        "IDLE": "I",
        "TO_PICKUP": "P",
        "TO_DROP": "D",
        "CHARGING": "C",
        "FAILED": "F",
    }
    robots = []
    for robot in simulation["robots"]:
        if robot.failed:
            status = "F"
        elif comm_loss_until.get(robot.robot_id, 0) > step:
            status = "L"
        else:
            status = status_codes.get(robot.status, "I")
        robots.append([robot.robot_id, robot.x, robot.y, status])

    task_status_codes = {
        "WAITING": "W",
        "PICKED_UP": "P",
        "COMPLETED": "C",
    }
    tasks = [
        [
            task.task_id,
            task.pickup[0],
            task.pickup[1],
            task.drop[0],
            task.drop[1],
            task_status_codes[task.status],
        ]
        for task in simulation["tasks"]
    ]

    stats = {
        "completed": sum(task.status == "COMPLETED" for task in simulation["tasks"]),
        "waiting": sum(task.status == "WAITING" for task in simulation["tasks"]),
        "picked_up": sum(task.status == "PICKED_UP" for task in simulation["tasks"]),
        "failed_robots": sum(robot.failed for robot in simulation["robots"]),
        "comm_loss_robots": sum(
            until > step for until in comm_loss_until.values()
        ),
        "total_deadlocks_resolved": simulation["totals"]["deadlocks_resolved"],
        "total_conflicts_blocked": simulation["totals"]["conflicts_blocked"],
        "total_recoveries": simulation["totals"]["recoveries"],
    }

    frame = {
        "type": frame_type,
        "step": step,
        "robots": robots,
        "tasks": tasks,
        "stats": stats,
        "events": simulation["events"],
    }
    if frame_type == "init":
        frame["warehouse"] = {
            "width": warehouse.width,
            "height": warehouse.height,
            "obstacles": [
                [x, y]
                for y, row in enumerate(warehouse.grid)
                for x, cell in enumerate(row)
                if cell == "#"
            ],
            "charging_stations": [list(position) for position in warehouse.charging_stations],
        }
    return frame


async def _broadcast(frame):
    disconnected = []
    for client in clients.copy():
        try:
            await client.send_json(frame)
        except WebSocketDisconnect:
            disconnected.append(client)
        except RuntimeError:
            disconnected.append(client)
    for client in disconnected:
        clients.discard(client)


async def _advance():
    async with state_lock:
        result = await asyncio.to_thread(
            step_simulation,
            simulation["robots"],
            simulation["tasks"],
            simulation["warehouse"],
            verbose=False,
        )
        simulation["step"] += 1
        simulation["events"] = result["assignments"]
        simulation["totals"]["deadlocks_resolved"] += result["recoveries"]
        simulation["totals"]["conflicts_blocked"] += result["conflicts_blocked"]
        simulation["totals"]["recoveries"] += result["recoveries"]
        simulation["comm_loss_until"] = {
            robot_id: until
            for robot_id, until in simulation["comm_loss_until"].items()
            if until > simulation["step"]
        }
        return _frame()


async def _run_simulation():
    while simulation["running"]:
        await asyncio.sleep(0.15)
        if not simulation["running"]:
            break
        await _broadcast(await _advance())


@app.get("/health")
async def health():
    return {"ok": True, "step": simulation["step"]}


@app.post("/api/start")
async def start_simulation():
    global runner_task
    simulation["running"] = True
    if runner_task is None or runner_task.done():
        runner_task = asyncio.create_task(_run_simulation())
    return {"running": True}


@app.post("/api/stop")
async def stop_simulation():
    simulation["running"] = False
    return {"running": False}


@app.post("/api/step")
async def step_once():
    frame = await _advance()
    await _broadcast(frame)
    return frame


@app.post("/api/reset")
async def reset_simulation(settings: ResetRequest):
    global simulation
    try:
        updated_simulation = _new_simulation(settings)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    async with state_lock:
        simulation["running"] = False
        simulation = updated_simulation
        frame = _frame("init")
    await _broadcast(frame)
    return frame


@app.post("/api/inject/failure")
async def inject_failure():
    alive = [robot for robot in simulation["robots"] if not robot.failed]
    if not alive:
        raise HTTPException(status_code=409, detail="All robots have failed.")
    random.choice(alive).fail()
    frame = _frame()
    await _broadcast(frame)
    return frame


@app.post("/api/inject/comm-loss")
async def inject_comm_loss():
    available = [
        robot
        for robot in simulation["robots"]
        if not robot.failed
        and simulation["comm_loss_until"].get(robot.robot_id, 0) <= simulation["step"]
    ]
    if not available:
        raise HTTPException(status_code=409, detail="No available robot for comm loss.")
    robot = random.choice(available)
    simulation["comm_loss_until"][robot.robot_id] = simulation["step"] + 30
    frame = _frame()
    await _broadcast(frame)
    return frame


@app.websocket("/ws")
async def simulation_updates(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    await websocket.send_json(_frame("init"))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        clients.discard(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)