import time

class TaskManager:
    def __init__(self, client):
        self.client = client

    def get_status(self, task_id):
        """
        Fetch the current status of a background task.

        REST API: `GET /api/tasks/{taskId}`
        """
        return self.client.get(f"/tasks/{task_id}")

    def create(self, task_payload):
        """
        Create a new background task.

        REST API: `POST /api/tasks`
        """
        return self.client.post("/tasks", json=task_payload)

    def wait(self, task_id, timeout=300, interval=2):
        """
        Alias for wait_for_task.
        """
        return self.wait_for_task(task_id, timeout=timeout, interval=interval)

    def wait_for_task(self, task_id, timeout=300, interval=2):
        """
        Poll the task status until it is completed or failed.

        REST API: `GET /api/tasks/{taskId}` (polled)

        Expected terminal statuses:
        - completed
        - failed
        - canceled
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            status_data = self.get_status(task_id)
            status = status_data.get("status")
            
            if status == "completed":
                # Final fetch to ensure we have the output field
                return self.get_status(task_id)
            if status in ["failed", "canceled"]:
                raise Exception(f"Task {task_id} failed or was canceled: {status_data.get('message')}")
            
            time.sleep(interval)
        
        raise TimeoutError(f"Task {task_id} timed out after {timeout} seconds")
