class Warehouse:
    def __init__(self, grid, charging_stations=None):
        self.grid = grid
        self.height = len(grid)
        self.width = len(grid[0])

        self.charging_stations = charging_stations or []
        self.robots = {}

    def is_inside(self, x, y):
        return (
            0 <= x < self.width
            and 0 <= y < self.height
        )

    # Checks only permanent warehouse obstacles.
    # Robots are NOT considered here.
    def is_static_free(self, x, y):

        if not self.is_inside(x, y):
            return False

        return self.grid[y][x] == "."

    # Checks whether a cell is currently free of robots.
    def is_free(self, x, y, ignore_robot=None):

        if not self.is_static_free(x, y):
            return False

        for robot in self.robots.values():

            if robot is ignore_robot:
                continue

            if robot.failed:
                continue

            if robot.position == (x, y):
                return False

        return True

    def add_robot(self, robot):
        self.robots[robot.robot_id] = robot

    def show(self):

        robot_positions = {}

        for robot in self.robots.values():

            if not robot.failed:
                robot_positions[
                    robot.position
                ] = "R"

        for y in range(self.height):

            row = []

            for x in range(self.width):

                if (x, y) in robot_positions:
                    row.append("R")
                else:
                    row.append(self.grid[y][x])

            print(" ".join(row))