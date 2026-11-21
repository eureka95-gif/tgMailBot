# Troubleshooting

## Mail does not arrive

Check in order — stop at the first failure:

1. **DNS** — see `docs/DNS.md`. Run `dig MX YOUR_DOMAIN +short` — it must print `10 mail.YOUR_DOMAIN.`
2. **Receiver running?**
   ```bash
   sudo systemctl status tempmail-receiver --no-pager
   sudo ss -tlnp | grep :25
   ```
   You must see a Python process listening on `0.0.0.0:25`. If not, check `sudo journalctl -u tempmail-receiver -n 30 --no-pager`.
   If something else is on port 25 (usually Postfix), stop it first: `sudo systemctl stop postfix; sudo systemctl disable postfix`, then restart the receiver.
3. **Port 25 blocked?** Many VPS providers block inbound 25 by default (Oracle Cloud, AWS, etc.).
   Check the provider firewall / security list for inbound TCP 25, and on the VPS: `sudo ufw allow 25/tcp`.
   Test from outside: `telnet mail.YOUR_DOMAIN 25` — you should get a `220` greeting. If it times out, the port is blocked upstream.
4. **Sender rejected?** Gmail etc. may delay mail from a brand-new VPS IP with no reputation. Wait 10 min, check spam / sender's bounce message, and confirm SPF is set (`v=spf1 mx -all`).

## Bot does not reply

```bash
sudo systemctl status tempmail-bot --no-pager
sudo journalctl -u tempmail-bot -n 30 --no-pager
```

- `TEMPMAIL_BOT_TOKEN not set` → token missing from `/etc/tempmail.env`. See `docs/TELEGRAM.md`.
- `401 Unauthorized` from Telegram → token is wrong / revoked. Make a new one in @BotFather and update `/etc/tempmail.env`.
- Bot replies to `/start` but never pushes mail → you did not create that address with `/new`. Use `/inbox <address>` to check it manually, or run `/new <name>` for that name first.

## Nginx failed to start (only if you use nginx)

This project does **not** need nginx — the bot + receiver are enough. If you run nginx for something else and it fails:

- `bind() to 0.0.0.0:888 failed (Address already in use)` → something else (e.g. tinyproxy) is on port 888. Stop it or move nginx's listener.
- `mkdir() "/dev/shm/nginx-cache/wp" failed` → that cache dir is wiped on reboot. Recreate it: `sudo mkdir -p /dev/shm/nginx-cache/wp && sudo chown www:www /dev/shm/nginx-cache/wp`, then restart nginx.
- `nginx -t` as a non-root user gives permission denied on the log/pid — run it with `sudo nginx -t`.

## "Email domain could not be verified" on GitHub

That is GitHub rejecting the *sender* domain you tried to sign up with (e.g. a disposable domain), not this server. Use an address on your own domain from this server — e.g. `/new github123` — GitHub accepts it if the MX + A records above are set.

## Mail is in the DB but the bot shows nothing

```bash
sudo sqlite3 /var/lib/tempmail/mail.db "SELECT id, to_addr, subject, code, received_at FROM mails ORDER BY id DESC LIMIT 5;"
```

If rows are there, the receiver works and the problem is the bot's active address. Run `/new <name>` for that exact address in Telegram, then `/inbox <address>`.
