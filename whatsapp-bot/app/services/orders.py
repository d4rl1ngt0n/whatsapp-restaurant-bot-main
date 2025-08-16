from typing import List, Tuple
from uuid import uuid4
import os

from sqlalchemy import select, delete

from app.models import CartItem, MenuItem, Order, OrderItem, User
from app.services.db import get_session

# Currency formatting
CURRENCY_CODE = (os.getenv("PAYSTACK_CURRENCY") or os.getenv("CURRENCY") or "USD").upper()
_SYMBOL_MAP = {"USD": "$", "GHS": "GH₵", "NGN": "₦", "EUR": "€", "GBP": "£"}

def _currency_symbol() -> str:
	return _SYMBOL_MAP.get(CURRENCY_CODE, f"{CURRENCY_CODE} ")

def _fmt(amount: float) -> str:
	return f"{_currency_symbol()}{amount:.2f}"


def get_or_create_user(wa_id: str, phone: str | None = None, name: str | None = None) -> User:
	with get_session() as s:
		user = s.execute(select(User).where(User.wa_id == wa_id)).scalars().first()
		if user:
			return user
		user = User(wa_id=wa_id, phone=phone, name=name)
		s.add(user)
		s.flush()
		return user


def add_item_to_cart(wa_id: str, item_number: int, quantity: int = 1) -> tuple[bool, str]:
	with get_session() as s:
		user = s.execute(select(User).where(User.wa_id == wa_id)).scalars().first()
		if not user:
			user = User(wa_id=wa_id)
			s.add(user)
			s.flush()
		item = s.execute(select(MenuItem).where(MenuItem.number == item_number, MenuItem.available == True)).scalars().first()  # noqa: E712
		if not item:
			return False, "Item not found or unavailable."
		ci = s.execute(select(CartItem).where(CartItem.user_id == user.id, CartItem.menu_item_id == item.id)).scalars().first()
		if ci:
			ci.quantity += quantity
		else:
			ci = CartItem(user_id=user.id, menu_item_id=item.id, quantity=quantity)
			s.add(ci)
		return True, f"Added {quantity} x #{item.number} {item.name}"


def get_cart(wa_id: str) -> List[tuple[MenuItem, int, float]]:
	with get_session() as s:
		user = s.execute(select(User).where(User.wa_id == wa_id)).scalars().first()
		if not user:
			return []
		rows: List[tuple[MenuItem, int, float]] = []
		for ci in user.cart_items:
			item = s.get(MenuItem, ci.menu_item_id)
			if not item:
				continue
			rows.append((item, ci.quantity, item.price * ci.quantity))
		return rows


def clear_cart(wa_id: str) -> None:
	with get_session() as s:
		user = s.execute(select(User).where(User.wa_id == wa_id)).scalars().first()
		if not user:
			return
		s.execute(delete(CartItem).where(CartItem.user_id == user.id))


def cart_total(wa_id: str) -> float:
	return sum(line[2] for line in get_cart(wa_id))


def cart_summary_text(wa_id: str) -> str:
	lines: List[str] = []
	rows = get_cart(wa_id)
	if not rows:
		return "Your cart is empty."
	for item, qty, subtotal in rows:
		lines.append(f"#{item.number} {item.name} x{qty} = {_fmt(subtotal)}")
	lines.append("")
	lines.append(f"Total: {_fmt(sum(r[2] for r in rows))}")
	return "\n".join(lines)


def create_order_from_cart(wa_id: str, order_type: str, address: str | None = None) -> tuple[bool, str, Order | None, List[tuple[str, float, int]]]:
	"""Create the order and return (ok, message_or_order_number, order, line_items).
	line_items = list of (name, unit_price, quantity)
	"""
	with get_session() as s:
		user = s.execute(select(User).where(User.wa_id == wa_id)).scalars().first()
		if not user:
			return False, "No user", None, []
		cart = list(user.cart_items)
		if not cart:
			return False, "Cart is empty", None, []
		order = Order(
			order_number=str(uuid4()).split("-")[0].upper(),
			user_id=user.id,
			status="pending",
			type=order_type,
			address=address,
			total=0.0,
			payment_status="unpaid",
		)
		s.add(order)
		s.flush()
		total = 0.0
		line_items: List[tuple[str, float, int]] = []
		for ci in cart:
			item = s.get(MenuItem, ci.menu_item_id)
			if not item:
				continue
			line_total = item.price * ci.quantity
			s.add(OrderItem(order_id=order.id, menu_item_id=item.id, quantity=ci.quantity, unit_price=item.price, total_price=line_total))
			total += line_total
			line_items.append((f"#{item.number} {item.name}", float(item.price), int(ci.quantity)))
		s.execute(delete(CartItem).where(CartItem.user_id == user.id))
		order.total = total
		s.flush()
		return True, order.order_number, order, line_items
