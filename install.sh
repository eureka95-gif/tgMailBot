#!/bin/bash
# Install temp mail server for your-domain.com on Ubuntu / Debian VPS.
# TELEGRAM BOT ONLY for now — no web inbox.
# Run as root:  sudo bash install.sh
# Usage: sudo DOMAIN=your-domain.com VPS_IP=1.2.3.4 BOT_TOKEN=123:ABC OWNER_CHAT_ID=123456789 bash install.sh
# BOT_TOKEN: get it from @BotFather in Telegram. Do NOT put it in chat.
# OWNER_CHAT_ID: your Telegram chat id from /start — locks the bot to you only.
#   If not passed, the bot is OPEN until you add TEMPMAIL_OWNER_CHAT_ID to /etc/tempmail.env.
# If BOT_TOKEN is not passed here, put it in /etc/tempmail.env later and restart the bot.
set -e
DOMAIN="${DOMAIN:-your-domain.com}"
VPS_IP="${VPS_IP:-}"
BOT_TOKEN="${BOT_TOKEN:-}"
OWNER_CHAT_ID="${OWNER_CHAT_ID:-}"
APP_DIR="/opt/tempmail"
DATA_DIR="/var/lib/tempmail"

echo "== Temp mail (Telegram bot) for @$DOMAIN =="
apt-get update -y
apt-get install -y python3 python3-pip python3-venv ufw curl

id -u tempmail >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin -d "$APP_DIR" tempmail
mkdir -p "$APP_DIR" "$DATA_DIR"
cp receiver.py bot.py tempmail_common.py requirements.txt "$APP_DIR/"
# web.py is kept in the folder but NOT installed / NOT run for now.
chown -R tempmail:tempmail "$APP_DIR" "$DATA_DIR"
chmod 755 "$APP_DIR"

python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

# Bot token + owner file — root-only, never in git / chat
if [ -n "$BOT_TOKEN" ]; then
  printf 'TEMPMAIL_BOT_TOKEN=%s\n' "$BOT_TOKEN" > /etc/tempmail.env
  echo "Bot token saved to /etc/tempmail.env"
else
  echo "No BOT_TOKEN passed. Create /etc/tempmail.env with:"
  echo "  TEMPMAIL_BOT_TOKEN=123:ABC"
  echo "then: sudo systemctl restart tempmail-bot"
  touch /etc/tempmail.env
fi
if [ -n "$OWNER_CHAT_ID" ]; then
  # replace any old owner line, then append the new one
  grep -v '^TEMPMAIL_OWNER_CHAT_ID=' /etc/tempmail.env > /tmp/tempmail.env.tmp 2>/dev/null || true
  mv /tmp/tempmail.env.tmp /etc/tempmail.env
  printf 'TEMPMAIL_OWNER_CHAT_ID=%s\n' "$OWNER_CHAT_ID" >> /etc/tempmail.env
  echo "Owner chat id $OWNER_CHAT_ID saved — bot is private to you."
else
  echo "No OWNER_CHAT_ID passed — bot is OPEN until you add TEMPMAIL_OWNER_CHAT_ID to /etc/tempmail.env"
fi
chmod 600 /etc/tempmail.env

cat > /etc/systemd/system/tempmail-receiver.service <<EOF
[Unit]
Description=Temp mail SMTP receiver for @$DOMAIN
After=network.target
[Service]
User=root
WorkingDirectory=$APP_DIR
Environment=TEMPMAIL_DOMAIN=$DOMAIN
Environment=TEMPMAIL_DB=$DATA_DIR/mail.db
ExecStart=$APP_DIR/venv/bin/python3 $APP_DIR/receiver.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/tempmail-bot.service <<EOF
[Unit]
Description=Temp mail Telegram bot for @$DOMAIN
After=network.target tempmail-receiver.service
[Service]
User=tempmail
WorkingDirectory=$APP_DIR
EnvironmentFile=/etc/tempmail.env
Environment=TEMPMAIL_DOMAIN=$DOMAIN
Environment=TEMPMAIL_DB=$DATA_DIR/mail.db
Environment=TEMPMAIL_BOT_STATE=$DATA_DIR/bot_state.json
Environment=TEMPMAIL_NOTIFY_STATE=$DATA_DIR/notified.json
Environment=TEMPMAIL_USERS_DIR=$DATA_DIR/users
Environment=TEMPMAIL_ACCESS_STATE=$DATA_DIR/access.json
ExecStart=$APP_DIR/venv/bin/python3 $APP_DIR/bot.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now tempmail-receiver tempmail-bot
ufw allow 25/tcp || true

echo ""
echo "== Done =="
systemctl status tempmail-receiver --no-pager -l | head -15 || true
systemctl status tempmail-bot --no-pager -l | head -15 || true
echo ""
echo "In Telegram, open your bot and send /new — you get an address like gh-a1b2c3@$DOMAIN"
echo "Test: send a mail from Gmail to that address, the bot should message you the code."
echo ""
echo "DNS still needed (see README.md):"
echo "  MX  @  10 mail.$DOMAIN."
echo "  A   mail  -> $VPS_IP"
echo "  TXT @  \"v=spf1 mx -all\""
