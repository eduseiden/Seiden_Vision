from __future__ import annotations

import logging
from typing import Any
import requests

LOGGER = logging.getLogger(__name__)

class WebhookPublisher:
    def __init__(self, enabled: bool, url: str, api_key: str = "", timeout: int = 10) -> None:
        self.enabled = bool(enabled and url.strip())
        self.url = url.strip()
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json", "User-Agent": "Seiden-Vision/0.4.0"})
        if api_key.strip():
            self.session.headers["Authorization"] = f"Bearer {api_key.strip()}"

    def publish(self, event: dict[str, Any]) -> bool:
        if not self.enabled:
            return True
        try:
            response = self.session.post(self.url, json=event, timeout=self.timeout)
            response.raise_for_status()
            return True
        except requests.RequestException as exc:
            LOGGER.warning("Falha ao publicar evento no webhook: %s", exc)
            return False
