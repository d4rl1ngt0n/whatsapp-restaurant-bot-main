import os
import json
import hmac
import hashlib
import logging
from typing import Any, Dict, List, Tuple

import requests

logger = logging.getLogger("paystack-service")

PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "")
PAYSTACK_PUBLIC_KEY = os.getenv("PAYSTACK_PUBLIC_KEY", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "")
DEFAULT_CURRENCY = (os.getenv("PAYSTACK_CURRENCY") or os.getenv("CURRENCY") or "ngn").lower()

API_BASE = "https://api.paystack.co"


def _configured() -> bool:
	if not PAYSTACK_SECRET_KEY:
		return False
	if len(PAYSTACK_SECRET_KEY) < 20:
		return False
	return True


def create_checkout_session(order_number: str, line_items: List[Tuple[str, int, int]], customer_email: str | None = None, currency_code: str | None = None) -> Tuple[bool, str, str]:
	"""Create a Paystack transaction and return authorization_url.
	line_items: list of (name, unit_amount_minor, quantity)
	Returns (ok, url, reference)
	"""
	if not _configured():
		logger.warning("Paystack not configured; skipping checkout session creation")
		return False, "", ""
	try:
		amount_minor = 0
		for name, unit_minor, qty in line_items:
			amount_minor += int(unit_minor) * int(qty)
		headers = {
			"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
			"Content-Type": "application/json",
		}
		metadata = {"order_number": order_number}
		currency = (currency_code or DEFAULT_CURRENCY).upper()
		logger.info("Initializing Paystack: currency=%s amount_minor=%s order=%s", currency, amount_minor, order_number)
		payload: Dict[str, Any] = {
			"amount": amount_minor,
			"email": customer_email or "customer@example.com",
			"reference": order_number,
			"currency": currency,
			"metadata": metadata,
			"callback_url": (PUBLIC_BASE_URL or "https://example.com") + "/payments/paystack/callback",
		}
		resp = requests.post(f"{API_BASE}/transaction/initialize", headers=headers, json=payload, timeout=15)
		if 200 <= resp.status_code < 300:
			data = resp.json().get("data") or {}
			return True, str(data.get("authorization_url", "")), str(data.get("reference", order_number))
		logger.warning("Paystack initialize failed: %s %s", resp.status_code, resp.text[:300])
		return False, "", ""
	except Exception as exc:  # noqa: BLE001
		logger.warning("Paystack session creation failed: %s", str(exc))
		return False, "", ""


def verify_transaction(reference: str) -> tuple[bool, Dict[str, Any]]:
	"""Verify a Paystack transaction by reference. Returns (paid, response_json)."""
	if not _configured():
		return False, {"error": "not_configured"}
	try:
		headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
		resp = requests.get(f"{API_BASE}/transaction/verify/{reference}", headers=headers, timeout=15)
		data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
		status = ((data.get("data") or {}).get("status") or "").lower()
		paid = status == "success"
		return paid, data
	except Exception as exc:  # noqa: BLE001
		return False, {"error": str(exc)}


def parse_webhook(raw_body: bytes, signature: str | None) -> Dict[str, Any] | None:
	"""Verify Paystack webhook using x-paystack-signature (HMAC SHA512)."""
	if not _configured() or not signature:
		return None
	try:
		computed = hmac.new(PAYSTACK_SECRET_KEY.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()
		if computed != signature:
			return None
		return json.loads(raw_body.decode("utf-8"))
	except Exception:  # noqa: BLE001
		return None
