"""Tests for inspect_workflow_run_outcome helper."""

from unittest.mock import MagicMock

from geopack_sdk.models import TaskResult, WorkflowRun
from geopack_sdk.workflow_runs import inspect_workflow_run_outcome


def test_inspect_resolves_run_id_from_submit(capsys):
    client = MagicMock()
    client.tasks.get_status.return_value = TaskResult(
        taskId="task-1",
        taskType="workflow:run",
        status="completed",
        inputParameters={"workflowRunId": 55},
        results={"workflowRunId": 55},
    )
    client.workflow_runs.get.return_value = WorkflowRun(
        id=55,
        workflowId=1,
        status="succeeded",
        artifacts=[],
    )
    client.workflow_runs.get_logs.return_value = {
        "status": "succeeded",
        "nodeStatuses": {"node_a": "succeeded", "node_b": "failed"},
    }

    resolved = inspect_workflow_run_outcome(client, "task-1", run_id=55)
    out = capsys.readouterr().out

    assert resolved == 55
    assert "Task task-1" in out
    assert "WorkflowRun #55" in out
    assert "failed nodes" in out
    client.workflow_runs.get.assert_called_once_with(55)


def test_inspect_returns_none_without_run_id(capsys):
    client = MagicMock()
    client.tasks.get_status.return_value = TaskResult(
        taskId="task-2",
        taskType="workflow:run",
        status="completed",
    )

    resolved = inspect_workflow_run_outcome(client, "task-2")
    out = capsys.readouterr().out

    assert resolved is None
    assert "No workflowRunId" in out
    client.workflow_runs.get.assert_not_called()
