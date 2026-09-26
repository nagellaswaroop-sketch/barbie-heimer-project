class Task:
    def __init__(self, task_id, pickup, drop, priority=1):
        self.task_id = task_id
        self.pickup = pickup
        self.drop = drop
        self.priority = priority

        self.status = "WAITING"
        self.assigned_robot = None

    def pickup_task(self):
        if self.status == "WAITING":
            self.status = "PICKED_UP"

    def deliver(self):
        if self.status == "PICKED_UP":
            self.status = "COMPLETED"
            self.assigned_robot = None

    def release(self):
        if self.status != "COMPLETED":
            self.status = "WAITING"
            self.assigned_robot = None