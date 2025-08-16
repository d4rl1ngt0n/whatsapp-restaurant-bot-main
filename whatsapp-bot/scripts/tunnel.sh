#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")"/.. && pwd)"
cd "$ROOT_DIR"

if [[ -f .env ]]; then
	set -a
	# shellcheck disable=SC1091
	source .env || true
	set +a
fi

if ! command -v ngrok >/dev/null 2>&1; then
	echo "ngrok is required. Install from https://ngrok.com/download" >&2
	exit 1
fi

if ! curl -sS http://127.0.0.1:4040/api/tunnels >/dev/null 2>&1; then
	echo "Starting ngrok on port 8081..."
	nohup ngrok http 8081 >/tmp/ngrok.log 2>&1 &
	for i in {1..30}; do
		sleep 1
		if curl -sS http://127.0.0.1:4040/api/tunnels >/dev/null 2>&1; then
			break
		fi
	done
fi

TUNNELS_JSON="$(curl -sS http://127.0.0.1:4040/api/tunnels || echo '{}')"
PUBLIC_URL=$(echo "$TUNNELS_JSON" | sed -n 's/.*"public_url":"\(https:\/\/[^\"]*\)".*/\1/p' | head -n1)

if [[ -z "${PUBLIC_URL:-}" ]]; then
	echo "Failed to determine ngrok public URL. Check /tmp/ngrok.log" >&2
	exit 1
fi

echo "Public URL: $PUBLIC_URL"

VERIFY_TOKEN="${META_VERIFY_TOKEN:-change-me-verify}"
CHALLENGE_TOKEN="123456"

echo "Verification curl:"
echo "curl -sS \"$PUBLIC_URL/webhook?hub.mode=subscribe&hub.verify_token=$VERIFY_TOKEN&hub.challenge=$CHALLENGE_TOKEN\""

echo -e "Meta config:\n- Callback URL: $PUBLIC_URL/webhook\n- Verify Token: $VERIFY_TOKEN"
