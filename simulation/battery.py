from pathfinding import bfs


def _closest_reachable_station(position, warehouse):
    """Find the charging station reachable from `position` with the
    shortest BFS path, or (None, None) if none are reachable.

    Shared by the "already charging" and "should I start charging"
    branches below so both use real, obstacle-aware reachability
    rather than raw Manhattan distance -- picking a station that's
    nearest as the crow flies but actually unreachable (or blocked
    along the way while another station isn't) used to leave a
    charging robot with an empty path and no way to recover.
    """

    best_path = None
    best_distance = None

    for station in warehouse.charging_stations:

        path = bfs(
            position,
            station,
            warehouse
        )

        if path is None:
            continue

        distance = len(path) - 1

        if (
            best_distance is None
            or distance < best_distance
        ):
            best_distance = distance
            best_path = path

    return best_path, best_distance


def handle_battery(
    robot,
    warehouse,
    safety_margin=10
):

    if robot.failed:
        return False

    if not warehouse.charging_stations:
        return False

    if robot.status == "CHARGING":

        # Already committed to charging: keep heading for the closest
        # REACHABLE station, replanning around obstacles/other robots
        # as needed.
        best_path, _ = _closest_reachable_station(
            robot.position,
            warehouse
        )

        robot.path = best_path[1:] if best_path else []

        return True

    carrying_pickup = (
        robot.current_task
        and robot.current_task.status
        == "PICKED_UP"
    )

    # Cheap lower-bound check first: the real obstacle-aware distance
    # can only be >= the straight-line Manhattan distance, so if even
    # that doesn't require charging yet, skip running BFS against every
    # station for this robot on this tick.
    nearest_manhattan = min(
        abs(station[0] - robot.x)
        + abs(station[1] - robot.y)
        for station in warehouse.charging_stations
    )

    if robot.battery > nearest_manhattan + safety_margin:
        return False

    # Getting close: find the real, obstacle-aware distance to the
    # closest reachable station.
    best_path, best_distance = _closest_reachable_station(
        robot.position,
        warehouse
    )

    if best_path is None:
        return False

    if robot.battery > best_distance + safety_margin:
        return False

    # From here the robot is genuinely close to running out of runway.
    # Normally that's enough on its own to head to charge -- but if it's
    # mid-delivery, only override that commitment as a real emergency
    # (this is a last resort: losing some time on a re-routed task beats
    # losing the robot, and the task, entirely).
    if carrying_pickup and robot.battery > best_distance:
        return False

    if robot.current_task:

        robot.current_task.release()

        robot.current_task = None

    robot.status = "CHARGING"

    robot.path = best_path[1:]

    return True


def recharge(robot, warehouse):

    # Only a robot that actually committed to charging should be reset
    # here. Without this check, any robot whose delivery route merely
    # passes through a charging-station cell (they sit at the four
    # corners, which ordinary pickup/drop paths can cross) would get
    # silently knocked back to IDLE with its path wiped -- while
    # current_task was still set. negotiate() only looks at
    # robot.status == "IDLE", so that robot could then be handed a
    # second task on the next tick, silently abandoning the first one
    # (its task would sit at WAITING/PICKED_UP forever with a dead
    # assigned_robot reference, since nothing else releases it).
    if robot.status != "CHARGING":
        return False

    if robot.position in warehouse.charging_stations:

        robot.battery = 100

        robot.status = "IDLE"

        robot.path = []

        return True

    return False