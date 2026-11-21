# Telegram bot guide

## 0. Who can use the bot? (private by choice)

By default the bot is **open** — anyone who finds it can use `/new`.
To lock it down to only you (recommended — do not give it away for free):

1. Send `/start` to your bot — it shows `Your chat id: 123456789`. Copy that number.
2. On the VPS, add it to `/etc/tempmail.env`:
   ```bash
   echo 'TEMPMAIL_OWNER_CHAT_ID=123456789' | sudo tee -a /etc/tempmail.env
   sudo systemctl restart tempmail-bot
   ```
   Or set it during `setup.sh` — it asks for your chat id (optional).
3. Now only you can use the bot. Anyone else gets:
   `Access denied. This bot is private. Your chat id is ... — send it to the owner to request access.`

To let someone else in, you (the owner) send:
```
/allow 987654321
```
To remove them: `/revoke 987654321`
To see who is allowed: `/users`

You can also seed a list in `/etc/tempmail.env`:
```
TEMPMAIL_ALLOWED_CHAT_IDS=111,222,333
```

If no owner / allow-list is set, the bot stays open. Set an owner to lock it down.

## 0b. Your mail is yours only

Every address you create with `/new` is linked to your Telegram chat id.
Only you can read its mail — with `/inbox`, `/code`, or `/mail <id>`.

Another allowed user cannot read your mail, even if they guess the address
or the mail id:
- `/inbox your-address@...` → "That address belongs to another user."
- `/mail <your-mail-id>` → "Mail not found or not yours."

That means: **always create the address with `/new` first**, then use it in the
signup form. An address that was never created with `/new` cannot be read
through the bot at all. Push notifications also go only to the chat that
created the address.

### How it is stored — `users/<chat_id>.json`

Each user gets their own file on the VPS, at `/var/lib/tempmail/users/<chat_id>.json`:

```json
{
  "chat_id": 111,
  "active": "private111@your-domain.com",
  "owned": ["gh-a1b2c3@your-domain.com", "private111@your-domain.com"],
  "mail_ids": [3, 7, 12]
}
```

- `owned` — addresses that chat created with `/new`
- `mail_ids` — mail ids that arrived for those addresses (added by the watcher when mail arrives, and when you read `/inbox` / `/mail`)

`/mail <id>` checks: is this id in *your* file? If not, it is denied — even if the mail exists in the database. No other user's file contains that id, so no other user can open it.

## 1. Make the bot (2 minutes)

1. In Telegram, open **@BotFather**.
2. Send `/newbot`, follow the prompts (pick a name + a username ending in `bot`).
3. Copy the token BotFather gives you. It looks like `1234567890:AAE...`.
4. **Do not paste the token in chat, in a GitHub issue, or in any file you commit.** It goes only in `/etc/tempmail.env` on your VPS (created by `setup.sh` / `install.sh`, mode 600).

If the token ever leaks, revoke it: in @BotFather send `/revoke`, pick your bot, copy the new token, update `/etc/tempmail.env`, then `sudo systemctl restart tempmail-bot`.

## 2. Commands

```
/start            hello + your chat id
/new              random address, e.g. gh-a1b2c3@your-domain.com
/new <name>       custom address, e.g. /new github123
/inbox [address]  last mails — all your addresses if no address given
/code [address]   latest verification code — across all your addresses if no address given
/mail <id>        full mail text (id from /inbox)
/addresses       list all your addresses
/help             this list
```

**All your addresses stay active.** Creating a new address with `/new` does
NOT deactivate your older ones — `/inbox` with no address shows mail from
all of them, newest first, and push notifications arrive for all of them.
Use `/inbox <address>` only when you want one specific address.

Custom names: 2–32 chars, letters / digits / `.` `-` `_`, starting with a letter or digit.
Examples that work: `/new github123`, `/new myshop`, `/new MyShop@your-domain.com` (lowercased).
Examples that fail: `/new a` (too short), `/new bad name` (space), `/new bad!name`.

## 3. How push works

When you run `/new <name>`, the bot remembers that address as *your* active address.
When mail arrives for it, the bot messages you immediately with from / subject / code.

If you use an address you did **not** create with `/new` (e.g. you just typed it into a signup form), the receiver still saves it — it is catch-all — but the bot will not know to push it to you. Check it manually with:

```
/inbox that-address@your-domain.com
/code that-address@your-domain.com
```

## 4. Check the bot is running

On the VPS:

```bash
sudo systemctl status tempmail-bot --no-pager
sudo journalctl -u tempmail-bot -n 30 --no-pager
sudo systemctl status tempmail-receiver --no-pager
```

`tempmail-bot` should say `active (running)`. If it says `activating (auto-restart)` with `TEMPMAIL_BOT_TOKEN not set`, the token is missing from `/etc/tempmail.env` — add it and restart:

```bash
echo 'TEMPMAIL_BOT_TOKEN=YOUR_TOKEN' | sudo tee /etc/tempmail.env
sudo chmod 600 /etc/tempmail.env
sudo systemctl restart tempmail-bot
```
