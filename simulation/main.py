import random

from robot import Robot
from task import Task
from warehouse import Warehouse

from pathfinding import bfs
from negotiation import negotiate

from collision import resolve_moves
from deadlock import detect_deadlocks

from battery import (
    handle_battery,
    recharge
)

from config import (
    ROWS,
    COLS,
    ROBOT_COUNT,
    TASK_COUNT,
    SIMULATION_STEPS,
    RANDOM_SEED
)


# ----------------------------------------
# Warehouse
# ----------------------------------------

def build_warehouse(
    rows=ROWS,
    cols=COLS,
    station_count=4
):

    grid = [
        ["." for _ in range(cols)]
        for _ in range(rows)
    ]

    obstacle_columns = sorted({
        max(2, min(cols - 3, round(cols * fraction)))
        for fraction in (0.2, 0.4, 0.6, 0.8)
    })

    for y in range(3, rows - 3):
        for x in obstacle_columns:
            if y % 6 != 0:
                grid[y][x] = "#"

    charging_stations = [
        (1, 1),
        (cols - 2, rows - 2),
        (cols - 2, 1),
        (1, rows - 2)
    ]
    charging_stations = [
        position
        for position in charging_stations
        if grid[position[1]][position[0]] == "."
    ][:station_count]

    free_cells = [
        (x, y)
        for y in range(rows)
        for x in range(cols)
        if grid[y][x] == "."
    ]

    while len(charging_stations) < station_count and free_cells:
        candidates = [
            position
            for position in free_cells
            if position not in charging_stations
        ]
        if not candidates:
            break
        station = max(
            candidates,
            key=lambda position: min(
                abs(position[0] - existing[0])
                + abs(position[1] - existing[1])
                for existing in charging_stations
            ) if charging_stations else 0
        )
        charging_stations.append(station)

    return Warehouse(
        grid,
        charging_stations
    )


# ----------------------------------------
# Find random free cell
# ----------------------------------------

def random_free_cell(
    warehouse,
    occupied=None
):

    occupied = set(occupied or [])

    attempts = 0

    while attempts < 10000:

        x = random.randrange(
            warehouse.width
        )

        y = random.randrange(
            warehouse.height
        )

        position = (x, y)

        if (
            position not in occupied
            and warehouse.is_static_free(x, y)
        ):
            return position

        attempts += 1

    raise RuntimeError(
        "Could not find a free cell."
    )


# ----------------------------------------
# Create robots
# ----------------------------------------

def create_robots(
    warehouse,
    count
):

    robots = []

    occupied = set(
        warehouse.charging_stations
    )

    for robot_id in range(
        1,
        count + 1
    ):

        position = random_free_cell(
            warehouse,
            occupied
        )

        occupied.add(position)

        robot = Robot(
            robot_id,
            position[0],
            position[1],
            battery=random.randint(
                70,
                100
            )
        )

        robots.append(robot)

        warehouse.add_robot(robot)

    return robots


# ----------------------------------------
# Create tasks
# ----------------------------------------

def create_tasks(
    warehouse,
    robots,
    count
):

    tasks = []

    occupied = {
        robot.position
        for robot in robots
    }

    for task_id in range(
        1,
        count + 1
    ):

        pickup = random_free_cell(
            warehouse,
            occupied
        )

        occupied.add(pickup)

        drop = random_free_cell(
            warehouse,
            occupied
        )

        occupied.add(drop)

        task = Task(
            task_id,
            pickup,
            drop,
            priority=random.randint(
                1,
                5
            )
        )

        tasks.append(task)

    return tasks


# ----------------------------------------
# Plan paths
# ----------------------------------------

def plan_paths(
    robots,
    warehouse
):

    for robot in robots:

        if robot.failed:
            continue

        task = robot.current_task

        if task is None:
            continue

        if task.status == "WAITING":

            target = task.pickup

        elif task.status == "PICKED_UP":

            target = task.drop

        else:

            continue

        path = bfs(
            robot.position,
            target,
            warehouse
        )

        if path:

            robot.path = path[1:]

        else:

            robot.path = []


# ----------------------------------------
# Deadlock recovery
# ----------------------------------------

STUCK_THRESHOLD = 5


def _current_goal(robot, warehouse):

    if robot.current_task:

        if robot.current_task.status == "WAITING":
            return robot.current_task.pickup

        if robot.current_task.status == "PICKED_UP":
            return robot.current_task.drop

    if robot.status == "CHARGING" and warehouse.charging_stations:

        return min(
            warehouse.charging_stations,
            key=lambda position:
                abs(position[0] - robot.x)
                + abs(position[1] - robot.y)
        )

    return None


def recover_from_deadlock(
    robots,
    warehouse,
    accepted
):

    recovered = 0

    occupied_positions = {
        robot.position
        for robot in robots
        if not robot.failed
    }

    claimed_destinations = set(
        accepted.values()
    )

    for robot in robots:

        if robot.failed:
            continue

        if robot.status == "CHARGING":
            continue

        if robot.stuck_ticks < STUCK_THRESHOLD:
            continue

        if robot.robot_id in accepted:
            continue

        neighbors = [
            (robot.x + 1, robot.y),
            (robot.x - 1, robot.y),
            (robot.x, robot.y + 1),
            (robot.x, robot.y - 1)
        ]

        random.shuffle(neighbors)

        goal = _current_goal(
            robot,
            warehouse
        )

        valid_neighbors = []

        for candidate in neighbors:

            if not warehouse.is_static_free(
                candidate[0],
                candidate[1]
            ):
                continue

            if candidate in occupied_positions:
                continue

            if candidate in claimed_destinations:
                continue

            # Count robots around this candidate.
            nearby_robots = 0

            for other in robots:

                if other.failed:
                    continue

                distance = (
                    abs(other.x - candidate[0])
                    + abs(other.y - candidate[1])
                )

                if distance <= 1:
                    nearby_robots += 1

            if goal is not None:

                goal_distance = (
                    abs(candidate[0] - goal[0])
                    + abs(candidate[1] - goal[1])
                )

            else:

                goal_distance = 0

            valid_neighbors.append(
                (
                    nearby_robots,
                    goal_distance,
                    candidate
                )
            )

        if not valid_neighbors:
            continue

        # First escape crowded areas.
        # If equally crowded, prefer the one closer to the goal.
        valid_neighbors.sort(
            key=lambda item: (
                item[0],
                item[1]
            )
        )

        candidate = valid_neighbors[0][2]

        accepted[robot.robot_id] = candidate

        claimed_destinations.add(candidate)

        recovered += 1

        robot.stuck_ticks = 0

        robot.path = []

    return recovered


# ----------------------------------------
# Execute one simulation step
# ----------------------------------------

def step_simulation(
    robots,
    tasks,
    warehouse,
    verbose=True
):

    # 1. Negotiate tasks
    assignments = negotiate(
        tasks,
        robots,
        warehouse
    )

    # 2. Battery handling
    for robot in robots:

        handle_battery(
            robot,
            warehouse
        )

    # 3. Plan paths
    plan_paths(
        robots,
        warehouse
    )

    # 4. Movement proposals
    proposals = {}

    for robot in robots:

        if robot.failed:
            continue

        if robot.status == "CHARGING":

            # Charging robots have no current_task, but they still have
            # a real path (set in handle_battery) that they need to
            # actually walk in order to reach a station.
            if robot.path:

                proposals[
                    robot.robot_id
                ] = robot.path[0]

            continue

        if robot.current_task is None:
            continue

        if not robot.path:
            continue

        proposals[
            robot.robot_id
        ] = robot.path[0]

    attempted = set(proposals)

    # 5. Detect deadlocks
    deadlocked = detect_deadlocks(
        robots,
        proposals
    )

    # Don't permanently block them.
    # Just remove their current proposal.
    for robot_id in deadlocked:

        proposals.pop(
            robot_id,
            None
        )

    # 6. Collision resolution
    accepted = resolve_moves(
    robots,
    proposals
)

    conflicts_blocked = len(attempted) - len(accepted)

    if verbose:
        print(
        f"  movement: proposed={len(proposals)}, "
        f"accepted={len(accepted)}, "
        f"deadlocked={len(deadlocked)}"
        )

    # 6b. Track how long each robot has gone without a move accepted,
    # and break real standoffs (e.g. two robots facing off in a
    # single-width corridor) that BFS alone can never resolve, since it
    # always recomputes the same shortest path for a robot that hasn't
    # moved. A robot stuck past the threshold takes any free adjacent
    # cell instead of waiting forever, and replans its real path next
    # tick.
    for robot in robots:

        if robot.failed:
            continue

        if robot.robot_id in accepted:

            robot.stuck_ticks = 0

        elif robot.robot_id in attempted:

            robot.stuck_ticks += 1

    recoveries = recover_from_deadlock(
        robots,
        warehouse,
        accepted
    )

    # 7. Move robots
    for robot in robots:

        if robot.robot_id not in accepted:
            continue

        destination = accepted[
            robot.robot_id
        ]

        robot.move_to(
            destination
        )

        if robot.path:
            robot.path.pop(0)

    # 8. Task state updates
    for robot in robots:

        task = robot.current_task

        if task is None:
            continue

        if (
            task.status == "WAITING"
            and robot.position == task.pickup
        ):

            task.pickup_task()

            robot.status = "TO_DROP"

            robot.path = []

        elif (
            task.status == "PICKED_UP"
            and robot.position == task.drop
        ):

            task.deliver()

            robot.release_task()

    # 9. Recharge
    for robot in robots:

        if robot.failed:
            continue

        recharge(
            robot,
            warehouse
        )

        if robot.battery <= 0:
            robot.fail()

    return {
        "assignments": assignments,
        "deadlocks": len(deadlocked),
        "conflicts_blocked": conflicts_blocked,
        "recoveries": recoveries,
    }


# ----------------------------------------
# Main
# ----------------------------------------

def main():

    random.seed(
        RANDOM_SEED
    )

    warehouse = build_warehouse()

    robots = create_robots(
        warehouse,
        ROBOT_COUNT
    )

    tasks = create_tasks(
        warehouse,
        robots,
        TASK_COUNT
    )

    print(
        f"Starting simulation with "
        f"{len(robots)} robots and "
        f"{len(tasks)} tasks."
    )

    for step in range(
        1,
        SIMULATION_STEPS + 1
    ):

        step_simulation(
            robots,
            tasks,
            warehouse
        )

        completed = sum(
            task.status == "COMPLETED"
            for task in tasks
        )

        waiting = sum(
            task.status == "WAITING"
            for task in tasks
        )

        failed = sum(
            robot.failed
            for robot in robots
        )

        if (
            step == 1
            or step % 20 == 0
        ):

            print(
                f"Step {step:3d} | "
                f"completed={completed:3d} | "
                f"waiting={waiting:3d} | "
                f"failed={failed:3d}"
            )

    print("\nFINAL SUMMARY")

    print(
        f"Robots: {len(robots)}"
    )

    print(
        f"Tasks: {len(tasks)}"
    )

    print(
        "Completed:",
        sum(
            task.status == "COMPLETED"
            for task in tasks
        )
    )

    print(
        "Waiting:",
        sum(
            task.status == "WAITING"
            for task in tasks
        )
    )

    print(
        "Failed robots:",
        sum(
            robot.failed
            for robot in robots
        )
    )


if __name__ == "__main__":
    main()