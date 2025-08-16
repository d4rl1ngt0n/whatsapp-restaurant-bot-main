# 🏢 Multi-Tenancy Implementation Guide

This document explains the comprehensive multi-tenancy architecture implemented for the WhatsApp Restaurant Bot, transforming it from a single-restaurant solution into an **enterprise-grade SaaS platform**.

## 🎯 Overview

The multi-tenancy implementation enables:
- **Restaurant Chains & Franchises**: Manage multiple locations under one organization
- **White-Label Solutions**: Custom branding per organization
- **Role-Based Access Control**: Granular permissions across tenants
- **Data Isolation**: Complete separation of tenant data
- **Scalable Architecture**: Support thousands of restaurants

## 🏗️ Architecture

### Multi-Tenant Data Model

```
Organization (Restaurant Chain)
├── Tenant (Individual Restaurant/Location)
│   ├── Users (Customers + Staff)
│   ├── Menu Items
│   ├── Orders
│   ├── Configuration
│   └── Branding Settings
├── Branding (Logo, Colors, Domain)
└── Billing & Plan Management
```

### Key Models

#### Organization
- **Purpose**: Top-level entity (restaurant chain/franchise)
- **Features**: Custom branding, billing, multi-location management
- **Plans**: Basic, Professional, Enterprise

#### Tenant
- **Purpose**: Individual restaurant location
- **Features**: Location-specific settings, WhatsApp config, payment setup
- **Isolation**: Complete data separation between tenants

#### User Roles
- `SUPER_ADMIN`: Platform administrator
- `TENANT_ADMIN`: Organization owner
- `MANAGER`: Restaurant manager
- `STAFF`: Restaurant staff
- `CUSTOMER`: End customer

## 🚀 Quick Start

### 1. Run Migration Script

```bash
# Migrate existing single-tenant setup to multi-tenant
cd whatsapp-bot
python scripts/migrate_to_multitenancy.py
```

### 2. Environment Variables

Add these to your `.env` file:

```env
# Multi-tenancy Settings
DEFAULT_ORG_NAME="Your Restaurant Chain"
DEFAULT_TENANT_NAME="Main Location" 
ADMIN_EMAIL="admin@yourrestaurant.com"
BASE_DOMAIN="yourdomain.com"

# Existing variables work the same way
META_PHONE_NUMBER_ID="your_phone_number_id"
META_ACCESS_TOKEN="your_access_token"
META_VERIFY_TOKEN="your_verify_token"
```

### 3. Access Methods

#### Subdomain Access
```
https://pizza-palace.yourdomain.com
https://burger-joint.yourdomain.com
```

#### Custom Domain
```
https://restaurant.com
```

#### API Header
```bash
curl -H "X-Tenant-ID: 1" https://api.yourdomain.com/orders
```

#### URL Parameter
```
https://yourdomain.com/admin?tenant_id=1
```

## 📱 WhatsApp Integration

### Tenant Resolution

The system automatically resolves tenants from:

1. **WhatsApp Phone Number ID**: Each tenant has unique WhatsApp credentials
2. **Custom Domain**: `restaurant.com` → Tenant
3. **Subdomain**: `pizza-palace.yourdomain.com` → Tenant
4. **API Headers**: `X-Tenant-ID: 1`

### Multi-Tenant Webhooks

```python
# Single webhook endpoint handles all tenants
@app.post("/webhook")
def webhook():
    # Automatically resolves tenant from phone_number_id
    tenant = resolve_tenant_from_request()
    if tenant:
        # Process message in tenant context
        process_message(tenant, message)
```

## 🎨 White-Label Features

### Organization Branding
- **Custom Logo**: Upload organization logo
- **Brand Colors**: Primary and secondary color themes
- **Custom Domain**: `restaurant.com` instead of subdomain
- **Brand Name**: Override organization name in UI

### Tenant Customization
- **Restaurant Name**: Location-specific naming
- **Currency & Language**: Per-location settings
- **WhatsApp Templates**: Custom welcome messages
- **Feature Flags**: Enable/disable features per tenant

### Admin Interface

The admin interface adapts to organization branding:

```html
<!-- Dynamic branding -->
<title>{{ organization.brand_name }} - Admin</title>
<style>
  :root {
    --primary-color: {{ organization.primary_color }};
    --secondary-color: {{ organization.secondary_color }};
  }
</style>
```

## 🔐 Security & Access Control

### Role-Based Permissions

```python
@require_role(UserRole.MANAGER, UserRole.TENANT_ADMIN)
def update_menu():
    # Only managers and admins can update menu
    pass

@require_tenant_admin
def billing_settings():
    # Only tenant admins can access billing
    pass
```

### Data Isolation

All database queries are automatically scoped to tenant:

```python
# Automatic tenant filtering
def get_orders():
    context = get_current_tenant_context()
    return filter_by_tenant(
        select(Order), 
        Order, 
        context.tenant_id
    )
```

### Security Middleware

- **Tenant Validation**: Ensures tenant is active
- **CORS Management**: Tenant-specific CORS policies
- **Rate Limiting**: Per-tenant rate limits
- **Audit Logging**: Track all tenant actions

## 📊 Admin Dashboard Features

### Multi-Tenant Dashboard
- **Tenant Selector**: Switch between locations
- **Real-Time Analytics**: Per-tenant metrics
- **Order Management**: Location-specific orders
- **Menu Management**: Tenant-scoped menu items
- **Customer Management**: Tenant customer base
- **Settings**: Tenant-specific configuration
- **Branding**: Organization-level customization
- **Organization Management**: Multi-location overview

### Analytics & Reporting
- **Per-Tenant Metrics**: Orders, revenue, customers
- **Organization Summary**: Aggregate across locations
- **Performance Comparison**: Compare tenant performance
- **Customer Insights**: Tenant-specific customer analytics

## 🔧 API Endpoints

### Tenant Management

```bash
# Get tenant info
GET /api/tenant/{tenant_id}

# Update tenant settings
PUT /api/tenant/{tenant_id}/settings

# Get tenant statistics
GET /api/tenant/{tenant_id}/stats
```

### Organization Management

```bash
# Get organization info
GET /api/organization

# Update branding
PUT /api/organization/branding

# List all tenants
GET /api/organization/tenants

# Create new tenant
POST /api/organization/tenants
```

### Tenant-Scoped Resources

All existing endpoints automatically work with tenant context:

```bash
# Automatically scoped to current tenant
GET /orders
GET /menu
GET /customers
POST /orders/update-status
```

## 🛠️ Development Guide

### Creating New Tenant-Aware Features

1. **Add Tenant ID to Model**:
```python
class NewModel(Base):
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
```

2. **Use Tenant Context**:
```python
from app.services.tenant import get_current_tenant

def my_function():
    tenant = get_current_tenant()
    # Use tenant.id for filtering
```

3. **Apply Tenant Filtering**:
```python
from app.services.tenant import filter_by_tenant

def get_tenant_data():
    query = select(MyModel)
    return filter_by_tenant(query, MyModel)
```

### Testing Multi-Tenancy

```python
# Test with tenant context
def test_tenant_isolation():
    with tenant_context(tenant_id=1):
        orders_t1 = get_orders()
    
    with tenant_context(tenant_id=2):
        orders_t2 = get_orders()
    
    # Ensure no overlap
    assert not set(orders_t1) & set(orders_t2)
```

## 📦 Deployment

### Docker Deployment

The existing Docker setup works with multi-tenancy:

```bash
# Build and deploy
docker compose up --build -d

# Run migration
docker exec whatsapp-bot python scripts/migrate_to_multitenancy.py
```

### Environment Configuration

Each tenant can have different configurations:

```yaml
# docker-compose.yml
version: '3.8'
services:
  app:
    environment:
      - BASE_DOMAIN=yourdomain.com
      - DEFAULT_ORG_NAME=Restaurant Chain
```

### Scaling Considerations

- **Database**: Use read replicas for tenant queries
- **Caching**: Redis with tenant-prefixed keys
- **Load Balancing**: Route by subdomain/domain
- **Monitoring**: Per-tenant metrics and alerts

## 🌐 White-Label SaaS Setup

### 1. Organization Setup
```python
# Create new organization
org = TenantService.create_organization(
    name="Pizza Palace Chain",
    slug="pizza-palace",
    contact_email="admin@pizzapalace.com",
    plan="professional"
)
```

### 2. Tenant Creation
```python
# Add locations
tenant = TenantService.create_tenant(
    organization_id=org.id,
    name="Downtown Location",
    slug="downtown",
    currency="USD"
)
```

### 3. Branding Configuration
```python
# Set custom branding
org.brand_name = "Pizza Palace"
org.logo_url = "https://cdn.pizzapalace.com/logo.png"
org.primary_color = "#e74c3c"
org.custom_domain = "order.pizzapalace.com"
```

### 4. WhatsApp Configuration
```python
# Per-tenant WhatsApp setup
tenant.wa_phone_number_id = "123456789"
tenant.wa_access_token = "tenant_specific_token"
tenant.wa_webhook_verify_token = "tenant_verify_token"
```

## 📈 Business Models

### 1. SaaS Platform
- **Monthly Subscriptions**: Per tenant pricing
- **Feature Tiers**: Basic, Professional, Enterprise
- **Usage-Based**: Per order or message pricing

### 2. White-Label Licensing
- **One-Time License**: Custom branding rights
- **Revenue Sharing**: Percentage of tenant revenue
- **Enterprise Contracts**: Custom terms and features

### 3. Franchise Management
- **Franchise Fee**: Setup cost per location
- **Ongoing Fees**: Monthly management fees
- **Marketing Fees**: Shared marketing costs

## 🔍 Monitoring & Analytics

### Tenant Metrics
- **Order Volume**: Orders per tenant per day
- **Revenue Tracking**: Revenue per tenant
- **Customer Growth**: New customers per tenant
- **Feature Usage**: Which features are used most

### Platform Metrics
- **Total Tenants**: Active tenant count
- **System Performance**: Response times per tenant
- **Error Rates**: Errors by tenant
- **Resource Usage**: CPU/Memory per tenant

## 🚨 Troubleshooting

### Common Issues

1. **Tenant Not Resolved**
   - Check subdomain/domain configuration
   - Verify tenant is active
   - Check WhatsApp phone number mapping

2. **Permission Denied**
   - Verify user role assignments
   - Check tenant membership
   - Validate organization access

3. **Data Isolation Issues**
   - Ensure all queries use tenant filtering
   - Check middleware configuration
   - Verify database constraints

### Debug Mode

Enable debug headers to see tenant resolution:

```python
# In development
app.debug = True
# Adds X-Tenant-ID and X-Tenant-Name headers
```

## 🎯 Next Steps

The multi-tenancy foundation enables these advanced features:

1. **API Marketplace**: Third-party integrations per tenant
2. **Advanced Analytics**: ML-driven insights per tenant
3. **Mobile Apps**: White-label mobile apps
4. **Voice Integration**: Tenant-specific voice assistants
5. **IoT Integration**: Kitchen displays, POS systems
6. **International Expansion**: Multi-currency, multi-language
7. **Compliance**: GDPR, PCI-DSS per region

## 📞 Support

For multi-tenancy support:
- **Documentation**: See inline code comments
- **Migration Issues**: Check `scripts/migrate_to_multitenancy.py`
- **Configuration**: Review tenant and organization models
- **Custom Development**: Extend tenant services

---

**🎉 Congratulations!** You now have an enterprise-grade, multi-tenant WhatsApp Restaurant Bot platform that can scale to serve thousands of restaurants with complete data isolation, custom branding, and advanced role-based access control.