from pathfinding import bfs


def bid(robot, task, warehouse, drop_distance):

    # Robot → pickup
    pickup_path = bfs(
        robot.position,
        task.pickup,
        warehouse
    )

    if pickup_path is None:
        return None

    pickup_distance = len(pickup_path) - 1

    total_distance = pickup_distance + drop_distance

    # Keep enough battery to complete the entire task
    if total_distance + 10 >= robot.battery:
        return None

    battery_penalty = max(
        0,
        30 - robot.battery
    )

    cost = (
        total_distance
        + battery_penalty
        - task.priority
    )

    return cost


def negotiate(tasks, robots, warehouse):

    assignments = []

    for task in tasks:

        if task.status != "WAITING":
            continue

        # Pickup → drop distance doesn't depend on which robot bids on
        # the task, so compute it once per task instead of redundantly
        # re-running BFS for it inside bid() for every idle robot
        # (was O(idle_robots) identical BFS calls per task).
        drop_path = bfs(
            task.pickup,
            task.drop,
            warehouse
        )

        if drop_path is None:
            continue

        drop_distance = len(drop_path) - 1

        candidates = []

        for robot in robots:

            if robot.failed:
                continue

            if robot.status != "IDLE":
                continue

            # Defense in depth: a robot should never carry a task while
            # marked IDLE, but if some other bug ever produces that
            # inconsistent state, don't let it get handed a second task
            # and silently orphan the first.
            if robot.current_task is not None:
                continue

            score = bid(
                robot,
                task,
                warehouse,
                drop_distance
            )

            if score is not None:

                candidates.append(
                    (
                        score,
                        robot.robot_id,
                        robot
                    )
                )

        if candidates:

            winner = min(
                candidates,
                key=lambda item: (
                    item[0],
                    item[1]
                )
            )

            robot = winner[2]

            robot.assign_task(task)

            assignments.append({
                "robot_id": robot.robot_id,
                "task_id": task.task_id,
                "cost": winner[0],
            })

    return assignments