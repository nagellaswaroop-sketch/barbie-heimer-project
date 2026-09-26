def resolve_moves(robots, proposals):
    """
    Resolve one tick of movement proposals into a set of accepted moves.

    A move is only safe to accept if the cell it targets will actually be
    free once everyone who is moving this tick has moved. That means:
      - moving onto a currently-empty cell is always fine
      - moving onto a cell held by a robot that is ALSO moving away this
        tick is fine, once that robot's own move has been accepted
      - moving onto a cell held by a robot that is staying put (whether
        it's simply not proposing a move, or it's stuck in a cycle with
        someone else) is never accepted

    This is resolved with a fixed-point pass: repeatedly accept any
    proposal whose destination is free or already vacated by an accepted
    move, until nothing changes. Anything left over is either blocked by
    a stationary robot or is part of a cyclic deadlock (e.g. two robots
    trying to swap places) -- both cases are correctly left unresolved.
    """

    positions = {
        robot.robot_id: robot.position
        for robot in robots
        if not robot.failed
    }

    occupied = {
        position: robot_id
        for robot_id, position in positions.items()
    }

    # Only one robot may win a destination that multiple robots want.
    by_destination = {}

    for robot_id, destination in proposals.items():

        by_destination.setdefault(
            destination,
            []
        ).append(robot_id)

    pending = {}

    for destination, robot_ids in by_destination.items():

        winner = min(robot_ids)

        pending[winner] = destination

    accepted = {}

    changed = True

    while changed:

        changed = False

        for robot_id, destination in list(pending.items()):

            occupant = occupied.get(destination)

            # Destination is empty, or the robot is "moving" onto its own
            # current cell (shouldn't normally happen, but stay safe).
            if occupant is None or occupant == robot_id:

                accepted[robot_id] = destination
                del pending[robot_id]
                changed = True
                continue

            # Destination's current occupant has already been confirmed
            # to be moving away this tick, so it's now safe to follow.
            if occupant in accepted:

                accepted[robot_id] = destination
                del pending[robot_id]
                changed = True
                continue

            # Otherwise the occupant isn't (yet, or ever) vacating the
            # cell this tick -- stay blocked.

    return accepted