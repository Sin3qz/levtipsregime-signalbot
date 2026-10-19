"""
ntfy-Push (https://ntfy.sh, kostenlos, kein Account).
Setup: ntfy-App installieren, das Topic aus dem GitHub-Secret NTFY_TOPIC abonnieren.
Der Topic-Name ist wie ein Passwort (lang und nicht erratbar waehlen).

Secret NTFY_TOPIC darf sein:  meintopic123   |   ntfy.sh/meintopic123   |   https://ntfy.sh/meintopic123
(Leerzeichen/Zeilenumbrueche/Anfuehrungszeichen werden entfernt). Optional NTFY_SERVER (eigener Server).

Rueckgabe: True (gesendet) / False (Fehler -> naechster Lauf wiederholt, Grund in LAST_ERROR) / None (kein Topic).
Wirft NIE (der Discord-Ablauf darf nie gestoert werden). Das Topic wird NIE ins (oeffentliche) Log geschrieben.
"""
import os
import re
import time
import urllib.error
import urllib.request

LAST_ERROR = ""
_TOPIC_RE = re.compile(r"^[-_A-Za-z0-9]{1,64}$")


def _target():
    """-> (url, topic, fehler). Akzeptiert Topic-Name oder komplette ntfy-URL."""
    raw = (os.environ.get("NTFY_TOPIC") or "").strip().strip("'\"").strip()
    if not raw:
        return None, None, None
    server = (os.environ.get("NTFY_SERVER") or "").strip().strip("'\"").strip().rstrip("/")
    if re.match(r"^https?://", raw, re.I):                      # komplette URL im Secret
        base, _, topic = raw.rstrip("/").rpartition("/")
        server = base
    else:
        topic = raw.strip("/")
        if "/" in topic:                                         # z.B. "ntfy.sh/meintopic"
            host, _, topic = topic.rpartition("/")
            server = server or "https://" + host
    server = server or "https://ntfy.sh"
    if not re.match(r"^https?://", server, re.I):
        server = "https://" + server
    if not _TOPIC_RE.match(topic or ""):
        return None, topic, ("NTFY_TOPIC ungueltig: erlaubt sind nur Buchstaben, Ziffern, - und _ (max. 64 Zeichen), "
                             "ohne Leerzeichen/Umlaute")
    return f"{server}/{topic}", topic, None


def _clean(msg, topic):
    return msg.replace(topic, "***") if topic else msg


def send_ntfy(title, message, tags="bell"):
    global LAST_ERROR
    LAST_ERROR = ""
    url, topic, err = _target()
    if url is None and err is None:
        print("Kein NTFY_TOPIC gesetzt (ntfy uebersprungen).")
        return None                    # nicht konfiguriert: kein Fehler, Meldung gilt als erledigt (nur Discord)
    if err:
        LAST_ERROR = err
        print(f"ntfy failed: {err}")
        return False
    data = (message or "-").encode("utf-8")
    for attempt in (1, 2, 3):
        try:
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Title", (title or "Signal").encode("ascii", "replace").decode("ascii"))   # Header muessen ASCII sein
            req.add_header("Priority", "high")
            req.add_header("Tags", tags)
            req.add_header("User-Agent", "gtaa-signalbot/1.0")
            with urllib.request.urlopen(req, timeout=30) as resp:
                status = resp.status
            print(f"ntfy OK ({status})")
            if 200 <= status < 300:
                return True
            LAST_ERROR = f"HTTP {status}"
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:200]
            except Exception:
                pass
            LAST_ERROR = _clean(f"HTTP {e.code} {e.reason} {body}".strip(), topic)
            if e.code not in (429, 500, 502, 503, 504):
                break                                            # 4xx (z.B. falsches Topic/Server) -> Wiederholen sinnlos
        except Exception as e:
            LAST_ERROR = _clean(f"{type(e).__name__}: {e}", topic)
        print(f"ntfy failed (Versuch {attempt}/3): {LAST_ERROR}")
        if attempt < 3:
            time.sleep(10 * attempt)
    print(f"ntfy failed: {LAST_ERROR}")
    return False


if __name__ == "__main__":
    import sys
    r = send_ntfy("TEST Signalbot", "ntfy Test-Nachricht: wenn du das liest, funktioniert der Push.")
    if r is None:
        print("::error::NTFY_TOPIC-Secret ist leer oder fehlt in diesem Repo.")
        sys.exit(1)
    if r is False:
        print(f"::error::ntfy-Test fehlgeschlagen: {LAST_ERROR}")
        sys.exit(1)
    print("ntfy-Test erfolgreich gesendet.")
