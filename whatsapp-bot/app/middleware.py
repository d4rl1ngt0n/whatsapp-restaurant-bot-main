import logging
from typing import Optional
from flask import Flask, request, g, jsonify

from app.services.tenant import (
    resolve_tenant_from_request, 
    resolve_user_from_whatsapp,
    get_current_tenant_context,
    TenantContext
)

logger = logging.getLogger("middleware")


class TenantMiddleware:
    """Middleware to handle tenant resolution and context setting"""
    
    def __init__(self, app: Flask):
        self.app = app
        self.init_app(app)
    
    def init_app(self, app: Flask):
        """Initialize middleware with Flask app"""
        app.before_request(self.before_request)
        app.after_request(self.after_request)
        app.teardown_appcontext(self.teardown_context)
    
    def before_request(self):
        """Set tenant context before each request"""
        context = get_current_tenant_context()
        context.clear()  # Clear any previous context
        
        # Skip tenant resolution for certain paths
        if self._should_skip_tenant_resolution():
            return
        
        # Resolve tenant from request
        tenant = resolve_tenant_from_request()
        if tenant:
            context.set_tenant(tenant)
            logger.debug(f"Tenant resolved: {tenant.name} (ID: {tenant.id})")
            
            # For WhatsApp webhooks, try to resolve user as well
            if request.path == '/webhook' and request.method == 'POST':
                wa_id = self._extract_whatsapp_user_id()
                if wa_id:
                    user = resolve_user_from_whatsapp(wa_id, tenant)
                    if user:
                        context.set_user(user)
                        logger.debug(f"User resolved: {user.name or user.wa_id}")
        
        # Set Flask g context for backward compatibility
        g.tenant = context.tenant
        g.organization = context.organization
        g.user = context.user
        g.tenant_config = context.configuration
    
    def after_request(self, response):
        """Process response after request"""
        # Add tenant info to response headers for debugging (dev only)
        if self.app.debug:
            context = get_current_tenant_context()
            if context.tenant:
                response.headers['X-Tenant-ID'] = str(context.tenant.id)
                response.headers['X-Tenant-Name'] = context.tenant.name
        
        return response
    
    def teardown_context(self, exception):
        """Clean up context after request"""
        context = get_current_tenant_context()
        context.clear()
    
    def _should_skip_tenant_resolution(self) -> bool:
        """Check if tenant resolution should be skipped for this request"""
        skip_paths = [
            '/health',
            '/static/',
            '/favicon.ico',
        ]
        
        # Skip for static files and health checks
        for path in skip_paths:
            if request.path.startswith(path):
                return True
        
        # Skip for webhook verification (GET /webhook)
        if request.path == '/webhook' and request.method == 'GET':
            return True
        
        return False
    
    def _extract_whatsapp_user_id(self) -> Optional[str]:
        """Extract WhatsApp user ID from webhook payload"""
        try:
            payload = request.get_json(silent=True) or {}
            for entry in payload.get('entry', []):
                for change in entry.get('changes', []):
                    messages = change.get('value', {}).get('messages', [])
                    for message in messages:
                        wa_id = message.get('from')
                        if wa_id:
                            return wa_id
        except Exception as e:
            logger.warning(f"Failed to extract WhatsApp user ID: {e}")
        
        return None


def handle_tenant_not_found():
    """Handle requests when tenant cannot be resolved"""
    if request.path.startswith('/api/') or request.path == '/webhook':
        return jsonify({
            "error": "Tenant not found",
            "message": "Please check your subdomain, domain, or tenant headers"
        }), 404
    
    # For web requests, could redirect to a tenant selection page
    return """
    <html>
        <head><title>Tenant Not Found</title></head>
        <body>
            <h1>Restaurant Not Found</h1>
            <p>The restaurant you're looking for could not be found.</p>
            <p>Please check your URL or contact support.</p>
        </body>
    </html>
    """, 404


def handle_tenant_inactive():
    """Handle requests for inactive tenants"""
    return jsonify({
        "error": "Restaurant temporarily unavailable",
        "message": "This restaurant is currently not accepting orders"
    }), 503


class SecurityMiddleware:
    """Security middleware for tenant isolation and protection"""
    
    def __init__(self, app: Flask):
        self.app = app
        self.init_app(app)
    
    def init_app(self, app: Flask):
        """Initialize security middleware"""
        app.before_request(self.check_tenant_security)
    
    def check_tenant_security(self):
        """Perform security checks for tenant requests"""
        context = get_current_tenant_context()
        
        # Skip security checks for non-tenant requests
        if not context.tenant:
            return
        
        # Check if tenant is active
        if not context.tenant.is_active:
            return handle_tenant_inactive()
        
        # Check if organization is active
        if context.organization and not context.organization.is_active:
            return jsonify({
                "error": "Organization suspended",
                "message": "This organization has been suspended"
            }), 503
        
        # Rate limiting per tenant could be added here
        # API key validation could be added here
        # IP whitelisting could be added here


class CORSMiddleware:
    """CORS middleware with tenant-aware settings"""
    
    def __init__(self, app: Flask):
        self.app = app
        self.init_app(app)
    
    def init_app(self, app: Flask):
        """Initialize CORS middleware"""
        app.after_request(self.add_cors_headers)
    
    def add_cors_headers(self, response):
        """Add CORS headers based on tenant configuration"""
        context = get_current_tenant_context()
        
        # Default CORS settings
        allowed_origins = ['*']  # Be more restrictive in production
        
        # Tenant-specific CORS settings
        if context.tenant and context.organization:
            # Allow custom domain
            if context.organization.custom_domain:
                allowed_origins.append(f"https://{context.organization.custom_domain}")
            
            # Allow subdomain
            base_domain = self.app.config.get('BASE_DOMAIN', 'localhost')
            allowed_origins.append(f"https://{context.organization.slug}.{base_domain}")
        
        response.headers['Access-Control-Allow-Origin'] = ', '.join(allowed_origins)
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Tenant-ID'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        
        return response


def init_middleware(app: Flask):
    """Initialize all middleware"""
    # Order matters - tenant middleware should be first
    TenantMiddleware(app)
    SecurityMiddleware(app)
    CORSMiddleware(app)
    
    # Error handlers
    app.register_error_handler(404, lambda e: handle_tenant_not_found() if not get_current_tenant_context().tenant else e)