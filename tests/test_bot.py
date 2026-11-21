import os, sys
os.environ["TEMPMAIL_DB"] = "/tmp/test-bot.db"
os.environ["TEMPMAIL_DOMAIN"] = "your-domain.com"
os.environ["TEMPMAIL_BOT_STATE"] = "/tmp/test-bot-state.json"
os.environ["TEMPMAIL_NOTIFY_STATE"] = "/tmp/test-notified.json"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("/tmp/test-bot.db", "/tmp/test-bot-state.json", "/tmp/test-notified.json"):
    try: os.remove(p)
    except FileNotFoundError: pass

import bot
from tempmail_common import save_mail as _save_mail

# /new makes a random @your-domain.com address
chat, reply = bot.handle_message({"chat": {"id": 111}, "text": "/new"})
print(reply)
assert "your-domain.com" in reply and "gh-" in reply
addr = reply.split("`")[1]
assert addr.endswith("@your-domain.com")

# save a mock GitHub mail for that address
mid, code = _save_mail(addr, "noreply@github.com", "Your code is 654321", "code 654321", "")
assert code == "654321", code
print("saved mail id", mid, "code", code)

# /code returns it
chat, reply = bot.handle_message({"chat": {"id": 111}, "text": "/code"})
print(reply)
assert "654321" in reply

# /inbox lists it
chat, reply = bot.handle_message({"chat": {"id": 111}, "text": "/inbox"})
print(reply)
assert "654321" in reply

# /mail <id> shows full text
chat, reply = bot.handle_message({"chat": {"id": 111}, "text": f"/mail {mid}"})
print(reply)
assert "654321" in reply

# /start shows chat id
chat, reply = bot.handle_message({"chat": {"id": 111}, "text": "/start"})
assert "111" in reply

# custom /new <name>
chat, reply = bot.handle_message({"chat": {"id": 222}, "text": "/new github123"})
print(reply)
assert "github123@your-domain.com" in reply
mid2, code2 = _save_mail("github123@your-domain.com", "noreply@github.com", "code 777777", "code 777777", "")
chat, reply = bot.handle_message({"chat": {"id": 222}, "text": "/code"})
assert "777777" in reply, reply
print("custom /new OK")

# custom /new with full address + uppercase
chat, reply = bot.handle_message({"chat": {"id": 333}, "text": "/new MyShop@your-domain.com"})
assert "myshop@your-domain.com" in reply, reply
print("custom full-address OK")

# invalid names rejected, active address unchanged
for bad in ("/new a", "/new bad name", "/new bad!name", "/new -bad", "/new bad..name"):
    chat, reply = bot.handle_message({"chat": {"id": 444}, "text": bad})
    assert ("Invalid name" in reply or "one name only" in reply), (bad, reply)
print("invalid names rejected OK")

# --- access control: open by default, private when owner is set ---
os.environ["TEMPMAIL_ACCESS_STATE"] = "/tmp/test-access.json"
bot.ACCESS_PATH = "/tmp/test-access.json"
try: os.remove("/tmp/test-access.json")
except FileNotFoundError: pass

# no owner set -> open, anyone can use it
assert bot.handle_message({"chat": {"id": 999}, "text": "/new"})[1].find("your-domain.com") >= 0
print("open-by-default OK")

# set owner 111 -> 999 is now denied, 111 is allowed
os.environ["TEMPMAIL_OWNER_CHAT_ID"] = "111"
chat, reply = bot.handle_message({"chat": {"id": 999}, "text": "/new"})
assert "Access denied" in reply and "999" in reply, reply
chat, reply = bot.handle_message({"chat": {"id": 111}, "text": "/new testuser"})
assert "testuser@your-domain.com" in reply, reply
print("owner-only deny OK")

# non-owner cannot /allow
chat, reply = bot.handle_message({"chat": {"id": 999}, "text": "/allow 555"})
assert "Only the owner" in reply, reply
# owner allows 555, then 555 can use it
chat, reply = bot.handle_message({"chat": {"id": 111}, "text": "/allow 555"})
assert "Allowed" in reply and "555" in reply, reply
chat, reply = bot.handle_message({"chat": {"id": 555}, "text": "/new hello"})
assert "hello@your-domain.com" in reply, reply
print("/allow OK")
# owner lists users
chat, reply = bot.handle_message({"chat": {"id": 111}, "text": "/users"})
assert "111" in reply and "555" in reply, reply
print("/users OK")
# owner revokes 555, 555 is denied again
chat, reply = bot.handle_message({"chat": {"id": 111}, "text": "/revoke 555"})
assert "Revoked" in reply, reply
chat, reply = bot.handle_message({"chat": {"id": 555}, "text": "/new"})
assert "Access denied" in reply, reply
print("/revoke OK")
# /start still answers a denied user with their chat id (so they can request access)
chat, reply = bot.handle_message({"chat": {"id": 999}, "text": "/start"})
assert "999" in reply and "NOT allowed" in reply, reply
print("/start deny note OK")

# --- mail linked to chat id: others cannot see your mails ---
# per-user files: users/<chat_id>.json holds that user's mail ids
import shutil
os.environ["TEMPMAIL_USERS_DIR"] = "/tmp/test-users"
bot.USERS_DIR = "/tmp/test-users"
shutil.rmtree("/tmp/test-users", ignore_errors=True)
# re-allow 555 so both 111 and 555 are allowed users
bot.handle_message({"chat": {"id": 111}, "text": "/allow 555"})
# 111 creates a private address and gets mail on it
chat, reply = bot.handle_message({"chat": {"id": 111}, "text": "/new private111"})
assert "private111@your-domain.com" in reply, reply
mid3, code3 = _save_mail("private111@your-domain.com", "noreply@github.com", "code 111111", "code 111111", "")
assert code3 == "111111"
# 111 can read it
chat, reply = bot.handle_message({"chat": {"id": 111}, "text": f"/mail {mid3}"})
assert "111111" in reply, reply
chat, reply = bot.handle_message({"chat": {"id": 111}, "text": "/inbox private111@your-domain.com"})
assert "111111" in reply, reply
print("owner can read own mail OK")
# 555 cannot read it by address, by code, or by guessing the mail id
for probe in ("/inbox private111@your-domain.com", "/code private111@your-domain.com", f"/mail {mid3}"):
    chat, reply = bot.handle_message({"chat": {"id": 555}, "text": probe})
    assert "111111" not in reply, (probe, reply)
    assert ("another user" in reply or "not yours" in reply), (probe, reply)
print("other user cannot read mail by address/code/id OK")
# 555 can still read their own mail
chat, reply = bot.handle_message({"chat": {"id": 555}, "text": "/new private555"})
mid4, code4 = _save_mail("private555@your-domain.com", "noreply@github.com", "code 555555", "code 555555", "")
chat, reply = bot.handle_message({"chat": {"id": 555}, "text": f"/mail {mid4}"})
assert "555555" in reply, reply
chat, reply = bot.handle_message({"chat": {"id": 111}, "text": f"/mail {mid4}"})
assert "555555" not in reply and "not yours" in reply, reply
print("each user sees only their own mail OK")
# address never created with /new cannot be probed
chat, reply = bot.handle_message({"chat": {"id": 555}, "text": "/inbox nevercreated@your-domain.com"})
assert "111111" not in reply and "555555" not in reply, reply
print("uncreated address cannot be probed OK")

# --- users/<chat_id>.json files ---
# watcher-style recording: mail id goes into the owner's file only
bot.record_mail_for_address("private111@your-domain.com", mid3)
bot.record_mail_for_address("private555@your-domain.com", mid4)
import json as _json
with open("/tmp/test-users/111.json") as f:
    u111 = _json.load(f)
with open("/tmp/test-users/555.json") as f:
    u555 = _json.load(f)
print("111.json:", u111)
print("555.json:", u555)
assert mid3 in u111["mail_ids"] and mid4 not in u111["mail_ids"], u111
assert mid4 in u555["mail_ids"] and mid3 not in u555["mail_ids"], u555
assert "private111@your-domain.com" in u111["owned"], u111
# /mail works from the file alone (even if address_owner were forgotten)
chat, reply = bot.handle_message({"chat": {"id": 111}, "text": f"/mail {mid3}"})
assert "111111" in reply, reply
chat, reply = bot.handle_message({"chat": {"id": 555}, "text": f"/mail {mid3}"})
assert "111111" not in reply and "not yours" in reply, reply
print("users/<chat_id>.json mail_ids OK")

# --- all mails active: /inbox with no address shows ALL owned addresses ---
# 111 already owns gh-... (code 654321), testuser, private111 (111111)
# 111 creates a second address and gets mail on it too
chat, reply = bot.handle_message({"chat": {"id": 111}, "text": "/new second111"})
assert "your-domain.com" in reply, reply
second_addr = reply.split("`")[1]
mid5, code5 = _save_mail(second_addr, "noreply@github.com", "code 222222", "code 222222", "")
# /inbox with no address must show BOTH 111111 (private111) and 222222 (second)
chat, reply = bot.handle_message({"chat": {"id": 111}, "text": "/inbox"})
print(reply)
assert "111111" in reply and "222222" in reply, reply
assert "654321" in reply, reply  # oldest address still active too
print("/inbox all addresses OK")
# /code with no address returns the latest across all addresses (222222)
chat, reply = bot.handle_message({"chat": {"id": 111}, "text": "/code"})
assert "222222" in reply, reply
print("/code all addresses OK")
# /addresses lists all of them
chat, reply = bot.handle_message({"chat": {"id": 111}, "text": "/addresses"})
assert "private111@your-domain.com" in reply and second_addr in reply, reply
print("/addresses OK")
# /inbox <specific address> still works for just that one
chat, reply = bot.handle_message({"chat": {"id": 111}, "text": "/inbox private111@your-domain.com"})
assert "111111" in reply and "222222" not in reply, reply
print("/inbox specific address OK")
# all_mails_for_user returns all, newest first
allm = bot.all_mails_for_user(111)
ids = [m["id"] for m in allm]
assert ids == sorted(ids, reverse=True) and len(ids) >= 3, ids
print("all_mails_for_user OK:", ids)

print("ALL BOT TESTS PASSED")
