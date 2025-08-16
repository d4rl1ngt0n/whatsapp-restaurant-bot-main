import os
import logging
from typing import Optional, Dict, Any
from functools import wraps
from contextlib import contextmanager
from threading import local

from flask import request, g, abort, jsonify
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Organization, Tenant, User, UserRole, TenantConfiguration
from app.services.db import get_session

logger = logging.getLogger("tenant-service")

# Thread-local storage for tenant context
_tenant_context = local()


class TenantContext:
    """Manages tenant context throughout the request lifecycle"""
    
    def __init__(self):
        self.tenant_id: Optional[int] = None
        self.organization_id: Optional[int] = None
        self.tenant: Optional[Tenant] = None
        self.organization: Optional[Organization] = None
        self.user: Optional[User] = None
        self.configuration: Optional[TenantConfiguration] = None
    
    def set_tenant(self, tenant: Tenant):
        """Set the current tenant context"""
        self.tenant_id = tenant.id
        self.organization_id = tenant.organization_id
        self.tenant = tenant
        
        # Load organization
        with get_session() as session:
            self.organization = session.execute(
                select(Organization).where(Organization.id == tenant.organization_id)
            ).scalars().first()
            
            # Load configuration
            self.configuration = session.execute(
                select(TenantConfiguration).where(TenantConfiguration.tenant_id == tenant.id)
            ).scalars().first()
    
    def set_user(self, user: User):
        """Set the current user context"""
        self.user = user
    
    def clear(self):
        """Clear the current context"""
        self.tenant_id = None
        self.organization_id = None
        self.tenant = None
        self.organization = None
        self.user = None
        self.configuration = None


def get_current_tenant_context() -> TenantContext:
    """Get the current tenant context"""
    if not hasattr(_tenant_context, 'context'):
        _tenant_context.context = TenantContext()
    return _tenant_context.context


def get_current_tenant() -> Optional[Tenant]:
    """Get the current tenant"""
    return get_current_tenant_context().tenant


def get_current_organization() -> Optional[Organization]:
    """Get the current organization"""
    return get_current_tenant_context().organization


def get_current_user() -> Optional[User]:
    """Get the current user"""
    return get_current_tenant_context().user


def get_tenant_config() -> Optional[TenantConfiguration]:
    """Get the current tenant configuration"""
    return get_current_tenant_context().configuration


class TenantResolver:
    """Resolves tenant from various sources"""
    
    @staticmethod
    def from_subdomain(subdomain: str) -> Optional[Tenant]:
        """Resolve tenant from subdomain (e.g., pizza-palace.yourdomain.com)"""
        if not subdomain:
            return None
            
        with get_session() as session:
            # Try organization slug first
            org = session.execute(
                select(Organization).where(Organization.slug == subdomain)
            ).scalars().first()
            
            if org:
                # For single-tenant organizations, get the first tenant
                tenant = session.execute(
                    select(Tenant).where(Tenant.organization_id == org.id)
                ).scalars().first()
                return tenant
            
            # Try tenant slug
            tenant = session.execute(
                select(Tenant).where(Tenant.slug == subdomain)
            ).scalars().first()
            return tenant
    
    @staticmethod
    def from_domain(domain: str) -> Optional[Tenant]:
        """Resolve tenant from custom domain"""
        if not domain:
            return None
            
        with get_session() as session:
            org = session.execute(
                select(Organization).where(Organization.custom_domain == domain)
            ).scalars().first()
            
            if org:
                tenant = session.execute(
                    select(Tenant).where(Tenant.organization_id == org.id)
                ).scalars().first()
                return tenant
        return None
    
    @staticmethod
    def from_whatsapp_phone(phone_number_id: str) -> Optional[Tenant]:
        """Resolve tenant from WhatsApp phone number ID"""
        if not phone_number_id:
            return None
            
        with get_session() as session:
            tenant = session.execute(
                select(Tenant).where(Tenant.wa_phone_number_id == phone_number_id)
            ).scalars().first()
            return tenant
    
    @staticmethod
    def from_tenant_id(tenant_id: int) -> Optional[Tenant]:
        """Resolve tenant from ID"""
        with get_session() as session:
            tenant = session.execute(
                select(Tenant).where(Tenant.id == tenant_id)
            ).scalars().first()
            return tenant
    
    @staticmethod
    def from_api_key(api_key: str) -> Optional[Tenant]:
        """Resolve tenant from API key (for future API authentication)"""
        # TODO: Implement API key-based tenant resolution
        return None


def resolve_tenant_from_request() -> Optional[Tenant]:
    """Resolve tenant from current HTTP request"""
    
    # 1. Try custom domain
    host = request.headers.get('Host', '').lower()
    if host:
        tenant = TenantResolver.from_domain(host)
        if tenant:
            return tenant
    
    # 2. Try subdomain
    if '.' in host:
        subdomain = host.split('.')[0]
        tenant = TenantResolver.from_subdomain(subdomain)
        if tenant:
            return tenant
    
    # 3. Try tenant header (for API calls)
    tenant_header = request.headers.get('X-Tenant-ID')
    if tenant_header:
        try:
            tenant_id = int(tenant_header)
            tenant = TenantResolver.from_tenant_id(tenant_id)
            if tenant:
                return tenant
        except ValueError:
            pass
    
    # 4. Try URL parameter
    tenant_param = request.args.get('tenant_id') or request.args.get('tenant')
    if tenant_param:
        try:
            tenant_id = int(tenant_param)
            tenant = TenantResolver.from_tenant_id(tenant_id)
            if tenant:
                return tenant
        except ValueError:
            pass
    
    # 5. For WhatsApp webhooks, try to resolve from phone number
    if request.path == '/webhook' and request.method == 'POST':
        payload = request.get_json(silent=True) or {}
        # Extract phone number ID from WhatsApp webhook
        for entry in payload.get('entry', []):
            for change in entry.get('changes', []):
                metadata = change.get('value', {}).get('metadata', {})
                phone_number_id = metadata.get('phone_number_id')
                if phone_number_id:
                    tenant = TenantResolver.from_whatsapp_phone(phone_number_id)
                    if tenant:
                        return tenant
    
    return None


def resolve_user_from_whatsapp(wa_id: str, tenant: Tenant) -> Optional[User]:
    """Resolve user from WhatsApp ID within tenant context"""
    if not wa_id or not tenant:
        return None
        
    with get_session() as session:
        user = session.execute(
            select(User).where(
                User.wa_id == wa_id,
                User.tenant_id == tenant.id
            )
        ).scalars().first()
        return user


def create_tenant_user(wa_id: str, tenant: Tenant, name: Optional[str] = None, 
                      phone: Optional[str] = None) -> User:
    """Create a new user within tenant context"""
    with get_session() as session:
        user = User(
            wa_id=wa_id,
            tenant_id=tenant.id,
            organization_id=tenant.organization_id,
            name=name,
            phone=phone,
            role=UserRole.CUSTOMER
        )
        session.add(user)
        session.flush()
        return user


def require_tenant(f):
    """Decorator to require valid tenant context"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        context = get_current_tenant_context()
        if not context.tenant:
            return jsonify({"error": "Tenant context required"}), 400
        return f(*args, **kwargs)
    return decorated_function


def require_role(*roles: UserRole):
    """Decorator to require specific user roles"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            context = get_current_tenant_context()
            if not context.user:
                return jsonify({"error": "Authentication required"}), 401
            
            if context.user.role not in roles:
                return jsonify({"error": "Insufficient permissions"}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_tenant_admin(f):
    """Decorator to require tenant admin or higher"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        context = get_current_tenant_context()
        if not context.user:
            return jsonify({"error": "Authentication required"}), 401
        
        allowed_roles = [UserRole.SUPER_ADMIN, UserRole.TENANT_ADMIN, UserRole.MANAGER]
        if context.user.role not in allowed_roles:
            return jsonify({"error": "Admin access required"}), 403
        
        return f(*args, **kwargs)
    return decorated_function


@contextmanager
def tenant_db_session(tenant_id: Optional[int] = None):
    """Context manager for tenant-scoped database sessions"""
    context = get_current_tenant_context()
    effective_tenant_id = tenant_id or context.tenant_id
    
    with get_session() as session:
        # Set tenant context for the session
        if effective_tenant_id:
            session.execute("SET app.current_tenant_id = :tenant_id", {"tenant_id": effective_tenant_id})
        yield session


def filter_by_tenant(query, model_class, tenant_id: Optional[int] = None):
    """Add tenant filter to SQLAlchemy query"""
    context = get_current_tenant_context()
    effective_tenant_id = tenant_id or context.tenant_id
    
    if not effective_tenant_id:
        raise ValueError("No tenant context available")
    
    # Check if model has tenant_id attribute
    if hasattr(model_class, 'tenant_id'):
        return query.where(model_class.tenant_id == effective_tenant_id)
    
    return query


class TenantService:
    """High-level service for tenant operations"""
    
    @staticmethod
    def create_organization(name: str, slug: str, contact_email: str, 
                          plan: str = "basic") -> Organization:
        """Create a new organization"""
        with get_session() as session:
            org = Organization(
                name=name,
                slug=slug,
                contact_email=contact_email,
                plan=plan,
                is_active=True
            )
            session.add(org)
            session.flush()
            return org
    
    @staticmethod
    def create_tenant(organization_id: int, name: str, slug: str, 
                     currency: str = "USD", language: str = "en") -> Tenant:
        """Create a new tenant within an organization"""
        with get_session() as session:
            tenant = Tenant(
                organization_id=organization_id,
                name=name,
                slug=slug,
                currency=currency,
                language=language,
                is_active=True
            )
            session.add(tenant)
            session.flush()
            
            # Create default configuration
            config = TenantConfiguration(tenant_id=tenant.id)
            session.add(config)
            
            return tenant
    
    @staticmethod
    def get_tenant_stats(tenant_id: int) -> Dict[str, Any]:
        """Get comprehensive stats for a tenant"""
        with get_session() as session:
            from app.models import Order, MenuItem
            
            # Basic counts
            total_orders = session.execute(
                select(Order).where(Order.tenant_id == tenant_id)
            ).scalars().all()
            
            total_menu_items = session.execute(
                select(MenuItem).where(MenuItem.tenant_id == tenant_id)
            ).scalars().all()
            
            total_users = session.execute(
                select(User).where(User.tenant_id == tenant_id)
            ).scalars().all()
            
            # Revenue calculation
            paid_orders = [o for o in total_orders if o.payment_status == "paid"]
            total_revenue = sum(o.total for o in paid_orders)
            
            return {
                "total_orders": len(total_orders),
                "total_revenue": total_revenue,
                "total_menu_items": len(total_menu_items),
                "total_customers": len([u for u in total_users if u.role == UserRole.CUSTOMER]),
                "total_staff": len([u for u in total_users if u.role in [UserRole.MANAGER, UserRole.STAFF]]),
                "active_menu_items": len([m for m in total_menu_items if m.available]),
            }
    
    @staticmethod
    def setup_demo_tenant(organization_id: int) -> Tenant:
        """Set up a demo tenant with sample data"""
        from app.models import MenuItem
        
        tenant = TenantService.create_tenant(
            organization_id=organization_id,
            name="Demo Restaurant",
            slug="demo",
            currency="USD",
            language="en"
        )
        
        # Add sample menu items
        with get_session() as session:
            sample_items = [
                {"number": 1, "name": "Margherita Pizza", "price": 12.99, "category": "Pizza"},
                {"number": 2, "name": "Caesar Salad", "price": 8.99, "category": "Salads"},
                {"number": 3, "name": "Chicken Burger", "price": 14.99, "category": "Burgers"},
                {"number": 4, "name": "Spaghetti Carbonara", "price": 13.99, "category": "Pasta"},
                {"number": 5, "name": "Chocolate Cake", "price": 6.99, "category": "Desserts"},
            ]
            
            for item_data in sample_items:
                item = MenuItem(
                    tenant_id=tenant.id,
                    **item_data,
                    description=f"Delicious {item_data['name']}",
                    available=True
                )
                session.add(item)
        
        return tenant