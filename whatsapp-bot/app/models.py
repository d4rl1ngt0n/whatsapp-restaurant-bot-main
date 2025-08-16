from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.services.db import Base


class User(Base):
	__tablename__ = "users"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	wa_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
	phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
	name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
	preferred_language: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
	created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
	total_orders: Mapped[int] = mapped_column(Integer, default=0)
	total_spent: Mapped[float] = mapped_column(Float, default=0.0)

	orders: Mapped[list["Order"]] = relationship("Order", back_populates="user")
	cart_items: Mapped[list["CartItem"]] = relationship("CartItem", back_populates="user", cascade="all, delete-orphan")


class MenuItem(Base):
	__tablename__ = "menu_items"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	number: Mapped[int] = mapped_column(Integer, unique=True, index=True)
	name: Mapped[str] = mapped_column(String(128))
	description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
	price: Mapped[float] = mapped_column(Float)
	category: Mapped[Optional[str]] = mapped_column(String(64), index=True)
	tags: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)  # comma-separated
	available: Mapped[bool] = mapped_column(Boolean, default=True)

	order_items: Mapped[list["OrderItem"]] = relationship("OrderItem", back_populates="menu_item")


class Order(Base):
	__tablename__ = "orders"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	order_number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
	user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
	status: Mapped[str] = mapped_column(String(16))  # pending|preparing|ready|completed|cancelled
	type: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # pickup|delivery
	address: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
	total: Mapped[float] = mapped_column(Float, default=0.0)
	payment_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
	created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
	updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

	user: Mapped["User"] = relationship("User", back_populates="orders")
	items: Mapped[list["OrderItem"]] = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
	payments: Mapped[list["Payment"]] = relationship("Payment", back_populates="order")


class OrderItem(Base):
	__tablename__ = "order_items"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
	menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id"))
	quantity: Mapped[int] = mapped_column(Integer, default=1)
	unit_price: Mapped[float] = mapped_column(Float)
	total_price: Mapped[float] = mapped_column(Float)

	order: Mapped["Order"] = relationship("Order", back_populates="items")
	menu_item: Mapped["MenuItem"] = relationship("MenuItem", back_populates="order_items")


class Payment(Base):
	__tablename__ = "payments"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
	provider: Mapped[str] = mapped_column(String(32))
	status: Mapped[str] = mapped_column(String(16))
	amount: Mapped[float] = mapped_column(Float)
	ref: Mapped[str] = mapped_column(String(64))
	created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

	order: Mapped["Order"] = relationship("Order", back_populates="payments")


class CartItem(Base):
	__tablename__ = "cart_items"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
	menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id"))
	quantity: Mapped[int] = mapped_column(Integer, default=1)

	user: Mapped["User"] = relationship("User", back_populates="cart_items")
	menu_item: Mapped["MenuItem"] = relationship("MenuItem")


class ProcessedMessage(Base):
	__tablename__ = "processed_messages"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	message_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
	created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
