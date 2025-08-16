import logging
import os
import re
import time
from collections import deque
from typing import Any, Optional
from datetime import datetime, timedelta
import random

from flask import Flask, jsonify, make_response, request, render_template

from app.services.whatsapp import send_text_message, send_interactive_buttons
from app.services.db import init_db
from app.services import menu as menu_service
from app.services import orders as order_service
from app.services import ai as ai_service
from app.services import payments as payments_service
from app.services import paystack as paystack_service
from app.seed_menu import main as seed_menu
from app.models import ProcessedMessage, Order, User, MenuItem, OrderItem
from app.services.db import get_session
from sqlalchemy import select

# Create app with explicit templates folder
app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "templates"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
RESTAURANT_NAME = os.getenv("RESTAURANT_NAME", "Our Restaurant")
logging.basicConfig(
	level=LOG_LEVEL,
	format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("whatsapp-bot")

APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "change-me-verify")

PAYMENT_PROVIDER = (os.getenv("PAYMENT_PROVIDER", "stripe") or "stripe").strip().lower()
if PAYMENT_PROVIDER not in ("stripe", "paystack"):
	PAYMENT_PROVIDER = "stripe"

# Currency formatting
CURRENCY_CODE = (os.getenv("PAYSTACK_CURRENCY") or os.getenv("CURRENCY") or "USD").upper()
_SYMBOL_MAP = {"USD": "$", "GHS": "GH₵", "NGN": "₦", "EUR": "€", "GBP": "£"}

def _currency_symbol() -> str:
	return _SYMBOL_MAP.get(CURRENCY_CODE, f"{CURRENCY_CODE} ")


def _fmt(amount: float) -> str:
	return f"{_currency_symbol()}{amount:.2f}"

_recent_message_ids: deque[str] = deque(maxlen=1000)
# Simple per-worker pending quantity state: wa_id -> item_number
_pending_qty: dict[str, int] = {}
# Pending checkout step: wa_id -> {stage: 'choose_type'|'collect_address', type: 'pickup'|'delivery'}
_checkout_state: dict[str, dict[str, str]] = {}

# Initialize database and seed menu at import time
init_db()
try:
	seed_menu()
except Exception:  # noqa: BLE001
	logger.exception("Menu seeding failed; continuing without fatal error")


def _is_duplicate(message_id: Optional[str]) -> bool:
	if not message_id:
		return False
	if message_id in _recent_message_ids:
		return True
	_recent_message_ids.append(message_id)
	return False


@app.get("/health")
def health() -> Any:
	return jsonify({
		"status": "ok",
		"timestamp": int(time.time()),
		"version": APP_VERSION,
	})


@app.get("/webhook")
def verify() -> Any:
	mode = request.args.get("hub.mode")
	token = request.args.get("hub.verify_token")
	challenge = request.args.get("hub.challenge", "")

	if mode == "subscribe" and token == VERIFY_TOKEN:
		logger.info("Webhook verified")
		response = make_response(challenge, 200)
		response.mimetype = "text/plain"
		return response

	logger.warning("Webhook verification failed: mode=%s", mode)
	return make_response("Forbidden", 403)


@app.post("/webhook")
def webhook() -> Any:
	payload = request.get_json(silent=True) or {}
	try:
		entries = payload.get("entry", [])
		for entry in entries:
			changes = entry.get("changes", [])
			for change in changes:
				value = change.get("value", {})
				messages = value.get("messages", [])
				contacts = value.get("contacts", [])
				contact_name = None
				if contacts:
					profile = (contacts[0] or {}).get("profile") or {}
					contact_name = profile.get("name")
				for msg in messages:
					message_id = msg.get("id")
					if _is_duplicate(message_id):
						continue
					# DB-backed idempotency
					if message_id:
						with get_session() as s:
							if s.query(ProcessedMessage).filter_by(message_id=message_id).first():
								continue
							s.add(ProcessedMessage(message_id=message_id))

					from_wa_id = msg.get("from")
					text = None
					msg_type = msg.get("type")
					if msg_type == "text":
						text = (msg.get("text") or {}).get("body")
					elif msg_type == "interactive":
						interactive = msg.get("interactive") or {}
						button_id = (interactive.get("button_reply") or {}).get("id")
						button_title = (interactive.get("button_reply") or {}).get("title")
						list_id = (interactive.get("list_reply") or {}).get("id")
						list_title = (interactive.get("list_reply") or {}).get("title")
						text = button_id or list_id or button_title or list_title

					if not from_wa_id:
						continue

					lower = (text or "").strip().lower()

					# Short-circuit if collecting checkout details
					if from_wa_id in _checkout_state:
						state = _checkout_state[from_wa_id]
						if state.get("stage") == "choose_type":
							if lower in ("pickup", "delivery"):
								state["type"] = lower
								if lower == "delivery":
									state["stage"] = "collect_address"
									send_text_message(from_wa_id, "Please send your delivery address (e.g., '12 High St, Apt 3, 94107')")
									continue
								else:
									_checkout_create_order_and_pay(from_wa_id, order_type="pickup")
									_checkout_state.pop(from_wa_id, None)
									continue
						elif state.get("stage") == "collect_address":
							address = (text or "").strip()
							_checkout_create_order_and_pay(from_wa_id, order_type="delivery", address=address)
							_checkout_state.pop(from_wa_id, None)
							continue

					# Global commands reset pending quantity and checkout state
					if lower in ("hi", "hello", "start"):
						_pending_qty.pop(from_wa_id, None)
						_checkout_state.pop(from_wa_id, None)
						_send_personalized_welcome(from_wa_id, contact_name)
						continue

					if lower in ("menu", "browse_menu", "browse"):
						_pending_qty.pop(from_wa_id, None)
						_checkout_state.pop(from_wa_id, None)
						_send_full_menu(from_wa_id)
						continue

					if lower in ("cart", "view_cart"):
						_pending_qty.pop(from_wa_id, None)
						_checkout_state.pop(from_wa_id, None)
						_send_cart(from_wa_id)
						continue

					if lower in ("clear cart", "clear"):
						_pending_qty.pop(from_wa_id, None)
						_checkout_state.pop(from_wa_id, None)
						order_service.clear_cart(from_wa_id)
						send_text_message(from_wa_id, "Cart cleared.")
						_send_menu_buttons(from_wa_id)
						continue

					if lower in ("help",):
						_pending_qty.pop(from_wa_id, None)
						_checkout_state.pop(from_wa_id, None)
						_send_help(from_wa_id)
						continue

					if lower in ("checkout",):
						_pending_qty.pop(from_wa_id, None)
						_checkout_state[from_wa_id] = {"stage": "choose_type"}
						send_interactive_buttons(
							from_wa_id,
							"Checkout: Pickup or Delivery?",
							[{"id": "pickup", "title": "Pickup"}, {"id": "delivery", "title": "Delivery"}, {"id": "view_cart", "title": "View Cart"}],
						)
						continue

					if lower in ("ai_reco", "recommend", "recommendations"):
						_pending_qty.pop(from_wa_id, None)
						_checkout_state.pop(from_wa_id, None)
						send_text_message(from_wa_id, "Tell me your preferences (e.g., 'vegan high protein no nuts') and I'll suggest options.")
						continue

					# Status command: status <order_number>
					m_status = re.match(r"^status\s+([A-Za-z0-9]+)$", lower)
					if m_status:
						_order_no = m_status.group(1).upper()
						_send_order_status(from_wa_id, _order_no)
						continue

					# Interactive qty buttons: qty|<number>|<qty>
					if lower.startswith("qty|"):
						try:
							_, num_str, qty_str = lower.split("|", 2)
							num = int(num_str)
							qty = int(qty_str)
							_add_to_cart_and_confirm(from_wa_id, num, qty)
							_pending_qty.pop(from_wa_id, None)
							continue
						except Exception:
							pass

					# Pattern: "<number> x <qty>" or "<number> <qty>"
					match = re.match(r"^(\d+)\s*[xX]\s*(\d+)$", lower) or re.match(r"^(\d+)\s+(\d+)$", lower)
					if match:
						num = int(match.group(1))
						qty = int(match.group(2))
						_add_to_cart_and_confirm(from_wa_id, num, qty)
						_pending_qty.pop(from_wa_id, None)
						continue

					# If we are awaiting quantity
					if from_wa_id in _pending_qty and lower.isdigit():
						qty = int(lower)
						num = _pending_qty.get(from_wa_id) or 0
						if num > 0 and 1 <= qty <= 20:
							_add_to_cart_and_confirm(from_wa_id, num, qty)
							_pending_qty.pop(from_wa_id, None)
							continue

					# Selecting an item by its number → prompt quantity
					if lower.isdigit():
						num = int(lower)
						item = menu_service.get_item_by_number(num)
						if not item or not item.available:
							send_text_message(from_wa_id, "Item not found or unavailable. Try 'menu' or 'search <term>'.")
							_send_menu_buttons(from_wa_id)
							continue
						_pending_qty[from_wa_id] = num
						_send_quantity_prompt(from_wa_id, num, item.name)
						continue

					# AI dietary guidance detection
					if any(k in lower for k in ["vegan", "vegetarian", "high protein", "protein", "low carb", "keto", "gluten", "allergy", "allergies", "dairy free", "nut free", "lactose"]):
						_send_ai_suggestions(from_wa_id, lower)
						continue

					# Search: explicit prefix
					if lower.startswith("search "):
						query = lower.split(" ", 1)[1].strip()
						_send_search_results(from_wa_id, query)
						continue

					# Implicit search for general text
					if lower and not lower.isdigit():
						_send_search_results(from_wa_id, lower)
						continue

					# Fallback
					send_text_message(from_wa_id, "Type 'menu' to browse the full menu or send a number to add an item.")

		return jsonify({"status": "received"})
	except Exception as exc:  # noqa: BLE001
		logger.exception("Error handling webhook: %s", exc)
		return jsonify({"status": "error"}), 200


def _send_personalized_welcome(wa_id: str, name: Optional[str]) -> None:
	username = name or "there"
	text = (
		f"Hello {username}! Welcome to {RESTAURANT_NAME}. I’m your cheerful digital waiter. "
		"I can show our full menu with prices, help you search or add by number, manage your cart, and checkout. "
		"I’m AI‑enabled—chat in your language and I’ll recommend dishes based on your preferences or allergies. "
		"What would you like to do today?"
	)
	send_text_message(wa_id, text)
	_send_welcome_buttons(wa_id)


def _send_welcome_buttons(wa_id: str) -> None:
	send_interactive_buttons(
		wa_id,
		"Choose an action:",
		[
			{"id": "browse_menu", "title": "Browse Menu"},
			{"id": "ai_reco", "title": "Get Recommendations"},
			{"id": "help", "title": "Help"},
		],
	)


def _send_full_menu(wa_id: str) -> None:
	items = menu_service.list_all_items()
	if not items:
		send_text_message(wa_id, "Our menu is being updated. Please try again shortly.")
		_send_menu_buttons(wa_id)
		return
	lines = ["Full menu with prices:"]
	for it in items:
		lines.append(f"#{it.number} {it.name} — {_fmt(it.price)}")
	lines.append("")
	lines.append("Reply with a number to add an item, then choose a quantity (e.g., '12 x 2').")
	send_text_message(wa_id, "\n".join(lines))
	_send_menu_buttons(wa_id)


def _send_menu_intro(wa_id: str) -> None:
	items = menu_service.list_items(limit=10)
	lines = ["Here are a few popular picks:"]
	for it in items:
		lines.append(f"#{it.number} {it.name} — {_fmt(it.price)}")
	lines.append("")
	lines.append("Reply with a number to select an item, then choose a quantity (e.g., '12 x 2').")
	send_text_message(wa_id, "\n".join(lines))
	_send_menu_buttons(wa_id)


def _send_menu_buttons(wa_id: str) -> None:
	send_interactive_buttons(
		wa_id,
		"Choose an action:",
		[
			{"id": "view_cart", "title": "View Cart"},
			{"id": "checkout", "title": "Checkout"},
			{"id": "help", "title": "Help"},
		],
	)


def _send_cart(wa_id: str) -> None:
	text = order_service.cart_summary_text(wa_id)
	send_text_message(wa_id, text)
	_send_cart_buttons(wa_id)


def _send_cart_buttons(wa_id: str) -> None:
	send_interactive_buttons(
		wa_id,
		"Next steps:",
		[
			{"id": "browse_menu", "title": "Browse Menu"},
			{"id": "checkout", "title": "Checkout"},
			{"id": "clear", "title": "Clear"},
		],
	)


def _send_help(wa_id: str) -> None:
	lines = [
		"Here’s how I can help:",
		"- Type 'menu' to see the full menu with prices",
		"- Send a number (e.g., 3) to pick an item, then a quantity (e.g., '2' or '3 x 2')",
		"- Type 'cart' to view your cart or 'clear' to empty it",
		"- Type 'checkout' to pay (Pickup or Delivery)",
		"- Type 'search <term>' to find dishes",
		"- Tell me your diet (e.g., 'vegan high protein') for tailored picks",
	]
	send_text_message(wa_id, "\n".join(lines))
	_send_welcome_buttons(wa_id)


def _send_search_results(wa_id: str, query: str) -> None:
	results = menu_service.search_items(query, limit=5)
	if not results:
		send_text_message(wa_id, f"No results for '{query}'. Try another search or type 'menu'.")
		_send_menu_buttons(wa_id)
		return
	lines = [f"Results for '{query}':"]
	for it in results:
		lines.append(f"#{it.number} {it.name} — {_fmt(it.price)}")
	lines.append("")
	lines.append("Send a number to select an item, then choose quantity (e.g., '12 x 2').")
	send_text_message(wa_id, "\n".join(lines))
	_send_cart_buttons(wa_id)


def _send_ai_suggestions(wa_id: str, user_text: str) -> None:
	suggestions = ai_service.suggest_items_for_preferences(user_text)
	if not suggestions:
		send_text_message(wa_id, "I couldn't find good matches. Try 'search <term>' or 'menu'.")
		_send_menu_buttons(wa_id)
		return
	lines = ["Suggestions for you:"]
	for number, name, price, why in suggestions:
		lines.append(f"#{number} {name} — {_fmt(price)} ({why})")
	lines.append("")
	lines.append("Send '<number> x <qty>' to add, e.g., '3 x 2'.")
	send_text_message(wa_id, "\n".join(lines))
	_send_cart_buttons(wa_id)


def _send_checkout_placeholder(wa_id: str) -> None:
	send_text_message(wa_id, "Checkout coming up next: we'll ask for pickup or delivery and generate a payment link.")
	_send_cart_buttons(wa_id)


def _send_quantity_prompt(wa_id: str, number: int, name: str) -> None:
	body = f"Great choice! How many #{number} {name} would you like? Reply with a number (1–9) or tap a button."
	buttons = [
		{"id": f"qty|{number}|1", "title": "x1"},
		{"id": f"qty|{number}|2", "title": "x2"},
		{"id": f"qty|{number}|3", "title": "x3"},
	]
	send_interactive_buttons(wa_id, body, buttons)


def _add_to_cart_and_confirm(wa_id: str, number: int, qty: int) -> None:
	qty = max(1, min(qty, 20))
	success, msg_text = order_service.add_item_to_cart(wa_id, number, qty)
	send_text_message(wa_id, msg_text)
	_send_cart(wa_id)


def _send_order_status(wa_id: str, order_number: str) -> None:
	with get_session() as s:
		order = s.execute(select(Order).where(Order.order_number == order_number)).scalars().first()
		if not order:
			send_text_message(wa_id, f"Order #{order_number} not found.")
			return
	text = f"Order #{order.order_number}: {order.status or 'unknown'} — total {_fmt(order.total)}"
	send_text_message(wa_id, text)


def _checkout_create_order_and_pay(wa_id: str, order_type: str, address: str | None = None) -> None:
	ok, order_number_or_msg, order_obj, line_items = order_service.create_order_from_cart(wa_id, order_type=order_type, address=address)
	if not ok or not order_obj:
		send_text_message(wa_id, f"Unable to create order: {order_number_or_msg}")
		return
	# For pickup, default to pay at counter and skip online payment
	if order_type == "pickup":
		send_text_message(wa_id, f"Order #{order_obj.order_number} created for pickup. Please pay at the counter when you arrive.")
		_send_cart_buttons(wa_id)
		return
	cart_lines = []
	for name, unit_price, qty in line_items:
		unit_minor = int(round(unit_price * 100))
		cart_lines.append((name, unit_minor, qty))
	logger.info("Creating checkout session via provider=%s for order=%s", PAYMENT_PROVIDER, order_obj.order_number)
	if PAYMENT_PROVIDER == "paystack":
		created, url, ref = paystack_service.create_checkout_session(order_obj.order_number, cart_lines, currency_code=CURRENCY_CODE)
	else:
		created, url, ref = payments_service.create_checkout_session(order_obj.order_number, cart_lines)
	if not created or not url:
		send_text_message(wa_id, f"Order #{order_obj.order_number} created. Payments are currently unavailable. We'll hold your order as 'pending'. You can try again later or choose 'Pickup' and pay at counter.")
		_send_cart_buttons(wa_id)
		return
	send_text_message(wa_id, f"Order #{order_obj.order_number} created. Pay securely here: {url}")
	_send_cart_buttons(wa_id)


@app.post("/payments/stripe/webhook")
def stripe_webhook() -> Any:
	payload = request.get_data()
	sig = request.headers.get("Stripe-Signature")
	event = payments_service.parse_webhook(payload, sig)
	if not event:
		return jsonify({"status": "ignored"})

	type_ = event.get("type")
	data = event.get("data", {}).get("object", {})
	if type_ in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
		order_number = (data.get("metadata") or {}).get("order_number")
		if order_number:
			# Mark order paid and notify user
			with get_session() as s:
				order = s.execute(select(Order).where(Order.order_number == order_number)).scalars().first()
				if order:
					if order.payment_status != "paid":
						order.payment_status = "paid"
						order.status = "preparing"
						user = s.execute(select(User).where(User.id == order.user_id)).scalars().first()
						if user and user.wa_id:
							send_text_message(user.wa_id, f"Payment received for order #{order.order_number}. Status: preparing. We'll update you when it's ready.")
							send_text_message(user.wa_id, f"Receipt: order #{order.order_number} total {_fmt(order.total)}. Thank you!")
	return jsonify({"status": "ok"})


# Add Paystack webhook
@app.post("/payments/paystack/webhook")
def paystack_webhook() -> Any:
	payload = request.get_data()
	sig = request.headers.get("x-paystack-signature")
	event = paystack_service.parse_webhook(payload, sig)
	if not event:
		return jsonify({"status": "ignored"})
	etype = (event.get("event") or event.get("event_type") or "").lower()
	data = event.get("data") or {}
	if etype in ("charge.success", "paymentrequest.success"):
		order_number = (data.get("metadata") or {}).get("order_number") or data.get("reference")
		if order_number:
			with get_session() as s:
				order = s.execute(select(Order).where(Order.order_number == order_number)).scalars().first()
				if order:
					if order.payment_status != "paid":
						order.payment_status = "paid"
						order.status = "preparing"
						user = s.execute(select(User).where(User.id == order.user_id)).scalars().first()
						if user and user.wa_id:
							send_text_message(user.wa_id, f"Payment received for order #{order.order_number}. Status: preparing. We'll update you when it's ready.")
							send_text_message(user.wa_id, f"Receipt: order #{order.order_number} total {_fmt(order.total)}. Thank you!")
	return jsonify({"status": "ok"})


@app.get("/payments/paystack/verify")
def paystack_verify_get() -> Any:
	order_number = request.args.get("order_number") or request.args.get("reference")
	if not order_number:
		return jsonify({"error": "missing order_number_or_reference"}), 400
	with get_session() as s:
		order = s.execute(select(Order).where(Order.order_number == order_number)).scalars().first()
		if not order:
			return jsonify({"error": "order_not_found"}), 404
		paid, resp = paystack_service.verify_transaction(order_number)
		if paid and order.payment_status != "paid":
			order.payment_status = "paid"
			order.status = "preparing"
			user = s.execute(select(User).where(User.id == order.user_id)).scalars().first()
			if user and user.wa_id:
				send_text_message(user.wa_id, f"Payment verified for order #{order.order_number}. Status: preparing. We'll update you when it's ready.")
				send_text_message(user.wa_id, f"Receipt: order #{order.order_number} total {_fmt(order.total)}. Thank you!")
		return jsonify({"paid": paid, "provider_response": resp})


# Admin endpoints
@app.get("/orders")
def list_orders() -> Any:
	status = (request.args.get("status") or "active").lower()
	start = request.args.get("start")
	end = request.args.get("end")
	with get_session() as s:
		q = select(Order)
		if status == "active":
			q = q.where(Order.status.in_(["pending", "preparing", "ready"]))
		elif status == "completed":
			q = q.where(Order.status.in_(["completed", "cancelled"]))
		if start:
			try:
				start_dt = datetime.fromisoformat(start)
				q = q.where(Order.created_at >= start_dt)
			except Exception:
				pass
		if end:
			try:
				end_dt = datetime.fromisoformat(end)
				q = q.where(Order.created_at <= end_dt)
			except Exception:
				pass
		orders = list(s.execute(q.order_by(Order.created_at.desc())).scalars())
		def serialize(o: Order) -> dict:
			return {
				"order_number": o.order_number,
				"status": o.status,
				"type": o.type,
				"address": o.address,
				"total": o.total,
				"payment_status": o.payment_status,
				"created_at": o.created_at.isoformat(),
			}
		return jsonify([serialize(o) for o in orders])


@app.post("/orders/update-status")
def update_order_status() -> Any:
	body = request.get_json(silent=True) or {}
	order_number = (body.get("order_number") or "").strip().upper()
	new_status = (body.get("status") or "").strip().lower()
	if not order_number or not new_status:
		return jsonify({"error": "missing order_number or status"}), 400
	with get_session() as s:
		order = s.execute(select(Order).where(Order.order_number == order_number)).scalars().first()
		if not order:
			return jsonify({"error": "order_not_found"}), 404
		order.status = new_status
		user = s.execute(select(User).where(User.id == order.user_id)).scalars().first()
		if user and user.wa_id:
			msg = f"Order #{order.order_number} status updated: {order.status}."
			if order.total is not None:
				msg += f" Total: {_fmt(order.total)}."
			send_text_message(user.wa_id, msg)
		return jsonify({"ok": True, "order_number": order.order_number, "status": order.status})


@app.get("/api/analytics")
def analytics() -> Any:
	start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
	with get_session() as s:
		orders_today = list(s.execute(select(Order).where(Order.created_at >= start)).scalars())
		orders_all = list(s.execute(select(Order)).scalars())
		revenue_today = sum(o.total or 0 for o in orders_today if (o.payment_status or "") == "paid")
		total_revenue = sum(o.total or 0 for o in orders_all if (o.payment_status or "") == "paid")
		return jsonify({
			"orders_today": len(orders_today),
			"revenue_today": revenue_today,
			"total_orders": len(orders_all),
			"total_revenue": total_revenue,
		})


@app.get("/menu")
def list_menu() -> Any:
	with get_session() as s:
		items = list(s.execute(select(MenuItem).order_by(MenuItem.number)).scalars())
		return jsonify([{
			"id": m.id,
			"number": m.number,
			"name": m.name,
			"price": m.price,
			"available": m.available,
			"category": m.category,
			"tags": m.tags,
		} for m in items])


@app.post("/menu/update-availability")
def update_menu_availability() -> Any:
	body = request.get_json(silent=True) or {}
	item_number = body.get("number")
	available = body.get("available")
	if item_number is None or available is None:
		return jsonify({"error": "missing number or available"}), 400
	with get_session() as s:
		item = s.execute(select(MenuItem).where(MenuItem.number == int(item_number))).scalars().first()
		if not item:
			return jsonify({"error": "item_not_found"}), 404
		item.available = bool(available)
		return jsonify({"ok": True, "number": item.number, "available": item.available})


@app.get("/admin")
def admin_page() -> Any:
	return render_template("admin.html")


@app.post("/admin/create-test-data")
def create_test_data() -> Any:
	try:
		from app.models import OrderItem as _OrderItem
		with get_session() as s:
			# Ensure some menu items exist
			if not list(s.execute(select(MenuItem)).scalars()):
				for i in range(1, 8):
					s.add(MenuItem(number=i, name=f"Test Dish {i}", description="Sample", price=10.0 + i, category="Test", tags="", available=True))
			# Create a few fake users and orders
			for _ in range(5):
				u = User(wa_id=str(random.randint(1000000000, 9999999999)), name=f"User{random.randint(1,999)}")
				s.add(u); s.flush()
				from uuid import uuid4
				order = Order(order_number=str(uuid4()).split('-')[0].upper(), user_id=u.id, status=random.choice(["pending","preparing","ready"]), type=random.choice(["pickup","delivery"]), total=0.0, payment_status="unpaid")
				s.add(order); s.flush()
				items = list(s.execute(select(MenuItem).limit(3)).scalars())
				total = 0.0
				for it in items:
					qty = random.randint(1,2)
					line = it.price * qty
					s.add(_OrderItem(order_id=order.id, menu_item_id=it.id, quantity=qty, unit_price=it.price, total_price=line))
					total += line
				order.total = total
		return jsonify({"ok": True})
	except Exception as e:
		logger.exception("create-test-data failed: %s", e)
		return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
	app.run(host="0.0.0.0", port=8080)
