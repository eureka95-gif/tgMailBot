"""Shared storage for your-domain.com temp mail. No Telegram, web inbox only."""
import os
import re
import sqlite3

DOMAIN = os.environ.get("TEMPMAIL_DOMAIN", "your-domain.com")
DB_PATH = os.environ.get("TEMPMAIL_DB", "/var/lib/tempmail/mail.db")
# Hours a mail is kept before auto-delete. Temp mail = short-lived.
RETENTION_HOURS = int(os.environ.get("TEMPMAIL_RETENTION_HOURS", "24"))

CODE_RE = re.compile(r"\b(\d{4,8})\b")

def init_db(path=DB_PATH):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("""
        CREATE TABLE IF NOT EXISTS mails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            to_addr TEXT NOT NULL,
            from_addr TEXT NOT NULL,
            subject TEXT DEFAULT '',
            body_text TEXT DEFAULT '',
            body_html TEXT DEFAULT '',
            code TEXT DEFAULT '',
            received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME DEFAULT (datetime('now', '+%d hours'))
        )
    """ % RETENTION_HOURS)
    con.execute("CREATE INDEX IF NOT EXISTS idx_to ON mails(to_addr)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_received ON mails(received_at DESC)")
    con.commit()
    con.close()

def extract_code(text):
    if not text:
        return ""
    # Prefer a 6-digit code, common for GitHub / verification mails.
    # Fall back to any 4-8 digit number, ignoring years like 2026.
    candidates = CODE_RE.findall(text)
    for c in candidates:
        if len(c) == 6:
            return c
    for c in candidates:
        if c not in ("2026", "2025", "2024") and len(c) >= 4:
            return c
    return ""

def save_mail(to_addr, from_addr, subject, body_text, body_html, path=DB_PATH):
    init_db(path)
    code = extract_code((subject or "") + "\n" + (body_text or ""))
    con = sqlite3.connect(path)
    cur = con.execute(
        "INSERT INTO mails (to_addr, from_addr, subject, body_text, body_html, code) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (to_addr.lower(), from_addr, subject or "", body_text or "", body_html or "", code),
    )
    mail_id = cur.lastrowid
    con.commit()
    con.close()
    return mail_id, code

def list_mails(to_addr, limit=50, path=DB_PATH):
    init_db(path)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id, to_addr, from_addr, subject, code, received_at "
        "FROM mails WHERE lower(to_addr)=lower(?) ORDER BY id DESC LIMIT ?",
        (to_addr, limit),
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]

def get_mail(mail_id, path=DB_PATH):
    init_db(path)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM mails WHERE id=?", (mail_id,)).fetchone()
    con.close()
    return dict(row) if row else None

def cleanup_expired(path=DB_PATH):
    init_db(path)
    con = sqlite3.connect(path)
    cur = con.execute("DELETE FROM mails WHERE expires_at < datetime('now')")
    n = cur.rowcount
    con.commit()
    con.close()
    return n
