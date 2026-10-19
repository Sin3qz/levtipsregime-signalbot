import traceback

from strategies.levspybits import run_strategy, commit_notify_state, mark_error, STATUS_FILE
from strategies import common as U
from strategies.constants import STRAT_ASCII

try:
    from send_ntfy import send_ntfy
except Exception:
    def send_ntfy(_title, _msg, tags=None):
        print("send_ntfy module not available.")
        return False


def _ntfy_error():
    try:
        import send_ntfy as _sn
        return _sn.LAST_ERROR or "unbekannter Fehler, siehe Actions-Log"
    except Exception:
        return "send_ntfy.py fehlt im Repo"


def save_text(text):
    if text:
        with open("message.txt", "w", encoding="utf-8") as f:
            f.write(text)


TITLES = {"MARKET": f"{STRAT_ASCII}: BUY - heute in den Markt", "CASH": f"{STRAT_ASCII}: SELL - heute in Cash"}


def main():
    # signal: None = nur Discord-Status; "MARKET"/"CASH" = echter Wechsel -> ntfy; "Error"
    signal, ntfy_text, discord_text = run_strategy()
    save_text(discord_text)
    if signal in TITLES:
        ok = False
        title = TITLES[signal] + (" (verspaetet)" if "verspätet" in (ntfy_text or "")[:300] else "")
        try:
            ok = send_ntfy(title, ntfy_text or discord_text)
        except Exception as e:
            print(f"ntfy send raised (ignored): {e}")
        if ok or ok is None:           # None = kein NTFY_TOPIC konfiguriert -> nicht endlos wiederholen
            commit_notify_state()
        if ok is not True:             # in Discord sichtbar machen (oben, da Discord bei 1900 Zeichen abschneidet)
            if ok is None:
                warn = "⚠️ ntfy NICHT gesendet: Secret NTFY_TOPIC fehlt/leer in diesem Repo (Meldung nur in Discord)."
            else:
                warn = (f"⚠️ ntfy-Push FEHLGESCHLAGEN ({_ntfy_error()}). Der naechste Lauf wiederholt automatisch. "
                        "Pruefen: Secret NTFY_TOPIC = nur der Topic-Name (oder https://ntfy.sh/<topic>), "
                        "Secret NTFY_SERVER leer lassen bzw. loeschen.")
            save_text(warn + "\n\n" + (discord_text or ""))
            if ok is False:            # Sicherheitslauf (11:47 UTC) soll den Push erneut versuchen
                try:
                    st = U.load_json(STATUS_FILE); st["ntfyFailed"] = _ntfy_error(); U.save_json(STATUS_FILE, st)
                except Exception as e:
                    print(f"Status-Markierung ntfyFailed fehlgeschlagen: {e}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        save_text("Error\n\n" + "".join(traceback.format_exception(e)))
        try:
            mark_error(e)
        except Exception:
            pass
