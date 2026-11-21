# DNS setup guide

You need 3 DNS records for your domain. Replace `YOUR_DOMAIN`
with your domain and `YOUR_VPS_IP` with your VPS public IP.
Do this **before** running `setup.sh` — mail will not arrive until DNS propagates (5–30 min).

## The 3 records

| Type | Name / Host | Value | Priority / TTL |
|------|-------------|-------|----------------|
| A | `mail` | `YOUR_VPS_IP` | TTL Auto / 300 |
| MX | `@` (or blank) | `mail.YOUR_DOMAIN.` | Priority 10 |
| TXT | `@` (or blank) | `v=spf1 mx -all` | TTL Auto / 300 |

Example for `your-domain.com` on `1.2.3.4`:

```
A    mail  1.2.3.4
MX   @     10 mail.your-domain.com.
TXT  @     "v=spf1 mx -all"
```

Notes:
- The MX value must end with a dot in some panels (`mail.your-domain.com.`) — the panel usually adds it.
- Do **not** put the MX on `mail` itself — it goes on `@` (the bare domain).
- Do **not** enable Cloudflare proxy (orange cloud) on the `mail` A record — it must be **DNS only** (grey cloud). Mail cannot go through the Cloudflare proxy.
- The wildcard `*.YOUR_DOMAIN` A record is optional — it is not needed for mail.

## Cloudflare (step by step)

1. Open Cloudflare → your domain → **DNS** → **Records**.
2. **Add record** → Type **A**, Name `mail`, IPv4 address `YOUR_VPS_IP`, Proxy status **DNS only**, Save.
3. **Add record** → Type **MX**, Name `@`, Mail server `mail.YOUR_DOMAIN`, Priority `10`, Save.
4. **Add record** → Type **TXT**, Name `@`, Content `v=spf1 mx -all`, Save.
5. Wait 5–30 min.

## GoDaddy / Namecheap / other registrars

Same 3 records, same values. The field names differ slightly:
- **Host** = `mail` for the A record, `@` for MX/TXT.
- **Points to / Value** = your VPS IP (A), `mail.YOUR_DOMAIN` (MX), `v=spf1 mx -all` (TXT).
- **Priority** = `10` for the MX record.
- **TTL** = leave on Auto / 300 / 1 hour — any is fine.

## Check it worked

From your VPS (or any terminal):

```bash
dig MX YOUR_DOMAIN +short
# should print: 10 mail.YOUR_DOMAIN.

dig A mail.YOUR_DOMAIN +short
# should print: YOUR_VPS_IP

dig TXT YOUR_DOMAIN +short
# should print: "v=spf1 mx -all"
```

If `dig` returns nothing, DNS has not propagated yet — wait and try again.
You can also check at https://mxtoolbox.com/mx/YOUR_DOMAIN

## Common mistakes

- **MX points to the bare domain instead of `mail.`** — mail will go nowhere.
- **Cloudflare proxy on for `mail`** — turn proxy off (DNS only).
- **No A record for `mail`** — the MX name must resolve to your VPS IP.
- **Port 25 blocked** — this is not DNS, but it looks like DNS. See `docs/TROUBLESHOOTING.md`. Check your VPS provider's firewall / security list allows inbound TCP 25, and `ufw allow 25/tcp` on the VPS.
