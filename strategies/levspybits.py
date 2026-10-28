# -*- coding: utf-8 -*-
"""
levSpyBits — Strategie-Kern + LIVE-Runner.

Vertrag fuer main.py:  run_strategy() -> (signal, ntfy_text, discord_text)
    signal "MARKET"/"IEF"/"CASH" -> echter Wechsel, heute handeln (ntfy);  None -> nur Discord;  "Error"
ntfy nur bei tatsaechlichem Handel: Vergleich der aktuellen Allokation mit der zuletzt gemeldeten
(notify_state_levspybits.json) -> keine Doppelmeldungen am Wochenende/bei Retries, kein verpasster
Wechsel, wenn ein Tag verspaetet geliefert wird. Nur mit frischen Daten.
"""
import numpy as np
import pandas as pd

from . import common as U
from .constants import (STRAT_NAME, SPY_SMA, TIPS_SMA, TLT_SMA, COOLDOWN_DAYS, MARKET_ASSETS_TEXT, SPY_TICKER,
                        TIPS_TICKER, TLT_TICKER, BTC_TICKER, SPY_PRODUCT, BTC_PRODUCT, IEF_PRODUCT, IEF_ISIN, IEF_TEXT,
                        TRY_COUNT, GRID_START, STATUS_FILE, NOTIFY_FILE, HISTORY_FILE, INFO_FOOTER, MIN_ROWS)

PENDING_STATE = {}
CASH, MARKET, IEF = 0, 1, 2                      # Zustands-Codes der Maschine
STATE_NAMES = {CASH: "CASH", MARKET: "MARKET", IEF: "IEF"}


def mark_error(e):
    """Lauf fehlgeschlagen: Status als needsRetry markieren (letzter gueltiger Stand bleibt)."""
    U.mark_status_error(STATUS_FILE, e)


def commit_notify_state():
    if PENDING_STATE:
        U.save_json(NOTIFY_FILE, dict(PENDING_STATE))


# ==========================================================================
#  Kern (rein, testbar) — identisch zu spy5.machine / r12s
# ==========================================================================
def target_series(spy, tips, tlt, spy_sma=SPY_SMA, tips_sma=TIPS_SMA, tlt_sma=TLT_SMA):
    """Zielzustand je Tag (ohne Cooldown):
         MARKET, wenn S&P > SMA280 UND TIPS > SMA220;
         IEF,    wenn TIPS < SMA220 UND TLT > SMA200  (TIPS-Abstand strikt negativ, beide Werte vorhanden);
         sonst CASH.  Fehlende Werte (SMA noch nicht berechenbar) = Bedingung nicht erfuellt."""
    ds = (spy / spy.rolling(spy_sma).mean() - 1).values
    dt = (tips / tips.rolling(tips_sma).mean() - 1).values
    dl = (tlt / tlt.rolling(tlt_sma).mean() - 1).values
    market = (np.nan_to_num(ds, nan=-1) > 0) & (np.nan_to_num(dt, nan=-1) > 0)
    ief = (np.nan_to_num(dt, nan=1) < 0) & (np.nan_to_num(dl, nan=-1) > 0) & ~market
    return np.where(market, MARKET, np.where(ief, IEF, CASH)).astype(int)


def machine(target, cooldown=COOLDOWN_DAYS):
    """Zustand je Tag (CASH/MARKET/IEF). Nach jedem Wechsel an Tag i sind die Tage i+1..i+cooldown
    gesperrt (Backtest: 'frozen = i + cool', Wechsel nur wenn i > frozen) — fuer jeden Wechsel zwischen
    den drei Zustaenden gleich. Start in Cash.
    Gibt (alloc, remaining) zurueck; remaining = noch gesperrte Handelstage nach dem jeweiligen Tag."""
    cur, frozen = CASH, -1
    alloc = np.zeros(len(target), int); rem = np.zeros(len(target), int)
    for i, t in enumerate(target):
        t = int(t)
        if t != cur and i > frozen:
            cur = t; frozen = i + cooldown
        alloc[i] = cur; rem[i] = max(0, frozen - i)
    return alloc, rem


# ==========================================================================
#  Nachricht
# ==========================================================================
LABEL = {"MARKET": "MARKT", "IEF": "3x IEF", "CASH": "CASH"}
TIMELINE_LEAD = {"MARKET": "MARKET", "IEF": "UST_IEF", "CASH": "CASH"}      # Farbe im Dashboard-Zeitbalken
ALLOCATION = {
    "MARKET": [{"asset": "SP500", "display": "S&P 500", "weight": None, "leverage": 3, "product": SPY_PRODUCT, "isin": ""},
               {"asset": "BTC", "display": "Bitcoin", "weight": None, "leverage": 1, "product": BTC_PRODUCT, "isin": ""}],
    "IEF": [{"asset": "UST_IEF", "display": "US-Treasury 7-10y", "weight": 1.0, "leverage": 3, "product": IEF_PRODUCT, "isin": IEF_ISIN}],
    "CASH": [{"asset": "CASH", "display": "Cash", "weight": 1.0, "leverage": 1, "product": "—", "isin": ""}],
}


def _change_type(prev, new):
    """Dashboard-Kennung eines Wechsels: aus Cash in den Markt = BUY, in Cash = SELL, sonst (mit IEF) = SWITCH."""
    if new == "CASH":
        return "SELL"
    if new == "MARKET" and prev in (None, "CASH"):
        return "BUY"
    return "SWITCH"


def _msg(c):
    L = []
    when = (f"(verspätet; Signal: Schluss {U.de(c['change_date'])}, regulär {U.de(c['trade'])} — heute {U.de(c['today'])} handeln)"
            if c["late"] else f"(Signal: Schluss {U.de(c['change_date'])}, handeln am {U.de(c['trade'])})")
    if c["signal"] == "MARKET":
        L += ["🟢 BUY — heute in den Markt" + (" (raus aus 3x IEF)" if c["prev"] == "IEF" else ""), when, ""]
    elif c["signal"] == "IEF":
        L += [f"🔵 WECHSEL — heute in {IEF_TEXT}" + (" (raus aus dem Markt)" if c["prev"] == "MARKET" else ""), when, ""]
    elif c["signal"] == "CASH":
        L += ["🔴 SELL — heute alles in Cash", when, ""]
    elif c["pending"]:
        L += [f"⏳ Wechsel zu {LABEL[c['state']]} (Signal: Schluss {U.de(c['change_date'])}) — "
              f"handeln am {U.de(c['pending'])}; ntfy kommt an diesem Handelstag.", ""]
    if c["state"] == "MARKET":
        L += [f"📈 {STRAT_NAME}: MARKT", "• 3x S&P 500", "• 1x Bitcoin"]
    elif c["state"] == "IEF":
        L += [f"🏦 {STRAT_NAME}: {IEF_TEXT} (100%)", f"• {IEF_PRODUCT} ({IEF_ISIN})"]
    else:
        L += [f"💵 {STRAT_NAME}: CASH (100%)"]
    L += [f"Cooldown: {c['rem']} Handelstage gesperrt" if c["rem"] > 0 else "Cooldown: frei (Wechsel möglich)"]
    if c["no_new_day"]:
        L += [f"ℹ️ Kein neuer US-Handelstag seit {U.de_short(c['asof'])} (Wochenende/Feiertag)"]
    rows = [["S&P 500", f"SMA{SPY_SMA}", U.pct1(c["spy_d"]), "über" if c["spy_d"] > 0 else "unter"],
            ["US-TIPS", f"SMA{TIPS_SMA}", U.pct1(c["tips_d"]), "über" if c["tips_d"] > 0 else "unter"],
            ["TLT 20y+", f"SMA{TLT_SMA}", U.pct1(c["tlt_d"]), "über" if c["tlt_d"] > 0 else "unter"]]
    tab = U.table(["Signal", "Linie", "Abst.", ""], rows, "lllr")
    rule = (f"Regel: MARKT, wenn S&P > SMA{SPY_SMA} UND TIPS > SMA{TIPS_SMA}; 3x IEF, wenn TIPS < SMA{TIPS_SMA} "
            f"UND TLT > SMA{TLT_SMA}; sonst Cash. Nach jedem Wechsel {COOLDOWN_DAYS} Tage Sperre.")
    disc = L + ["", f"Signale (USD, Stand {U.de_short(c['asof'])}):", "```"] + tab + ["```", rule]
    ntfy = L + ["", f"Signale (Stand {U.de_short(c['asof'])}):"] + [f"{r[0]}: {r[2]} {r[3]} {r[1]}" for r in rows] + [rule]
    tail = []
    if c["btc"] is not None:
        tail += [f"BTC (Info): {c['btc']['price']:,.0f} USD ({U.de_short(c['btc']['date'])})".replace(",", ".")]
    if c["stale"]:
        tail += ["", "⚠️ Kursdaten evtl. veraltet — Retry läuft; ntfy erst mit frischen Daten."]
    if c["warns"]:
        tail += ["", "⚠️ Datenprüfung:"] + [f"• {x}" for x in c["warns"][:6]]
    tail += ["", INFO_FOOTER]
    return "\n".join(ntfy + tail), "\n".join(disc + tail)


# ==========================================================================
#  Hauptfunktion
# ==========================================================================
def run_strategy(raw=None, write_files=True):
    if raw is None:
        try:
            raw = {t: U.fetch_close(t, TRY_COUNT) for t in (SPY_TICKER, TIPS_TICKER, TLT_TICKER)}
        except Exception as e:
            mark_error(e)
            return ("Error", None, f"{STRAT_NAME}: Signaldaten (^SP500TR / TIP / TLT) nicht ladbar: {e}" + "\n" + U.ERROR_HINT)
        try:
            raw[BTC_TICKER] = U.fetch_close(BTC_TICKER, 2)
        except Exception as e:
            print(f"BTC-Infokurs nicht verfuegbar (ignoriert): {e}")
    prev_first = U.load_json(STATUS_FILE).get("firstDates", {})         # Erkennung abgeschnittener Yahoo-Antworten
    grid = U.build_grid(GRID_START, us_series=[raw[SPY_TICKER], raw[TIPS_TICKER], raw[TLT_TICKER]])
    spy = U.oncal(raw[SPY_TICKER], grid); tips = U.oncal(raw[TIPS_TICKER], grid); tlt = U.oncal(raw[TLT_TICKER], grid)
    f1, l1, w1 = U.check_series("S&P 500 (^SP500TR)", raw[SPY_TICKER], grid,
                                  index_level=True, min_rows=MIN_ROWS, prev_first=prev_first.get(SPY_TICKER))
    f2, l2, w2 = U.check_series("US-TIPS (TIP)", raw[TIPS_TICKER], grid, min_rows=MIN_ROWS,
                                  prev_first=prev_first.get(TIPS_TICKER))
    f3, l3, w3 = U.check_series("US-Treasury 20y+ (TLT)", raw[TLT_TICKER], grid, min_rows=MIN_ROWS,
                                  prev_first=prev_first.get(TLT_TICKER))
    stale = not (f1 and f2 and f3); warns = sorted(set(w1 + w2 + w3))

    tgt = target_series(spy, tips, tlt)
    alloc, rem = machine(tgt)
    idx = grid; i = len(idx) - 1
    spy_sma = spy.rolling(SPY_SMA).mean(); tips_sma = tips.rolling(TIPS_SMA).mean(); tlt_sma = tlt.rolling(TLT_SMA).mean()
    spy_d = float(spy.iloc[i] / spy_sma.iloc[i] - 1); tips_d = float(tips.iloc[i] / tips_sma.iloc[i] - 1)
    tlt_d = float(tlt.iloc[i] / tlt_sma.iloc[i] - 1)
    cur = STATE_NAMES[int(alloc[i])]
    chg = np.where(alloc[1:] != alloc[:-1])[0]
    change_date = idx[chg[-1] + 1].date() if len(chg) else idx[0].date()

    # ---- ntfy nur bei tatsaechlichem Handel, nur an NYSE-Handelstagen ----
    today = U.berlin_today()
    trade_c = U.next_session_after(change_date)            # regulaerer Handelstag des juengsten Wechsels
    state = U.load_json(NOTIFY_FILE)
    signal, late, pending = None, False, None
    if not state.get("lastAllocation"):
        # Erststart (oder Zustand verloren): Ist der juengste Wechsel noch nicht gehandelt (Handelstag heute oder
        # spaeter), wird mit der Allokation VOR dem Wechsel gestartet -> die Meldung geht normal raus.
        if len(chg) and trade_c is not None and today <= trade_c:
            state = {"lastAllocation": STATE_NAMES[int(alloc[chg[-1]])], "init": today.isoformat()}
        else:
            state.update(lastAllocation=cur, since=change_date.isoformat(), init=today.isoformat())
            if write_files:
                U.save_json(NOTIFY_FILE, state)
    prev = state.get("lastAllocation")
    if state["lastAllocation"] != cur and not stale:
        if U.ntfy_allowed(today) and today >= trade_c:
            signal = cur
            late = today > trade_c
            state.update(lastAllocation=cur, since=change_date.isoformat(), sentOn=today.isoformat())
            PENDING_STATE.clear(); PENDING_STATE.update(state)
        else:                                               # Wochenende/Feiertag -> ntfy am naechsten Handelstag
            pending = trade_c if (trade_c and trade_c >= today) else U.next_session_after(today)

    btc = None
    if BTC_TICKER in raw and len(raw[BTC_TICKER]):
        b = raw[BTC_TICKER]; btc = {"price": float(b.iloc[-1]), "date": b.index[-1].date().isoformat()}
    ctx = dict(signal=signal, state=cur, prev=prev, rem=int(rem[i]), change_date=change_date, trade=trade_c,
               late=late, today=today, pending=pending,
               asof=idx[i].date(), spy_d=spy_d, tips_d=tips_d, tlt_d=tlt_d, btc=btc, stale=stale, warns=warns,
               no_new_day=(not stale) and idx[i].date() < U.berlin_yesterday())
    ntfy_text, disc_text = _msg(ctx)

    # ---- Status (Dashboard; alte Felder bleiben erhalten) + History ----
    exp = U.expected_session_date().isoformat()
    status = {
        "updated": pd.Timestamp.now(tz=U.TZ).isoformat(), "name": STRAT_NAME,
        "strategy": (f"{MARKET_ASSETS_TEXT} | {IEF_TEXT} (USD-Signale, "
                     f"SPY-SMA{SPY_SMA}/TIPS-SMA{TIPS_SMA}/TLT-SMA{TLT_SMA}, Cooldown {COOLDOWN_DAYS})"),
        "signals": {
            "spy_usd": {"key": "spy_usd", "name": "S&P 500 (USD)", "ticker": SPY_TICKER, "currentDate": l1, "expectedDate": exp,
                        "current": float(spy.iloc[i]), "sma": float(spy_sma.iloc[i]), "diffPct": spy_d * 100, "fresh": bool(f1)},
            "tips_usd": {"key": "tips_usd", "name": "US-TIPS (USD)", "ticker": TIPS_TICKER, "currentDate": l2, "expectedDate": exp,
                         "current": float(tips.iloc[i]), "sma": float(tips_sma.iloc[i]), "diffPct": tips_d * 100, "fresh": bool(f2)},
            "tlt_usd": {"key": "tlt_usd", "name": "US-Treasury 20y+ (USD)", "ticker": TLT_TICKER, "currentDate": l3, "expectedDate": exp,
                        "current": float(tlt.iloc[i]), "sma": float(tlt_sma.iloc[i]), "diffPct": tlt_d * 100, "fresh": bool(f3)}},
        "needsRetry": bool(stale), "dataWarnings": warns, "asOf": idx[i].date().isoformat(),
        "firstDates": U.merge_first(prev_first, {t: U.first_date(raw[t]) for t in (SPY_TICKER, TIPS_TICKER, TLT_TICKER)}),
        "allocationState": cur, "cooldown": int(rem[i]), "since": change_date.isoformat(),
        "changedToday": signal is not None, "late": bool(late),
        "pendingTrade": pending.isoformat() if pending else None, "changeType": (_change_type(prev, signal) if signal else None),
        # Gewichtung im Markt offen: weight = None (Dashboard zeigt nur die Assets, ohne Prozent und ohne Cash-Rest)
        "weightFree": cur == "MARKET",
        "allocation": ALLOCATION[cur],
        "table": {"head": ["Signal (USD)", "Linie", "Abstand", "Status"],
                  "note": (f"MARKT, wenn S&P und TIPS über ihrer Linie; 3x IEF, wenn TIPS unter SMA{TIPS_SMA} und TLT über "
                           f"SMA{TLT_SMA}; sonst Cash; nach jedem Wechsel {COOLDOWN_DAYS} Handelstage Sperre"),
                  "rows": [["S&P 500 (^SP500TR)", f"SMA{SPY_SMA}", U.num(spy_d), "über" if spy_d > 0 else "unter"],
                           ["US-TIPS (TIP)", f"SMA{TIPS_SMA}", U.num(tips_d), "über" if tips_d > 0 else "unter"],
                           ["US-Treasury 20y+ (TLT)", f"SMA{TLT_SMA}", U.num(tlt_d), "über" if tlt_d > 0 else "unter"]],
                  "kinds": ["text", "text", "spct", "text"]},
        "timeline": {"span": "letzte 120 Handelstage", "what": "ob im Markt (Farbe), in 3x IEF (türkis) oder in Cash (grau)",
                     "items": [{"date": idx[k].date().isoformat(), "lead": TIMELINE_LEAD[STATE_NAMES[int(alloc[k])]],
                                "allocation": STATE_NAMES[int(alloc[k])]} for k in range(max(0, i - 119), i + 1)]},
    }
    if btc is not None:
        status["btc_info"] = btc
    if write_files:
        U.save_json(STATUS_FILE, status)
        try:
            first = int(np.argmax(~np.isnan((spy / spy_sma).values) & ~np.isnan((tips / tips_sma).values)))
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                # Spalten: Datum, S&P, TIPS, S&P-SMA, TIPS-SMA, Cooldown, Zustand (MARKET/IEF/CASH), TLT, TLT-SMA
                for k in range(first, i + 1):
                    f.write(f"{idx[k]},{spy.iloc[k]},{tips.iloc[k]},{spy_sma.iloc[k]},{tips_sma.iloc[k]},{rem[k]},"
                            f"{STATE_NAMES[int(alloc[k])]},{tlt.iloc[k]},{tlt_sma.iloc[k]}\n")
        except Exception as e:
            print(f"History-Schreibfehler (ignoriert): {e}")
    return signal, ntfy_text, disc_text
