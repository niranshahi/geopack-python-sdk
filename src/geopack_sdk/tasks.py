import time

class TaskManager:
    def __init__(self, client):
        self.client = client

    def get_status(self, task_id):
        """
        Fetch the current status of a background task.
        """
        return self.client.get(f"/tasks/{task_id}")

    def wait_for_task(self, task_id, timeout=300, interval=2):
        """
        Poll the task status until it is completed or failed.
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            status_data = self.get_status(task_id)
            status = status_data.get("status")
            
            if status == "completed":
                return status_data
            if status in ["failed", "canceled"]:
                raise Exception(f"Task {task_id} failed or was canceled: {status_data.get('message')}")
            
            time.sleep(interval)
        
        raise TimeoutError(f"Task {task_id} timed out after {timeout} seconds")
