"""Slack-Benachrichtigungen für fehlgeschlagene Airflow-Tasks."""

import os

import requests


def notify_slack_failure(context: dict) -> None:
    """Sende bei einem fehlgeschlagenen Airflow-Task eine Slack-Nachricht."""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")

    if not webhook_url:
        print("SLACK_WEBHOOK_URL ist nicht gesetzt. Keine Slack-Nachricht gesendet.")
        return

    task_instance = context["task_instance"]
    exception = context.get("exception")

    message = {
        "text": (
            "European Energy Pipeline fehlgeschlagen\n"
            f"DAG: {task_instance.dag_id}\n"
            f"Task: {task_instance.task_id}\n"
            f"Run: {context.get('run_id', 'unknown')}\n"
            f"Fehler: {exception}"
        )
    }

    response = requests.post(
        webhook_url,
        json=message,
        timeout=10,
    )
    response.raise_for_status()
