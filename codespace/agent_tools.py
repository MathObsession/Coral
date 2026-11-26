"""Hermes plugin that calls Coral using only the active task's capability."""
import json
import os
from datetime import datetime
from uuid import UUID

import httpx


def call_coral(path, method="GET", body=None):
    url = os.getenv("CORAL_AGENT_URL", "")
    token = os.getenv("CORAL_AGENT_TOKEN", "")
    if not url or not token:
        return json.dumps({"error": "This tool requires an active Hermes task started by Coral."})
    try:
        response = httpx.request(method, url + "/agent" + path, json=body,
                                 headers={"Authorization": "Bearer " + token}, timeout=12, follow_redirects=False)
        result = response.json()
        if response.is_success:
            return json.dumps(result)
        detail = result.get("detail")
        return json.dumps({"error": detail if isinstance(detail, str) else "Coral refused the tool request."})
    except (httpx.HTTPError, ValueError):
        return json.dumps({"error": "Could not reach Coral. Check the workspace status and retry."})


def save_schedule(params, **_):
    try:
        run_at = datetime.fromisoformat(params["starts_at"])
        if run_at.tzinfo is None:
            raise ValueError
        schedule_id = str(UUID(params["schedule_id"])) if params.get("schedule_id") else ""
    except (ValueError, TypeError, KeyError, AttributeError):
        return json.dumps({"error": "Use an ISO 8601 start time with a time zone and a schedule ID from coral_list_schedules when editing."})
    body = {"title": params.get("title"), "prompt": params.get("prompt"), "next_run": run_at.timestamp(),
            "recurrence": params.get("recurrence", "once"), "interval_seconds": params.get("interval_seconds", 86400),
            "duration_limit": params.get("duration_limit", 900), "paused": params.get("paused", False)}
    if schedule_id:
        return call_coral("/schedules/" + schedule_id, "PUT", body)
    return call_coral("/schedules", "POST", body)


def pause_schedule(params, **_):
    try:
        schedule_id = str(UUID(params["schedule_id"]))
    except (ValueError, TypeError, KeyError, AttributeError):
        return json.dumps({"error": "Use a schedule ID returned by coral_list_schedules."})
    return call_coral("/schedules/" + schedule_id, "PATCH", {"paused": params.get("paused")})


def register(ctx):
    tools = [
        ("coral_workspace_status", "Check this workspace's Codespace state, daily allowance and server time.", {}, [],
         lambda *_args, **_kwargs: call_coral("/workspace")),
        ("coral_recent_tasks", "Read the status of recent tasks in this workspace, including scheduled runs.", {}, [],
         lambda *_args, **_kwargs: call_coral("/tasks")),
        ("coral_list_schedules", "List this workspace's Coral schedules and their IDs and next run times.", {}, [],
         lambda *_args, **_kwargs: call_coral("/schedules")),
        ("coral_save_schedule", "Create or replace a Coral schedule at the user's request. Coral runs it even while the Codespace and app are closed.",
         {"title": {"type": "string"}, "prompt": {"type": "string", "description": "The full task Hermes should run."},
          "starts_at": {"type": "string", "description": "ISO 8601 date and time with offset or Z."},
          "recurrence": {"type": "string", "enum": ["once", "daily", "weekly", "recurring"]},
          "interval_seconds": {"type": "integer", "minimum": 300, "description": "Interval for recurring schedules."},
          "duration_limit": {"type": "integer", "minimum": 10, "maximum": 7200, "description": "Maximum task duration in seconds."},
          "paused": {"type": "boolean"},
          "schedule_id": {"type": "string", "description": "Existing Coral schedule ID. Omit to create a schedule."}},
         ["title", "prompt", "starts_at"], save_schedule),
        ("coral_pause_schedule", "Pause or resume one schedule at the user's request.",
         {"schedule_id": {"type": "string"}, "paused": {"type": "boolean"}}, ["schedule_id", "paused"], pause_schedule),
    ]
    for name, description, properties, required, handler in tools:
        ctx.register_tool(name=name, toolset="coral-workspace", handler=handler,
                          check_fn=lambda: bool(os.getenv("CORAL_AGENT_TOKEN")),
                          schema={"name": name, "description": description,
                                  "parameters": {"type": "object", "properties": properties, "required": required}})
