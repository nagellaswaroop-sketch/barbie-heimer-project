class Robot:
    def __init__(self, robot_id, x, y, battery=100):
        self.robot_id = robot_id
        self.x = x
        self.y = y
        self.battery = battery

        self.status = "IDLE"
        self.current_task = None
        self.path = []
        self.failed = False
        self.stuck_ticks = 0
        self.previous_position = None

    @property
    def position(self):
        return (self.x, self.y)

    def assign_task(self, task):
        self.current_task = task
        self.status = "TO_PICKUP"
        task.assigned_robot = self.robot_id

    def move_to(self, position):
        self.x, self.y = position
        self.battery = max(0, self.battery - 1)

    def release_task(self):
        if self.current_task:
            self.current_task.assigned_robot = None

        self.current_task = None
        self.path = []

        if not self.failed:
            self.status = "IDLE"

    def fail(self):
        self.failed = True
        self.status = "FAILED"
        self.path = []

        if self.current_task:
            self.current_task.release()
            self.current_task = None

    def __repr__(self):
        return (
            f"Robot({self.robot_id}, "
            f"pos={self.position}, "
            f"battery={self.battery}, "
            f"status={self.status})"
        )