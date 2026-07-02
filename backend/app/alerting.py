"""Alerting via webhook for anomalies and operational failures."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import get_settings

logger = logging.getLogger("app.alerting")


def send_alert(title: str, payload: dict[str, Any]) -> None:
    settings = get_settings()
    url = settings.alert_webhook_url.strip()
    if not url:
        logger.warning("alert_skipped title=%s (ALERT_WEBHOOK_URL unset)", title)
        return
    body = {"title": title, **payload}
    try:
        with httpx.Client(timeout=5.0) as client:
            client.post(url, json=body)
        logger.info("alert_sent title=%s", title)
    except Exception:
        logger.exception("alert_delivery_failed title=%s", title)
