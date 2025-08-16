import logging
import os
from typing import Any, Dict, List

import requests

logger = logging.getLogger("whatsapp-service")

META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID", "")
GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v18.0")


def _api_headers() -> Dict[str, str]:
	return {
		"Authorization": f"Bearer {META_ACCESS_TOKEN}",
		"Content-Type": "application/json",
	}


def _should_dry_run() -> bool:
	if not META_ACCESS_TOKEN or not META_PHONE_NUMBER_ID:
		return True
	# Treat placeholder values as not configured
	if META_ACCESS_TOKEN.startswith("EAA...replace") or len(META_ACCESS_TOKEN) < 20:
		return True
	if not META_PHONE_NUMBER_ID.isdigit():
		return True
	return False


def send_text_message(to_wa_id: str, text: str) -> bool:
	if _should_dry_run():
		logger.info("[DRY RUN] send text to %s: %s", to_wa_id, text[:120])
		return True

	url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{META_PHONE_NUMBER_ID}/messages"
	payload: Dict[str, Any] = {
		"messaging_product": "whatsapp",
		"to": to_wa_id,
		"type": "text",
		"text": {"preview_url": False, "body": text[:4096]},
	}

	try:
		resp = requests.post(url, headers=_api_headers(), json=payload, timeout=10)
		if 200 <= resp.status_code < 300:
			logger.info("Sent message to %s", to_wa_id)
			return True
		logger.error("Failed to send message: status=%s body=%s", resp.status_code, _safe_body(resp.text))
		return False
	except Exception as exc:  # noqa: BLE001
		logger.exception("Error sending message: %s", exc)
		return False


def send_interactive_buttons(to_wa_id: str, body_text: str, buttons: List[Dict[str, str]]) -> bool:
	"""buttons: list of {id, title}, max 3"""
	if _should_dry_run():
		logger.info("[DRY RUN] send interactive to %s: %s | buttons=%s", to_wa_id, body_text[:120], [b.get("title") for b in buttons])
		return True
	if not buttons:
		return send_text_message(to_wa_id, body_text)

	url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{META_PHONE_NUMBER_ID}/messages"
	wa_buttons = [
		{"type": "reply", "reply": {"id": b["id"][:256], "title": b["title"][:20]}}
		for b in buttons[:3]
	]
	payload: Dict[str, Any] = {
		"messaging_product": "whatsapp",
		"to": to_wa_id,
		"type": "interactive",
		"interactive": {
			"type": "button",
			"body": {"text": body_text[:1024]},
			"action": {"buttons": wa_buttons},
		},
	}
	try:
		resp = requests.post(url, headers=_api_headers(), json=payload, timeout=10)
		if 200 <= resp.status_code < 300:
			logger.info("Sent interactive to %s", to_wa_id)
			return True
		logger.error("Failed to send interactive: status=%s body=%s", resp.status_code, _safe_body(resp.text))
		return False
	except Exception as exc:  # noqa: BLE001
		logger.exception("Error sending interactive: %s", exc)
		return False


def _safe_body(body: str) -> str:
	return body.replace(META_ACCESS_TOKEN, "***") if META_ACCESS_TOKEN else body
