#!/bin/bash
# Temp Mail Server — interactive setup wizard
# Run on your Ubuntu / Debian VPS as root (or with sudo):
#   sudo bash setup.sh
# It asks 3 questions, then installs everything. No token is saved in this repo.
# Flags: --help, --dry-run (print what it would do, install nothing)
set -e

if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
  cat <<'EOF'
Temp Mail Server — setup wizard

Usage:
  sudo bash setup.sh            # interactive prompts
  sudo bash setup.sh --dry-run  # show the plan, install nothing

What it asks:
  1. Domain          e.g. your-domain.com
  2. VPS public IP   auto-detected, press Enter to accept
  3. Telegram bot token  from @BotFather (hidden input, never printed)
  4. Your Telegram chat id (optional, recommended) — locks the bot to you only.
     Get it by sending /start to your bot first. Press Enter to leave the bot open.

What it installs:
  - SMTP receiver on port 25 (catch-all @your-domain, SQLite, 24h expiry)
  - Telegram bot ( /new [name], /inbox, /code, /mail )
  - systemd services: tempmail-receiver + tempmail-bot

Before you run it, set DNS first — see docs/DNS.md (takes 5 min).
After it runs, test with: /new github123 in Telegram, then mail that address from Gmail.
EOF
  exit 0
fi

DRY_RUN=0
[ "$1" = "--dry-run" ] && DRY_RUN=1

echo "=== Temp Mail Server — setup ==="
echo ""

# 1. Domain
read -rp "Your domain (e.g. your-domain.com): " DOMAIN
DOMAIN="${DOMAIN,,}"
DOMAIN="${DOMAIN#https://}"; DOMAIN="${DOMAIN#http://}"; DOMAIN="${DOMAIN%/}"
if ! echo "$DOMAIN" | grep -Eq '^[a-z0-9][a-z0-9.-]+\.[a-z]{2,}$'; then
  echo "ERROR: '$DOMAIN' does not look like a domain. Example: your-domain.com"
  exit 1
fi

# 2. VPS IP — auto-detect, allow override
DETECTED_IP="$(curl -s --max-time 10 https://ifconfig.me 2>/dev/null || true)"
if [ -n "$DETECTED_IP" ]; then
  read -rp "VPS public IP [$DETECTED_IP]: " VPS_IP
  VPS_IP="${VPS_IP:-$DETECTED_IP}"
else
  read -rp "VPS public IP: " VPS_IP
fi
if ! echo "$VPS_IP" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "ERROR: '$VPS_IP' does not look like an IPv4 address."
  exit 1
fi

# 3. Bot token — hidden, validated by shape only (digits:letters)
read -rsp "Telegram bot token from @BotFather (hidden, paste it): " BOT_TOKEN
echo ""
if ! echo "$BOT_TOKEN" | grep -Eq '^[0-9]+:[A-Za-z0-9_-]{30,}$'; then
  echo "WARNING: that token does not look like a Telegram bot token (digits:long-string)."
  read -rp "Continue anyway? [y/N] " yn
  case "$yn" in [yY]*) ;; *) echo "Aborted."; exit 1;; esac
fi

# 4. Owner chat id — optional, locks the bot to you only
read -rp "Your Telegram chat id (optional, from /start — Enter to leave bot open): " OWNER_CHAT_ID
if [ -n "$OWNER_CHAT_ID" ] && ! echo "$OWNER_CHAT_ID" | grep -Eq '^[0-9]+$'; then
  echo "WARNING: '$OWNER_CHAT_ID' is not a numeric chat id — ignoring it (bot will stay open)."
  OWNER_CHAT_ID=""
fi

echo ""
echo "Plan:"
echo "  Domain:   @$DOMAIN"
echo "  VPS IP:   $VPS_IP"
echo "  Bot:      Telegram (token hidden, not printed)"
if [ -n "$OWNER_CHAT_ID" ]; then echo "  Owner:    $OWNER_CHAT_ID (bot is private to you)"; else echo "  Owner:    (not set — bot will be OPEN to anyone)"; fi
echo "  DNS needed:"
echo "    A     mail  -> $VPS_IP"
echo "    MX    @     10 mail.$DOMAIN."
echo "    TXT   @     \"v=spf1 mx -all\""
echo ""
if [ "$DRY_RUN" = "1" ]; then
  echo "[dry-run] Would run: DOMAIN=$DOMAIN VPS_IP=$VPS_IP BOT_TOKEN=<hidden> OWNER_CHAT_ID=${OWNER_CHAT_ID:-<none>} bash install.sh"
  echo "[dry-run] Nothing installed."
  exit 0
fi
read -rp "Install now? [Y/n] " yn
case "$yn" in [nN]*) echo "Aborted."; exit 0;; *) ;; esac

export DOMAIN VPS_IP BOT_TOKEN OWNER_CHAT_ID
bash "$(dirname "$0")/install.sh"

echo ""
echo "=== Done ==="
echo "In Telegram, send /new to your bot, then /new github123 for a custom address."
echo "Test: mail that address from Gmail — the bot should message you the code."
echo "If mail does not arrive, see docs/TROUBLESHOOTING.md"
