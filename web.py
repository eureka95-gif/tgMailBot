#!/usr/bin/env python3
"""Web inbox for your-domain.com temp mail. No Telegram bot.

Open http://<vps-ip>:8080/ , type any address @your-domain.com
(e.g. github123@your-domain.com) and see its mail + verification code.
Set INBOX_TOKEN to require ?token=... — otherwise it is open, so
put it behind nginx + basic auth, or bind to localhost + SSH tunnel.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, render_template_string
from tempmail_common import DOMAIN, list_mails, get_mail, cleanup_expired

app = Flask(__name__)
TOKEN = os.environ.get("INBOX_TOKEN", "")

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Temp mail — {{ domain }}</title>
<style>body{font-family:system-ui,sans-serif;max-width:760px;margin:24px auto;padding:0 16px}
input,button{font-size:16px;padding:8px} input{width:70%} .code{font-size:22px;font-weight:700;
background:#eef;padding:4px 10px} .mail{border:1px solid #ccc;padding:10px;margin:10px 0}
small{color:#666}</style></head><body>
<h1>Temp mail — {{ domain }}</h1>
<p>Any address works, e.g. <code>github123@{{ domain }}</code>. Mail auto-deletes after 24h.</p>
<form method="get"><input name="to" value="{{ to }}" placeholder="name@{{ domain }}">
<button>View inbox</button></form>
{% if to %}
<h2>Inbox: {{ to }}</h2>
{% if mails %}{% for m in mails %}<div class="mail">
<b>{{ m.subject or '(no subject)' }}</b><br><small>From {{ m.from_addr }} · {{ m.received_at }}</small><br>
{% if m.code %}Code: <span class="code">{{ m.code }}</span><br>{% endif %}
<a href="/mail/{{ m.id }}{% if token %}?token={{ token }}{% endif %}">Open</a>
</div>{% endfor %}{% else %}<p>No mail yet for this address.</p>{% endif %}
{% endif %}</body></html>"""

def _ok():
    if not TOKEN:
        return True
    return request.args.get("token", "") == TOKEN

@app.before_request
def _auth():
    if request.path in ("/health",):
        return None
    if not _ok():
        return "token required: add ?token=YOUR_TOKEN", 401

@app.route("/health")
def health():
    return "ok"

@app.route("/")
def index():
    to = request.args.get("to", "").strip()
    mails = list_mails(to) if to else []
    return render_template_string(PAGE, domain=DOMAIN, to=to, mails=mails,
                                  token=request.args.get("token", ""))

@app.route("/mail/<int:mail_id>")
def mail_view(mail_id):
    m = get_mail(mail_id)
    if not m:
        return "not found", 404
    body = (m["body_text"] or "") or "(empty)"
    return (f"<h1>{m['subject']}</h1><p>From {m['from_addr']} · To {m['to_addr']} · "
            f"{m['received_at']}</p>"
            + (f"<p>Code: <b style='font-size:24px'>{m['code']}</b></p>" if m["code"] else "")
            + f"<pre style='white-space:pre-wrap'>{body}</pre>"
            + '<p><a href="/">Back</a></p>')

@app.route("/api/inbox")
def api_inbox():
    to = request.args.get("to", "").strip()
    if not to:
        return jsonify({"error": "to required"}), 400
    cleanup_expired()
    return jsonify({"to": to, "mails": list_mails(to)})

@app.route("/api/mail/<int:mail_id>")
def api_mail(mail_id):
    m = get_mail(mail_id)
    return jsonify(m) if m else (jsonify({"error": "not found"}), 404)

if __name__ == "__main__":
    host = os.environ.get("TEMPMAIL_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("TEMPMAIL_WEB_PORT", "8080"))
    print(f"[tempmail] web inbox on {host}:{port} domain={DOMAIN} token={'set' if TOKEN else 'not set'}", flush=True)
    app.run(host=host, port=port)
