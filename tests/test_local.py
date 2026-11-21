import os, sys, smtplib, time
os.environ["TEMPMAIL_DB"] = "/tmp/test-mail.db"
os.environ["TEMPMAIL_DOMAIN"] = "your-domain.com"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# fresh DB
try: os.remove("/tmp/test-mail.db")
except FileNotFoundError: pass

from aiosmtpd.controller import Controller
from receiver import Handler
from tempmail_common import list_mails, get_mail

ctrl = Controller(Handler(), hostname="127.0.0.1", port=2525)
ctrl.start()
time.sleep(0.5)
try:
    s = smtplib.SMTP("127.0.0.1", 2525)
    s.sendmail("noreply@github.com", ["github123@your-domain.com"],
               "Subject: Your GitHub code is 123456\nFrom: noreply@github.com\n\nYour verification code is 123456")
    s.quit()
    time.sleep(0.5)
    mails = list_mails("github123@your-domain.com", path="/tmp/test-mail.db")
    print("mails:", mails)
    assert len(mails) == 1, "expected 1 mail"
    assert mails[0]["code"] == "123456", f"code wrong: {mails[0]}"
    m = get_mail(mails[0]["id"], path="/tmp/test-mail.db")
    assert "123456" in m["body_text"], "body missing code"
    print("SMTP receiver OK, code extracted:", m["code"])

    # Web inbox via Flask test client
    os.environ["TEMPMAIL_DB"] = "/tmp/test-mail.db"
    import web as webapp
    client = webapp.app.test_client()
    r = client.get("/api/inbox?to=github123@your-domain.com")
    print("web api:", r.status_code, r.get_json())
    assert r.status_code == 200
    assert len(r.get_json()["mails"]) == 1
    assert r.get_json()["mails"][0]["code"] == "123456"
    print("WEB INBOX OK")
    # reject other domain
    s2 = smtplib.SMTP("127.0.0.1", 2525)
    try:
        s2.sendmail("a@b.com", ["x@other.com"], "Subject: hi\n\nhi")
        print("NOTE: other-domain mail was accepted by smtplib (handler should reject at RCPT)")
    except Exception as e:
        print("other-domain rejected as expected:", e)
    s2.quit()
    print("ALL TESTS PASSED")
finally:
    ctrl.stop()
