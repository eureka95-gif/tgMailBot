#!/usr/bin/env python3
"""Catch-all SMTP receiver for your-domain.com. Listens on port 25, no auth, no sending.

Any address @your-domain.com works, e.g. github123@your-domain.com.
Mail is stored in SQLite via tempmail_common. Run as root (port 25) or
via systemd with CAP_NET_BIND_SERVICE. No Telegram bot.
"""
import asyncio
import email
import os
import sys
from email import policy
from email.parser import BytesParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aiosmtpd.controller import Controller
from tempmail_common import DOMAIN, DB_PATH, save_mail, cleanup_expired

def _body(msg):
    text, html = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                s = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            except Exception:
                continue
            if ctype == "text/plain" and not text:
                text = s
            elif ctype == "text/html" and not html:
                html = s
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                text = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
        except Exception:
            text = str(msg.get_payload() or "")
    return text, html

class Handler:
    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        # Catch-all: accept anything addressed to our domain.
        # Reject other domains so we are not an open relay target.
        if not address.lower().endswith("@" + DOMAIN):
            return "550 not for this domain"
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(self, server, session, envelope):
        try:
            msg = BytesParser(policy=policy.default).parsebytes(envelope.content)
            subject = str(msg["Subject"] or "")
            from_addr = str(msg["From"] or "")
            text, html = _body(msg)
            for rcpt in envelope.rcpt_tos:
                mail_id, code = save_mail(rcpt, from_addr, subject, text, html)
                print(f"[tempmail] id={mail_id} to={rcpt} from={from_addr} "
                      f"subject={subject!r} code={code}", flush=True)
            cleanup_expired()
        except Exception as e:
            print(f"[tempmail] ERROR saving mail: {e}", flush=True)
            return "451 temporary error"
        return "250 OK"

if __name__ == "__main__":
    host = os.environ.get("TEMPMAIL_SMTP_HOST", "0.0.0.0")
    port = int(os.environ.get("TEMPMAIL_SMTP_PORT", "25"))
    print(f"[tempmail] receiver for @{DOMAIN} on {host}:{port} db={DB_PATH}", flush=True)
    controller = Controller(Handler(), hostname=host, port=port)
    controller.start()
    try:
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        controller.stop()
