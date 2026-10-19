# -*- coding: utf-8 -*-
"""
Gemeinsame Infrastruktur fuer alle Signal-Bots (identische Kopie in jedem Repo).

  * Kursdownload (Yahoo via yahooquery, adjustierte Schlusskurse, nur bis GESTERN Berlin)
  * NYSE-Kalender (pandas_market_calendars; Fallback Wochentage)
  * Ausrichtung auf das US-Handelstags-Gitter wie im Backtest ("oncal": Wochenend-Werte
    verwerfen, letzter verfuegbarer Wert je US-Handelstag)
  * Datenpruefung vor jeder Berechnung: Datum des letzten Kurses, Luecken, Tagesspruenge > 30 %
  * ntfy-Zustand (verhindert doppelte Pushes an Wochenenden / bei Retries)

Wirft nie bei Kalender-/State-Problemen; Download-Fehler werden an den Aufrufer gemeldet.
"""
import json
import time

import numpy as np
import pandas as pd

TZ = "Europe/Berlin"
_TODAY = None          # nur fuer Tests/Simulation: festes "heute" (datetime.date)
CAL_FALLBACK = False   # True, wenn der NYSE-Kalender nicht geladen werden konnte (dann keine Entscheidung/ntfy)


def set_today(d):
    global _TODAY
    _TODAY = None if d is None else pd.Timestamp(d).date()


# ==========================================================================
#  Zeit / Kalender
# ==========================================================================
def berlin_today():
    return _TODAY if _TODAY is not None else pd.Timestamp.now(tz=TZ).date()


def berlin_yesterday():
    return berlin_today() - pd.Timedelta(days=1)


def nyse_sessions(start, end):
    """Liste der NYSE-Handelstage (datetime.date) im Intervall [start, end]."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    try:
        import pandas_market_calendars as mcal
        sched = mcal.get_calendar("XNYS").schedule(start_date=start, end_date=end)
        return [d.date() for d in sched.index]
    except Exception as e:                                  # Fallback: Wochentage (Feiertage fehlen!)
        global CAL_FALLBACK
        CAL_FALLBACK = True
        print(f"NYSE-Kalender nicht verfuegbar (Fallback Wochentage): {e}")
        return [d.date() for d in pd.bdate_range(start, end)]


def expected_session_date():
    """Letzte NYSE-Sitzung <= gestern (Berlin): deren Schlusskurs muss jetzt vorliegen."""
    yday = berlin_yesterday()
    s = nyse_sessions(yday - pd.Timedelta(days=20), yday)
    return s[-1] if s else yday


def next_session_after(d):
    d = pd.Timestamp(d).date()
    s = [x for x in nyse_sessions(d, d + pd.Timedelta(days=12)) if x > d]
    return s[0] if s else None


def is_session(d):
    d = pd.Timestamp(d).date()
    return d in nyse_sessions(d, d)


def is_month_end_session(d):
    """True, wenn d der letzte NYSE-Handelstag seines Monats ist."""
    n = next_session_after(d)
    d = pd.Timestamp(d).date()
    return n is not None and (n.month, n.year) != (d.month, d.year)


def last_month_end_session(upto):
    """Juengster Monatsletzter (NYSE) <= upto."""
    upto = pd.Timestamp(upto).date()
    s = nyse_sessions(upto - pd.Timedelta(days=40), upto)
    for d in reversed(s):
        if is_month_end_session(d):
            return d
    return None


def month_end_flags(idx):
    """Monatsletzte Handelstage im Gitter; der juengste Tag kalender-genau (NYSE)."""
    idx = pd.DatetimeIndex(idx)
    per = idx.to_period("M")
    flags = np.zeros(len(idx), bool)
    flags[:-1] = per[1:] != per[:-1]
    if len(idx):
        flags[-1] = is_month_end_session(idx[-1])
    return flags


def de(d):
    try:
        return pd.Timestamp(d).strftime("%d.%m.%Y")
    except Exception:
        return str(d)


def de_short(d):
    try:
        return pd.Timestamp(d).strftime("%d.%m.")
    except Exception:
        return str(d)


# ==========================================================================
#  Download
# ==========================================================================
def _download_close(ticker):
    import yahooquery as yq
    df = yq.Ticker(ticker).history(period="max", adj_ohlc=True, adj_timezone=False)
    if df is None or not hasattr(df, "index") or len(df) == 0:
        raise RuntimeError(f"leere Antwort fuer {ticker}")
    date_level = pd.Index([str(x) for x in df.index.get_level_values("date")])
    colon = date_level.str.contains(":")
    df.index = pd.to_datetime(date_level.where(~colon, date_level.str.split(" ").str[0]))
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    close = close[close > 0]
    close = close[~close.index.duplicated(keep="last")].sort_index()
    return close[close.index.date <= berlin_yesterday()]


def fetch_close(ticker, tries=3):
    last = None
    for attempt in range(tries):
        try:
            s = _download_close(ticker)
            if s is not None and not s.empty:
                return s
        except Exception as e:
            last = e
            print(f"({attempt + 1}/{tries}) Download {ticker} fehlgeschlagen: {e}")
            time.sleep(2)
    raise RuntimeError(f"Konnte {ticker} nicht laden ({last}).")


# ==========================================================================
#  Gitter / Ausrichtung (identisch zum Backtest)
# ==========================================================================
def build_grid(start, end=None, us_series=None):
    """US-Handelstags-Gitter (NYSE) von start bis zur zuletzt erwarteten Sitzung.
    us_series: Liste von US-Kursreihen; fehlt bei einer der juengste Tag (Yahoo-Verzoegerung), endet das
    Gitter am letzten Tag, an dem ALLE vorliegen -> keine Entscheidung auf fortgeschriebenen Kursen."""
    end = end or expected_session_date()
    if us_series:
        lasts = [s.dropna().index[-1].date() for s in us_series if len(s.dropna())]
        if lasts:
            end = min(pd.Timestamp(end).date(), min(lasts))
    return pd.DatetimeIndex(pd.to_datetime(nyse_sessions(start, end)))


def oncal(s, grid):
    """Letzter verfuegbarer Wert je US-Handelstag (Wochenend-Werte verworfen) — wie p5data.oncal."""
    s = s[s.index.dayofweek < 5].dropna()
    return s.reindex(s.index.union(grid)).ffill().reindex(grid)


# ==========================================================================
#  Datenpruefung (vor jeder Berechnung)
# ==========================================================================
def check_series(label, raw, grid, us_market=True, jump=0.30, lookback=260, crypto=False, index_level=False,
                 max_age_days=None, min_rows=None, prev_first=None):
    """Datenpruefung VOR jeder Berechnung. Gibt (fresh: bool, lastDate: str, warnings: list[str]) zurueck.
    fresh = False (-> keine Entscheidung, keine ntfy, Retry) wenn:
      - letzter Kurs aelter als die zuletzt erwartete NYSE-Sitzung (Nicht-US: aelter als max_age_days),
      - die Historie zu kurz ist (min_rows Kurse) oder spaeter beginnt als beim letzten Lauf (prev_first + 30 Tage):
        eine abgeschnittene Yahoo-Antwort wuerde SMAs, Momentum und den Cooldown-Pfad verfaelschen,
      - der juengste Tag einen unplausiblen Sprung > 30 % zeigt (nicht bei Krypto),
      - bei Index-Reihen (^...) der juengste Schluss exakt dem Vortag entspricht (Platzhalter-Zeile bei Yahoo),
      - der NYSE-Kalender nicht geladen werden konnte.
    Nur gemeldet (Warnung): fehlende US-Handelstage und aeltere Spruenge > 30 % in den letzten `lookback` Sitzungen."""
    warns = []
    exp = expected_session_date()
    raw = raw.dropna() if raw is not None else pd.Series(dtype=float)
    last = raw.index[-1].date() if len(raw) else None
    if max_age_days is None:                     # US-Titel: der Schluss der zuletzt erwarteten NYSE-Sitzung muss da sein
        fresh = bool(last is not None and last >= exp)
    else:                                        # Nicht-US-Boerse (Sensex, Xetra): eigene Feiertage -> max. Alter in Kalendertagen
        fresh = bool(last is not None and (pd.Timestamp(exp) - pd.Timestamp(last)).days <= max_age_days)
    if not fresh:
        warns.append(f"{label}: letzter Kurs {de(last)} (erwartet {de(exp)})")
    if min_rows is not None and len(raw) < min_rows:
        fresh = False
        warns.append(f"{label}: nur {len(raw)} Kurse (mind. {min_rows} nötig) — Yahoo-Antwort unvollständig, Retry")
    if prev_first and len(raw) and raw.index[0] > pd.Timestamp(prev_first) + pd.Timedelta(days=30):
        fresh = False
        warns.append(f"{label}: Historie beginnt erst {de(raw.index[0])} (letzter Lauf: {de(prev_first)}) — "
                     f"Yahoo-Antwort abgeschnitten, Retry (falls dauerhaft: 'firstDates' im Status löschen)")
    g = grid[-lookback:]
    if us_market and len(g):
        wk = raw[raw.index.dayofweek < 5]
        miss = [d for d in g if d not in wk.index]
        miss = [d for d in miss if d.date() != exp]           # die letzte Sitzung wird ueber 'fresh' gemeldet
        if len(miss) > 0:
            warns.append(f"{label}: {len(miss)} fehlende Handelstage (zuletzt {de(miss[-1])})")
    if not crypto and len(g) > 1:
        r = oncal(raw, g).pct_change().dropna()
        big = r[r.abs() > jump]
        if len(big):
            if big.index[-1] == g[-1]:
                fresh = False
                warns.append(f"{label}: unplausibler Kurssprung {big.iloc[-1]*100:+.0f}% am {de(big.index[-1])} — "
                             f"keine Entscheidung, Retry; bitte Kurs prüfen")
            else:
                warns.append(f"{label}: Kurssprung {big.iloc[-1]*100:+.0f}% am {de(big.index[-1])} prüfen")
    if index_level and fresh and len(raw) > 2 and float(raw.iloc[-1]) == float(raw.iloc[-2]):
        fresh = False
        warns.append(f"{label}: Schluss {de(last)} identisch mit Vortag (Platzhalter?) — Retry")
    if CAL_FALLBACK:
        fresh = False
        warns.append("NYSE-Kalender nicht verfügbar (Fallback Wochentage) — keine Entscheidung, Retry")
    return fresh, (last.isoformat() if last else None), warns


def merge_first(prev, cur):
    """Frueheste je gesehene Startdaten behalten (eine abgeschnittene Antwort ueberschreibt sie nicht)."""
    out = dict(prev or {})
    for t, d in (cur or {}).items():
        if d and (t not in out or not out[t] or d < out[t]):
            out[t] = d
    return out


def first_date(raw):
    raw = raw.dropna() if raw is not None else None
    return raw.index[0].date().isoformat() if raw is not None and len(raw) else None


# ==========================================================================
#  ntfy-Zustand
# ==========================================================================
def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {} if default is None else default


def _clean(o):
    """NaN/Inf -> None, numpy-Typen -> Python (gueltiges JSON fuer Dashboard/Browser)."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return float(o) if np.isfinite(o) else None
    return o


def save_json(path, obj):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_clean(obj), f, indent=2, ensure_ascii=False, allow_nan=False)
    except Exception as e:
        print(f"{path}: Schreibfehler (ignoriert): {e}")


def mark_status_error(path, msg):
    """Fehlgeschlagener Lauf (z. B. Yahoo-Download): letzter gueltiger Status bleibt erhalten, wird aber als
    'needsRetry' markiert -> der Workflow wiederholt den Lauf, das Dashboard zeigt den Fehler."""
    st = load_json(path)
    note = f"Lauf fehlgeschlagen ({de(berlin_today())}): {str(msg)[:140]} — letzter gültiger Stand angezeigt, Retry läuft"
    st["dataWarnings"] = [note] + [w for w in st.get("dataWarnings", []) if not str(w).startswith("Lauf fehlgeschlagen")]
    st.update(needsRetry=True, lastError=str(msg)[:300], lastErrorAt=pd.Timestamp.now(tz=TZ).isoformat(),
              changeType=None, changedToday=False, monthlyNotifyToday=False, pendingTrade=None, late=False)
    save_json(path, st)


ERROR_HINT = ("Kein Handel auf unvollständigen Daten. Der Workflow versucht es erneut; der nächste erfolgreiche Lauf "
              "rechnet alles (inkl. Cooldown) aus der vollen Historie neu und holt eine fällige ntfy-Meldung nach.")


# ==========================================================================
#  Formatierung (schmale Tabellen fuers Handy)
# ==========================================================================
def pct0(x):
    if x is None or x != x:
        return "n/a"
    v = round(x * 100)
    return "0%" if v == 0 else f"{v:+d}%"


def pct1(x):
    if x is None or x != x:
        return "n/a"
    v = round(x * 100, 1)
    return "0.0%" if v == 0 else f"{v:+.1f}%"


def w0(x):
    return f"{x*100:.0f}%"


W_EPS = 0.0005   # Gewichte < 0,05 % gelten fuer Anzeige und Wechsel-Einstufung als 0 (Rundung auf 0,1 %)


def w1(x):
    """Gewicht mit einer Nachkommastelle (z. B. 37.4%)."""
    return f"{x*100:.1f}%"


def ntfy_allowed(today=None):
    """ntfy nur an tatsaechlichen Handelstagen (NYSE-Sitzung), nie am Wochenende/Feiertag."""
    return is_session(today or berlin_today())


def table(head, rows, align):
    """Monospace-Tabelle. align: je Spalte 'l' oder 'r'. Spaltenbreite = laengster Eintrag."""
    cols = list(zip(*([head] + rows))) if rows else [[h] for h in head]
    wid = [max(len(str(c)) for c in col) for col in cols]
    def fmt(r):
        out = []
        for k, c in enumerate(r):
            c = str(c)
            out.append(c.ljust(wid[k]) if align[k] == "l" else c.rjust(wid[k]))
        return " ".join(out).rstrip()
    return [fmt(head)] + [fmt(r) for r in rows]


def num(x, nd=6):
    try:
        return round(float(x), nd) if x == x else None
    except Exception:
        return None
