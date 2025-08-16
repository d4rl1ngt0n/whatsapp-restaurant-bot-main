## WhatsApp Restaurant Bot (Phase 1)

One-command Dockerized Flask app exposing a WhatsApp Cloud API webhook with health check, verification, and minimal echo.

### Quick start

1. Copy `.env.example` to `.env` and fill values.

```bash
cp .env.example .env
```

Required at minimum:
- `META_VERIFY_TOKEN`
- `META_ACCESS_TOKEN`
- `META_PHONE_NUMBER_ID`

2. Build and run:

```bash
docker compose up --build -d
```

3. Verify health locally:

```bash
curl -sS http://localhost:8081/health
```

4. Start ngrok and get the public URL + verification curl:

```bash
scripts/tunnel.sh
```

Use the printed public URL in Meta App config:
- Callback URL: `<PUBLIC_URL>/webhook`
- Verify Token: the value of `META_VERIFY_TOKEN`
- Subscribe to messages

5. Send a WhatsApp message to your test number. The bot will echo your message.

### Endpoints
- `GET /health` → `{status, timestamp, version}`
- `GET /webhook` → WhatsApp verification (returns the `hub.challenge` when token matches)
- `POST /webhook` → Receives messages and echoes back via WhatsApp Cloud API

### Ports
- Container port: `8080`
- Host mapping: `8081`

### Notes
- No secrets are printed in logs.
- Minimal in-memory idempotency for message ids is added in later phases.

### Payments
- Providers: Stripe (default) or Paystack
- Select via env: `PAYMENT_PROVIDER=stripe|paystack`
- Stripe env:
  - `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET`, optional `STRIPE_PUBLISHABLE_KEY`
- Paystack env:
  - `PAYSTACK_SECRET_KEY`, `PAYSTACK_PUBLIC_KEY`
  - Set webhook to: `<PUBLIC_URL>/payments/paystack/webhook`
