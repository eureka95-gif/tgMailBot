# Temp Mail Server

A simple, inbound-only temp mail server on **your own domain + your own VPS**, with a Telegram bot.

Any address works — `anything@your-domain.com` — mail is kept 24 hours, then deleted. No web inbox needed, no Postfix needed, no third-party temp mail service.

## What you get

- **Telegram bot** — `/new [name]` makes an address, the bot messages you the verification code when mail arrives
- **SMTP receiver** — catch-all on port 25, saves to SQLite, extracts 6-digit codes
- **Custom addresses** — `/new github123` → `github123@your-domain.com`, or `/new` alone for a random one
- **Private by choice** — set your Telegram chat id as owner, only you (and people you `/allow`) can use the bot
- **Easy setup** — one interactive prompt, `setup.sh` asks 3 questions and installs everything

## Quick start (5 minutes + DNS)

### 1. Set DNS first — see [docs/DNS.md](docs/DNS.md)

You need 3 records (replace with your domain / VPS IP):

```
A    mail  YOUR_VPS_IP
MX   @     10 mail.YOUR_DOMAIN.
TXT  @     "v=spf1 mx -all"
```

The `mail` A record must be **DNS only** (no Cloudflare proxy). Wait 5–30 min for propagation.

### 2. Make a Telegram bot

In Telegram, open **@BotFather** → `/newbot` → copy the token. See [docs/TELEGRAM.md](docs/TELEGRAM.md). Do not paste the token in chat or commit it.

### 3. Install on your VPS (Ubuntu / Debian, as root)

```bash
git clone https://github.com/eureka95-gif/temp-mail-server.git
cd temp-mail-server
sudo bash setup.sh
```

`setup.sh` asks for:
1. Your domain — e.g. `your-domain.com`
2. Your VPS public IP — auto-detected, press Enter to accept
3. Your Telegram bot token — hidden input

Or non-interactive, if you prefer:

```bash
sudo DOMAIN=your-domain.com VPS_IP=1.2.3.4 BOT_TOKEN=YOUR_TOKEN bash install.sh
```

### 4. Test it

In Telegram, send `/new github123` to your bot, then mail that address from Gmail. The bot should message you the code.

## Bot commands

```
/new              random address, e.g. gh-a1b2c3@your-domain.com
/new <name>       custom address, e.g. /new github123
/inbox [address]  last mails — all your addresses if no address given
/code [address]   latest verification code
/mail <id>        full mail text
/addresses       list all your addresses
/start, /help
```

All your addresses stay active — making a new one with `/new` does not deactivate the older ones.

## Project layout

```
setup.sh              interactive installer (asks domain, IP, token)
install.sh            non-interactive installer (called by setup.sh)
receiver.py           SMTP catch-all on port 25
bot.py                Telegram bot (stdlib only)
tempmail_common.py    SQLite storage + code extraction
requirements.txt      aiosmtpd only
web.py                optional web inbox (not installed by default)
nginx.conf            optional reverse proxy for the web inbox
docs/DNS.md           DNS setup, Cloudflare + generic, with checks
docs/TELEGRAM.md      BotFather + bot commands + push explained
docs/TROUBLESHOOTING.md  mail not arriving, bot not replying, nginx, port 25
tests/                local tests (mock mail + mock bot)
```

## Limits — read this

- **Inbound only.** This does not send mail.
- **Port 25 must be open inbound.** Check your VPS provider firewall / security list, and `ufw allow 25/tcp` on the VPS. If another mail server (Postfix) is already on port 25, stop it first — see `docs/TROUBLESHOOTING.md`.
- **New VPS IPs have no reputation** — Gmail may delay the first mails. SPF (above) helps.
- **Bot token is a secret** — keep it in `/etc/tempmail.env` (mode 600) only. If it leaks, revoke it in @BotFather.
- **Private by design** — the bot only pushes mail for addresses you created with `/new`. Anyone can still *send* to any address (that's catch-all temp mail).

## Tested

- Receiver + web inbox: mock GitHub mail, code extraction, other-domain rejection — passed
- Bot: `/new`, `/new <name>`, `/code`, `/inbox`, `/mail`, invalid names — passed
- Live: Ubuntu 22.04 VPS, domain `your-domain.com`, GitHub signup code received via the bot and account created — worked end-to-end

## License

MIT — see [LICENSE](LICENSE).
