import os
import logging
from typing import Any, Dict, List, Tuple

import stripe

logger = logging.getLogger("payments-service")

STRIPE_API_KEY = os.getenv("STRIPE_API_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "")
DEFAULT_CURRENCY = os.getenv("CURRENCY", "usd")

if STRIPE_API_KEY:
	stripe.api_key = STRIPE_API_KEY


def _stripe_configured() -> bool:
	if not STRIPE_API_KEY:
		return False
	# Treat obvious placeholders/short keys as not configured
	if STRIPE_API_KEY.endswith("...") or len(STRIPE_API_KEY) < 20:
		return False
	return True


def create_checkout_session(order_number: str, line_items: List[Tuple[str, int, int]]) -> Tuple[bool, str, str]:
	"""Create a Stripe Checkout Session.
	line_items: list of tuples (name, unit_amount_cents, quantity)
	Returns (ok, url, session_id)
	"""
	if not _stripe_configured():
		logger.warning("Stripe not configured or using placeholder key; skipping checkout session creation")
		return False, "", ""
	try:
		items = [
			{
				"price_data": {
					"currency": DEFAULT_CURRENCY,
					"product_data": {"name": name[:120]},
					"unit_amount": amount_cents,
				},
				"quantity": max(1, qty),
			}
			for (name, amount_cents, qty) in line_items
		]
		success_url = (PUBLIC_BASE_URL or "https://example.com") + "/payments/success"
		cancel_url = (PUBLIC_BASE_URL or "https://example.com") + "/payments/cancel"
		session = stripe.checkout.Session.create(
			mode="payment",
			line_items=items,
			success_url=success_url,
			cancel_url=cancel_url,
			metadata={"order_number": order_number},
		)
		return True, session.url, session.id
	except Exception as exc:  # noqa: BLE001
		logger.warning("Stripe session creation failed: %s", str(exc))
		return False, "", ""


def parse_webhook(payload: bytes, sig_header: str | None) -> Dict[str, Any] | None:
	if STRIPE_WEBHOOK_SECRET and sig_header:
		try:
			event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
			return event
		except Exception as exc:  # noqa: BLE001
			logger.warning("Stripe signature verification failed: %s", exc)
			return None
	try:
		# No secret: try to decode JSON directly
		import json
		return json.loads(payload.decode("utf-8"))
	except Exception:  # noqa: BLE001
		return None
