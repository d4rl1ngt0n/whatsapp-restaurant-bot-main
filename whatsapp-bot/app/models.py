from datetime import datetime
from typing import Optional
from enum import Enum

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.services.db import Base


class PlanType(str, Enum):
	BASIC = "basic"
	PROFESSIONAL = "professional"
	ENTERPRISE = "enterprise"


class UserRole(str, Enum):
	SUPER_ADMIN = "super_admin"		# Platform admin
	TENANT_ADMIN = "tenant_admin"	# Organization owner
	MANAGER = "manager"				# Restaurant manager
	STAFF = "staff"					# Restaurant staff
	CUSTOMER = "customer"			# End customer


class Organization(Base):
	"""Top-level organization (restaurant chain/franchise)"""
	__tablename__ = "organizations"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	name: Mapped[str] = mapped_column(String(128))
	slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # URL-friendly identifier
	description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
	plan: Mapped[PlanType] = mapped_column(SQLEnum(PlanType), default=PlanType.BASIC)
	is_active: Mapped[bool] = mapped_column(Boolean, default=True)
	max_locations: Mapped[int] = mapped_column(Integer, default=1)  # Based on plan
	created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
	
	# Billing and contact info
	contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
	contact_phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
	billing_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
	
	# White-label customization
	brand_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
	logo_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
	primary_color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)  # #HEX color
	secondary_color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)
	custom_domain: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

	# Relationships
	tenants: Mapped[list["Tenant"]] = relationship("Tenant", back_populates="organization")
	users: Mapped[list["User"]] = relationship("User", back_populates="organization")


class Tenant(Base):
	"""Individual restaurant/location within an organization"""
	__tablename__ = "tenants"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
	name: Mapped[str] = mapped_column(String(128))
	slug: Mapped[str] = mapped_column(String(64), index=True)  # Must be unique per org
	description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
	is_active: Mapped[bool] = mapped_column(Boolean, default=True)
	
	# Location details
	address: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
	city: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
	state: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
	country: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
	postal_code: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
	phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
	email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
	
	# Operating details
	timezone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, default="UTC")
	currency: Mapped[str] = mapped_column(String(3), default="USD")
	language: Mapped[str] = mapped_column(String(5), default="en")
	
	# WhatsApp configuration
	wa_phone_number_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
	wa_access_token: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
	wa_webhook_verify_token: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
	
	# Payment configuration
	payment_provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, default="stripe")
	stripe_account_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
	paystack_public_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
	paystack_secret_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
	
	created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

	# Relationships
	organization: Mapped["Organization"] = relationship("Organization", back_populates="tenants")
	users: Mapped[list["User"]] = relationship("User", back_populates="tenant")
	menu_items: Mapped[list["MenuItem"]] = relationship("MenuItem", back_populates="tenant")
	orders: Mapped[list["Order"]] = relationship("Order", back_populates="tenant")


class User(Base):
	__tablename__ = "users"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	organization_id: Mapped[Optional[int]] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
	tenant_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
	wa_id: Mapped[str] = mapped_column(String(32), index=True)  # Removed unique constraint for multi-tenancy
	phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
	name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
	email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
	role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole), default=UserRole.CUSTOMER)
	preferred_language: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
	is_active: Mapped[bool] = mapped_column(Boolean, default=True)
	created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
	last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
	
	# Customer-specific fields
	total_orders: Mapped[int] = mapped_column(Integer, default=0)
	total_spent: Mapped[float] = mapped_column(Float, default=0.0)

	# Relationships
	organization: Mapped[Optional["Organization"]] = relationship("Organization", back_populates="users")
	tenant: Mapped[Optional["Tenant"]] = relationship("Tenant", back_populates="users")
	orders: Mapped[list["Order"]] = relationship("Order", back_populates="user")
	cart_items: Mapped[list["CartItem"]] = relationship("CartItem", back_populates="user", cascade="all, delete-orphan")


class MenuItem(Base):
	__tablename__ = "menu_items"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
	number: Mapped[int] = mapped_column(Integer, index=True)  # Unique per tenant, not globally
	name: Mapped[str] = mapped_column(String(128))
	description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
	price: Mapped[float] = mapped_column(Float)
	category: Mapped[Optional[str]] = mapped_column(String(64), index=True)
	tags: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)  # comma-separated
	available: Mapped[bool] = mapped_column(Boolean, default=True)
	image_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
	
	# Nutritional info for enterprise features
	calories: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
	allergens: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)  # comma-separated
	dietary_tags: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)  # vegan, gluten-free, etc.

	# Relationships
	tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="menu_items")
	order_items: Mapped[list["OrderItem"]] = relationship("OrderItem", back_populates="menu_item")


class Order(Base):
	__tablename__ = "orders"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
	order_number: Mapped[str] = mapped_column(String(20), index=True)  # Unique per tenant
	user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
	status: Mapped[str] = mapped_column(String(16))  # pending|preparing|ready|completed|cancelled
	type: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # pickup|delivery
	address: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
	total: Mapped[float] = mapped_column(Float, default=0.0)
	tax_amount: Mapped[float] = mapped_column(Float, default=0.0)
	tip_amount: Mapped[float] = mapped_column(Float, default=0.0)
	payment_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
	special_instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
	estimated_ready_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
	created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
	updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

	# Relationships
	tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="orders")
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
	special_instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

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
	provider_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON response
	created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

	order: Mapped["Order"] = relationship("Order", back_populates="payments")


class CartItem(Base):
	__tablename__ = "cart_items"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
	menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id"))
	quantity: Mapped[int] = mapped_column(Integer, default=1)
	special_instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

	user: Mapped["User"] = relationship("User", back_populates="cart_items")
	menu_item: Mapped["MenuItem"] = relationship("MenuItem")


class ProcessedMessage(Base):
	__tablename__ = "processed_messages"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	tenant_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
	message_id: Mapped[str] = mapped_column(String(100), index=True)  # Unique per tenant
	created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# New models for advanced features
class TenantConfiguration(Base):
	"""Tenant-specific configuration and feature flags"""
	__tablename__ = "tenant_configurations"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), unique=True)
	
	# Feature flags
	enable_delivery: Mapped[bool] = mapped_column(Boolean, default=True)
	enable_pickup: Mapped[bool] = mapped_column(Boolean, default=True)
	enable_ai_recommendations: Mapped[bool] = mapped_column(Boolean, default=True)
	enable_loyalty_program: Mapped[bool] = mapped_column(Boolean, default=False)
	enable_table_reservations: Mapped[bool] = mapped_column(Boolean, default=False)
	
	# Business settings
	min_order_amount: Mapped[float] = mapped_column(Float, default=0.0)
	delivery_fee: Mapped[float] = mapped_column(Float, default=0.0)
	delivery_radius_km: Mapped[float] = mapped_column(Float, default=10.0)
	tax_rate: Mapped[float] = mapped_column(Float, default=0.0)
	
	# Operating hours (JSON string)
	operating_hours: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
	
	# AI configuration
	ai_provider: Mapped[str] = mapped_column(String(32), default="openai")
	ai_persona_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
	
	# WhatsApp templates and messages
	welcome_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
	order_confirmation_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
	
	created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
	updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuditLog(Base):
	"""Audit trail for important actions"""
	__tablename__ = "audit_logs"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	organization_id: Mapped[Optional[int]] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
	tenant_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
	user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
	
	action: Mapped[str] = mapped_column(String(64))  # create_order, update_menu, etc.
	resource_type: Mapped[str] = mapped_column(String(32))  # order, menu_item, user, etc.
	resource_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
	details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON details
	ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
	user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
	
	created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
