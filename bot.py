#!/usr/bin/env python3
"""Telegram bot for your-domain.com temp mail. Web inbox NOT used for now.

Commands (in Telegram):
  /start            - hello + your chat id + domain
  /new [name]       - make an address: /new alone = random gh-a1b2c3@your-domain.com,
                      /new github123 = github123@your-domain.com (custom name)
  /inbox [address]  - last mails (all your addresses if no address given —
                      every address you created stays active, not just the last /new)
  /code [address]   - latest verification code (across all your addresses if no address given)
  /mail <id>        - full mail text
  /addresses        - list all your addresses
  /help             - this list
  /allow <chat_id>  - owner only: allow a user (see ACCESS below)
  /revoke <chat_id> - owner only: remove a user
  /users            - owner only: list allowed users

ACCESS — private bot (not free for everyone):
  Set TEMPMAIL_OWNER_CHAT_ID to your Telegram chat id (shown by /start)
  in /etc/tempmail.env, e.g. TEMPMAIL_OWNER_CHAT_ID=123456789
  Then only you can use the bot. Use /allow <chat_id> to add others,
  /revoke <chat_id> to remove them. You can also seed a list with
  TEMPMAIL_ALLOWED_CHAT_IDS=111,222 (comma-separated).
  If no owner / allow-list is set, the bot is OPEN to anyone — set an
  owner to lock it down. See docs/TELEGRAM.md.

Plus push: when the SMTP receiver saves a new mail for an address
you created with /new, the bot messages you immediately with
from / subject / code. Mail auto-deletes after 24h (see tempmail_common).

Setup: get a token from @BotFather, then run with:
  TEMPMAIL_BOT_TOKEN=123:ABC TEMPMAIL_DOMAIN=your-domain.com \
  TEMPMAIL_DB=/var/lib/tempmail/mail.db python3 bot.py
No token in the file — pass it via env / systemd EnvironmentFile.
Only stdlib is used (urllib), no python-telegram-bot needed.
"""
import json
import os
import random
import re
import string
import sys
import threading
import time
import urllib.request
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tempmail_common import DOMAIN, DB_PATH, list_mails, get_mail

TOKEN = os.environ.get("TEMPMAIL_BOT_TOKEN", "")
API = f"https://api.telegram.org/bot{TOKEN}" if TOKEN else ""
STATE_PATH = os.environ.get("TEMPMAIL_BOT_STATE", "/var/lib/tempmail/bot_state.json")
NOTIFY_PATH = os.environ.get("TEMPMAIL_NOTIFY_STATE", "/var/lib/tempmail/notified.json")
ACCESS_PATH = os.environ.get("TEMPMAIL_ACCESS_STATE", "/var/lib/tempmail/access.json")
USERS_DIR = os.environ.get("TEMPMAIL_USERS_DIR", "/var/lib/tempmail/users")
POLL_SECONDS = 5

# Per-user mail links: users/<chat_id>.json
#   {"chat_id": 111, "active": "gh-a1b2c3@your-domain.com",
#    "owned": ["gh-a1b2c3@...", "github123@..."],
#    "mail_ids": [12, 13, 14]}
# One file per user, so /mail <id> is just: is this id in YOUR file?
def _user_path(chat_id):
    return os.path.join(USERS_DIR, f"{int(chat_id)}.json")

def load_user(chat_id):
    data = {"chat_id": int(chat_id), "active": None, "owned": [], "mail_ids": []}
    file_data = _load_json(_user_path(chat_id), {})
    if file_data:
        data.update(file_data)
        data["chat_id"] = int(chat_id)
    else:
        # first time: migrate from bot_state.json if it has this chat
        state = _load_json(STATE_PATH, {})
        entry = state.get(str(chat_id), {})
        if entry:
            data["active"] = entry.get("active")
            owned = list(entry.get("owned") or [])
            if entry.get("active") and entry["active"] not in owned:
                owned.append(entry["active"])
            data["owned"] = owned
            if owned or data["active"]:
                save_user(chat_id, data)
    return data

def save_user(chat_id, data):
    data = dict(data)
    data["chat_id"] = int(chat_id)
    _save_json(_user_path(chat_id), data)

def user_mail_ids(chat_id):
    try:
        return set(int(x) for x in load_user(chat_id).get("mail_ids", []))
    except (ValueError, TypeError):
        return set()

def record_mail_for_address(addr, mail_id):
    """Append mail_id to the owner's <chat_id>.json. Returns owner chat id or None."""
    owner = address_owner(addr)
    if owner is None:
        return None
    data = load_user(owner)
    if addr not in data.get("owned", []):
        data.setdefault("owned", []).append(addr)
    if int(mail_id) not in [int(x) for x in data.get("mail_ids", [])]:
        data.setdefault("mail_ids", []).append(int(mail_id))
    save_user(owner, data)
    return owner

def record_mail_for_user(chat_id, mail_id):
    data = load_user(chat_id)
    if int(mail_id) not in [int(x) for x in data.get("mail_ids", [])]:
        data.setdefault("mail_ids", []).append(int(mail_id))
        save_user(chat_id, data)

def _owner_id():
    try:
        v = os.environ.get("TEMPMAIL_OWNER_CHAT_ID", "").strip()
        return int(v) if v else None
    except ValueError:
        return None

def _env_allowed():
    out = set()
    for part in os.environ.get("TEMPMAIL_ALLOWED_CHAT_IDS", "").split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out

def _load_access():
    return _load_json(ACCESS_PATH, {"owner": None, "allowed": []})

def _save_access(data):
    _save_json(ACCESS_PATH, data)

def _allowed_set():
    data = _load_access()
    allowed = set(_env_allowed())
    if _owner_id() is not None:
        allowed.add(_owner_id())
    if data.get("owner"):
        allowed.add(int(data["owner"]))
    for x in data.get("allowed", []):
        try:
            allowed.add(int(x))
        except (ValueError, TypeError):
            pass
    return allowed

def _access_enabled():
    return _owner_id() is not None or bool(_env_allowed()) or bool(_load_access().get("allowed")) or bool(_load_access().get("owner"))

def _is_owner(chat_id):
    owner = _owner_id()
    if owner is not None:
        return chat_id == owner
    data = _load_access()
    return bool(data.get("owner")) and chat_id == int(data["owner"])

def _is_allowed(chat_id):
    if not _access_enabled():
        return True
    return chat_id in _allowed_set()

def _deny_reply(chat_id):
    return (f"Access denied. This bot is private.\nYour chat id is `{chat_id}` — "
            f"send it to the owner to request access.")

def _load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default

def _save_json(path, data):
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"[bot] save {path} failed: {e}", flush=True)

def random_address(prefix="gh"):
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{prefix}-{suffix}@{DOMAIN}"

def custom_address(name):
    """Turn a user-supplied name into an address, or return '' if invalid.
    Accepts 'github123', 'github123@your-domain.com', 'GitHub_123' etc.
    Rules: 2-32 chars, starts with a letter/digit, letters/digits/dot/hyphen/underscore only.
    """
    name = (name or "").strip().lower()
    if "@" in name:
        name = name.split("@")[0]
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,31}", name):
        return ""
    # no leading/trailing dot/hyphen, no double dots
    if name.startswith((".", "-")) or name.endswith((".", "-")) or ".." in name:
        return ""
    return f"{name}@{DOMAIN}"

def format_mail(m):
    code = f"\nCode: `{m['code']}`" if m.get("code") else ""
    return (f"From: {m['from_addr']}\nTo: {m['to_addr']}\n"
            f"Subject: {m['subject'] or '(no subject)'}\n"
            f"Received: {m['received_at']}{code}\nID: {m['id']}")

def send_message(chat_id, text):
    if not TOKEN:
        print(f"[bot] (no token) would send to {chat_id}:\n{text}", flush=True)
        return False
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}).encode()
    req = urllib.request.Request(API + "/sendMessage", data=data)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception as e:
        print(f"[bot] sendMessage failed: {e}", flush=True)
        return False

def get_updates(offset=None, timeout=30):
    params = {"timeout": timeout}
    if offset:
        params["offset"] = offset
    url = API + "/getUpdates?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=timeout + 10) as r:
            return json.load(r).get("result", [])
    except Exception as e:
        print(f"[bot] getUpdates failed: {e}", flush=True)
        time.sleep(5)
        return []

def all_mails_for_user(chat_id):
    """All mails for ALL addresses this chat owns — every address stays active.
    Returns mails sorted newest first, deduplicated by id."""
    seen = {}
    # 1. every owned address
    owned = list(owned_addresses(chat_id))
    for a in load_user(chat_id).get("owned", []):
        if a not in owned:
            owned.append(a)
    for addr in owned:
        for m in list_mails(addr, limit=20):
            seen[m["id"]] = m
    # 2. every mail id recorded in users/<chat_id>.json (covers addresses
    #    whose mail arrived before this version, or via /inbox)
    for mid in user_mail_ids(chat_id):
        if mid not in seen:
            m = get_mail(int(mid))
            if m:
                seen[m["id"]] = m
    return sorted(seen.values(), key=lambda m: m["id"], reverse=True)

def active_address(chat_id):
    state = _load_json(STATE_PATH, {})
    return state.get(str(chat_id), {}).get("active")

def owned_addresses(chat_id):
    """All addresses this chat created with /new (old state: just the active one)."""
    state = _load_json(STATE_PATH, {})
    entry = state.get(str(chat_id), {})
    owned = entry.get("owned") or []
    if entry.get("active") and entry["active"] not in owned:
        owned = owned + [entry["active"]]
    return owned

def address_owner(addr):
    """Chat id that created this address with /new, or None if nobody did."""
    state = _load_json(STATE_PATH, {})
    addr = (addr or "").strip().lower()
    for cid, entry in state.items():
        owned = entry.get("owned") or []
        if entry.get("active"):
            owned = owned + [entry["active"]]
        if addr in [a.lower() for a in owned]:
            return int(cid)
    return None

def set_active(chat_id, addr):
    state = _load_json(STATE_PATH, {})
    entry = state.get(str(chat_id), {}) or {}
    owned = entry.get("owned") or []
    if entry.get("active") and entry["active"] not in owned:
        owned.append(entry["active"])
    if addr not in owned:
        owned.append(addr)
    entry["active"] = addr
    entry["owned"] = owned
    state[str(chat_id)] = entry
    _save_json(STATE_PATH, state)
    # keep the per-user file in sync: users/<chat_id>.json
    data = load_user(chat_id)
    data["active"] = addr
    for a in owned:
        if a not in data.get("owned", []):
            data.setdefault("owned", []).append(a)
    save_user(chat_id, data)

def handle_message(msg):
    """Return (chat_id, reply_text) for a Telegram message dict. Pure logic, testable."""
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    if not text.startswith("/"):
        if not _is_allowed(chat_id):
            return chat_id, _deny_reply(chat_id)
        return chat_id, "Send /help for commands. Use /new to make a temp address."
    parts = text.split()
    cmd = parts[0].split("@")[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "/start":
        # /start always answers, so a stranger can learn their chat id to request access.
        # It does NOT grant access.
        note = ""
        if _access_enabled():
            note = "\nAccess: private — only allowed users can use this bot." if _is_allowed(chat_id) else "\nAccess: private — you are NOT allowed yet."
            if _is_owner(chat_id):
                note += " You are the owner."
        return chat_id, (f"Temp mail for @{DOMAIN}\nYour chat id: `{chat_id}`{note}\n\n"
                         f"/new — random address\n/new <name> — custom address, e.g. /new github123\n"
                         f"All your addresses stay active — /inbox shows mail from all of them.\n"
                         f"/inbox [address] — last mails (all addresses if no address given)\n"
                         f"/code [address] — latest code\n/mail <id> — full mail\n"
                         f"/addresses — list all your addresses")

    # Owner-only admin commands
    if cmd in ("/allow", "/revoke", "/users"):
        if not _is_owner(chat_id):
            return chat_id, "Only the owner can do that."
        data = _load_access()
        allowed = [int(x) for x in data.get("allowed", []) if str(x).isdigit()]
        if cmd == "/users":
            owner = _owner_id() or data.get("owner")
            lines = [f"Owner: {owner}"] + [f"Allowed: {x}" for x in sorted(set(allowed))]
            return chat_id, "\n".join(lines) if lines else "No users."
        if not arg.isdigit():
            return chat_id, f"Usage: {cmd} <chat_id>"
        target = int(arg)
        if cmd == "/allow":
            if target not in allowed:
                allowed.append(target)
                data["allowed"] = allowed
                _save_access(data)
            return chat_id, f"Allowed chat id `{target}`."
        # /revoke
        if target == _owner_id():
            return chat_id, "Cannot revoke the owner."
        if target in allowed:
            allowed.remove(target)
            data["allowed"] = allowed
            _save_access(data)
        return chat_id, f"Revoked chat id `{target}`."

    if not _is_allowed(chat_id):
        return chat_id, _deny_reply(chat_id)

    if cmd == "/help":
        return chat_id, "/new [name], /inbox [address], /code [address], /mail <id>, /addresses, /start — all your addresses stay active, /inbox with no address shows mail from all of them"
    if cmd == "/addresses":
        owned = list(owned_addresses(chat_id))
        for a in load_user(chat_id).get("owned", []):
            if a not in owned:
                owned.append(a)
        if not owned:
            return chat_id, "No addresses yet. Send /new first."
        active = active_address(chat_id)
        lines = [f"• `{a}`" + ("  (latest)" if a == active else "") for a in owned]
        return chat_id, "Your addresses (all active):\n" + "\n".join(lines)
    if cmd == "/new":
        if len(parts) > 2:
            return chat_id, "Use one name only, no spaces.\nExample: `/new github123`"
        if arg:
            addr = custom_address(arg)
            if not addr:
                return chat_id, ("Invalid name. Use 2-32 chars, letters/digits/dot/hyphen/underscore, "
                                 "starting with a letter or digit.\nExample: `/new github123`")
        else:
            addr = random_address()
        set_active(chat_id, addr)
        return chat_id, f"Your temp address:\n`{addr}`\n\nUse it anywhere. I will message you here when mail arrives. Your older addresses stay active too — /inbox shows all of them."
    if cmd in ("/inbox", "/code"):
        # No address given: ALL your addresses are active — show mail from all of them.
        if not arg:
            mails = all_mails_for_user(chat_id)
            if not mails:
                return chat_id, "No mail yet for any of your addresses. Send /new first."
            for _m in mails:
                record_mail_for_user(chat_id, _m["id"])
            if cmd == "/code":
                latest = mails[0]
                if latest.get("code"):
                    return chat_id, f"Latest code for `{latest.get('to_addr', '')}`: `{latest['code']}`\n({latest['subject']})"
                return chat_id, f"Latest mail for `{latest.get('to_addr', '')}` has no code.\n{latest['subject']}"
            lines = [f"• {m['subject'] or '(no subject)'} — {m['code'] or 'no code'} (id {m['id']}, to {m['to_addr']})" for m in mails[:10]]
            return chat_id, "Inbox (all your addresses):\n" + "\n".join(lines)
        # Specific address given: only that one, and only if you own it.
        addr = arg
        owner = address_owner(addr)
        if owner is not None and owner != chat_id:
            return chat_id, f"That address belongs to another user. Create your own with /new."
        if owner is None:
            return chat_id, (f"No address `{addr}` was created with /new here. "
                             f"Create it first with `/new {addr.split('@')[0]}`.")
        mails = list_mails(addr)
        for _m in mails:
            record_mail_for_user(chat_id, _m["id"])
        if not mails:
            return chat_id, f"No mail yet for `{addr}`"
        if cmd == "/code":
            latest = mails[0]
            if latest.get("code"):
                return chat_id, f"Latest code for `{addr}`: `{latest['code']}`\n({latest['subject']})"
            return chat_id, f"Latest mail for `{addr}` has no code.\n{latest['subject']}"
        lines = [f"• {m['subject'] or '(no subject)'} — {m['code'] or 'no code'} (id {m['id']})" for m in mails[:5]]
        return chat_id, f"Inbox `{addr}`:\n" + "\n".join(lines)
    if cmd == "/mail":
        if not arg.isdigit():
            return chat_id, "Usage: /mail <id> — get the id from /inbox"
        m = get_mail(int(arg))
        if not m:
            return chat_id, "Mail not found (maybe expired after 24h)"
        # Mail id is linked to the chat that owns the address it was sent to.
        # Check 1: is this id in YOUR users/<chat_id>.json?
        # Check 2 (fallback for mail that arrived before v1.4): does your chat own the address?
        mail_id = int(arg)
        if mail_id in user_mail_ids(chat_id):
            pass
        else:
            owner = address_owner(m.get("to_addr", ""))
            if owner is None or owner != chat_id:
                return chat_id, "Mail not found or not yours."
            # first read of an older mail — record it in your file from now on
            record_mail_for_user(chat_id, mail_id)
        body = (m["body_text"] or "")[:2000]
        return chat_id, format_mail(m) + f"\n\n{body}"
    return chat_id, "Unknown command. Send /help."

def _addr_to_chat(state):
    """address -> chat_id for every address any chat owns (not just the active one)."""
    out = {}
    for cid, entry in state.items():
        owned = list(entry.get("owned") or [])
        if entry.get("active") and entry["active"] not in owned:
            owned.append(entry["active"])
        for addr in owned:
            out[addr] = cid
    return out

def watcher(stop_event):
    """Push new mail to chats that created the address.
    Every mail id is treated as active on its own — no single last_id gate.
    A mail is pushed once, tracked in notified_ids, so an older id arriving
    after a newer one is NOT skipped (the old last_id bug)."""
    notified = _load_json(NOTIFY_PATH, {"last_id": 0, "notified_ids": []})
    notified_ids = set(int(x) for x in notified.get("notified_ids", []) or [])
    if notified.get("last_id"):
        notified_ids.add(int(notified["last_id"]))
    state = _load_json(STATE_PATH, {})
    # address -> chat_id
    addr_to_chat = _addr_to_chat(state)
    while not stop_event.is_set():
        try:
            state = _load_json(STATE_PATH, {})
            addr_to_chat = _addr_to_chat(state)
            # check every address we know about
            for addr, chat_id in list(addr_to_chat.items()):
                try:
                    if not _is_allowed(int(chat_id)):
                        continue
                except (ValueError, TypeError):
                    continue
                for m in list_mails(addr, limit=20):
                    if m["id"] in notified_ids:
                        continue
                    # link this mail id to the owner's users/<chat_id>.json
                    record_mail_for_address(addr, m["id"])
                    send_message(chat_id, "New mail:\n" + format_mail(m))
                    notified_ids.add(m["id"])
                    # keep the list bounded
                    notified_ids = set(sorted(notified_ids)[-500:])
                    _save_json(NOTIFY_PATH, {"last_id": max(notified_ids) if notified_ids else 0, "notified_ids": sorted(notified_ids)})
        except Exception as e:
            print(f"[bot] watcher error: {e}", flush=True)
        stop_event.wait(POLL_SECONDS)

def main():
    if not TOKEN:
        print("[bot] ERROR: TEMPMAIL_BOT_TOKEN not set. Get one from @BotFather.", flush=True)
        sys.exit(1)
    print(f"[bot] temp mail bot for @{DOMAIN} db={DB_PATH} access={'private' if _access_enabled() else 'OPEN (no owner set — set TEMPMAIL_OWNER_CHAT_ID to lock it down)'}", flush=True)
    stop = threading.Event()
    threading.Thread(target=watcher, args=(stop,), daemon=True).start()
    offset = None
    try:
        while True:
            for upd in get_updates(offset):
                offset = upd["update_id"] + 1
                msg = upd.get("message")
                if msg:
                    chat_id, reply = handle_message(msg)
                    send_message(chat_id, reply)
    except KeyboardInterrupt:
        stop.set()

if __name__ == "__main__":
    main()
