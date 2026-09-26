def detect_deadlocks(robots, proposals):
    """
    Find robots that are stuck in a genuine circular wait -- e.g. A wants
    B's cell, B wants A's cell (or a longer loop: A -> B -> C -> A).

    A robot that merely wants to move into a cell held by a robot that is
    itself part of such a cycle is NOT deadlocked: once the cycle members
    are excluded from this tick's moves, collision resolution will
    correctly block that robot too (its target cell stays occupied), but
    it isn't part of the cycle itself and shouldn't be reported as one.
    So only the actual cycle members are returned here.
    """

    position_to_robot = {
        robot.position: robot.robot_id
        for robot in robots
        if not robot.failed
    }

    graph = {}

    for robot in robots:

        if robot.failed:
            continue

        if robot.robot_id not in proposals:
            continue

        destination = proposals[
            robot.robot_id
        ]

        other_robot = position_to_robot.get(
            destination
        )

        if (
            other_robot is not None
            and other_robot != robot.robot_id
        ):

            graph[robot.robot_id] = other_robot

    deadlocked = set()

    # Nodes whose outcome (part of a cycle, or not) is already known,
    # so each node is only walked through once overall.
    resolved = set()

    for start in graph:

        if start in resolved:
            continue

        chain = []
        chain_index = {}
        current = start

        while (
            current in graph
            and current not in chain_index
            and current not in resolved
        ):

            chain_index[current] = len(chain)
            chain.append(current)

            current = graph[current]

        if current in chain_index:

            # Found a real cycle: only the part of the chain from the
            # first repeated node onward is the actual cycle.
            cycle_start = chain_index[current]

            deadlocked.update(
                chain[cycle_start:]
            )

        resolved.update(chain)

    return deadlocked