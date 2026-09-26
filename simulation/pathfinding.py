from collections import deque


def bfs(start, goal, warehouse):

    if not warehouse.is_static_free(
        goal[0],
        goal[1]
    ):
        return None

    queue = deque([start])

    parent = {
        start: None
    }

    while queue:

        current = queue.popleft()

        if current == goal:

            path = []

            while current is not None:
                path.append(current)
                current = parent[current]

            return path[::-1]

        x, y = current

        neighbors = [
            (x + 1, y),
            (x - 1, y),
            (x, y + 1),
            (x, y - 1)
        ]

        for next_position in neighbors:

            if next_position in parent:
                continue

            nx, ny = next_position

            if not warehouse.is_static_free(
                nx,
                ny
            ):
                continue

            parent[next_position] = current

            queue.append(next_position)

    return None