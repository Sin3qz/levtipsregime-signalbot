# ============================================================================
#  levSpyBits (wikifolio: levTipsRegime) — freigegeben 29.09.2026 (Stand Backtest-Runde 16)
#  Ab 17.10.2026: Gewichtung zwischen 3x S&P 500 und 1x Bitcoin wird NICHT mehr vorgegeben (frei).
#  Single Source of Truth fuer alle Parameter und Anzeigen.
#
#  EINE Maschine, taegliche Entscheidung auf USD-1x-Schlusskursen:
#     MARKT  =  S&P 500 Total Return (^SP500TR) > SMA280   UND   US-TIPS (TIP) > SMA220
#               -> 3x-S&P 500  +  1x-Bitcoin, Aufteilung frei   (BTC nur im Markt, kein Buy&Hold)
#     sonst  -> 100 % Cash
#  Cooldown: nach jedem Wechsel MARKT<->CASH sind die naechsten 10 Handelstage gesperrt
#  (frueheste Gegenbewegung am 11. Handelstag) — exakt wie im Backtest.
#  Zeitplan: Signal = Schlusskurs Tag d, Handel = Tag d+1.
#
#  Referenz-Backtest mit 75 % 3x-S&P 500 / 25 % 1x-Bitcoin (nur Referenz, keine Vorgabe):
#  Backtest 1987+: CAGR 30,1 %, MaxDD -50 %, Sortino 0,93, z31 2,85, z4 3,02,
#     P(DD<-50 %) 7,7 %, P(DD<-75 %) 0 %; BTC ohne Drift 27,2 % / Sortino 0,85.
#  Realistische Erwartung eher 26-28 % (Laengenwahl nur schwach vorhersagbar).
#  KEINE ANLAGEBERATUNG.
# ============================================================================
STRAT_NAME = "levSpyBits"
STRAT_ASCII = "levSpyBits"

SPY_SMA = 280
TIPS_SMA = 220
COOLDOWN_DAYS = 10

# Gewichtung bewusst offen: Bot, Nachricht und Dashboard nennen nur die beiden Assets (ohne Prozent).
MARKET_ASSETS_TEXT = "3x S&P 500 + 1x Bitcoin"

SPY_TICKER = "^SP500TR"
TIPS_TICKER = "TIP"
BTC_TICKER = "BTC-USD"            # nur Info, kein Signal

SPY_PRODUCT = "3x-S&P 500 (z.B. WisdomTree 3USL, IE00B7Y34M31)"
BTC_PRODUCT = "1x-Bitcoin-ETP"

TRY_COUNT = 3
GRID_START = "1990-01-02"
STATUS_FILE = "letsgo_status.json"          # Dateiname bleibt (Dashboard-Kompatibilitaet)
NOTIFY_FILE = "notify_state_levspybits.json"
HISTORY_FILE = f"history_{SPY_SMA}_{TIPS_SMA}_{COOLDOWN_DAYS}_USD.txt"
INFO_FOOTER = "Hebel-ETPs: Pfad-/Emittentenrisiko. KEINE ANLAGEBERATUNG."

# Datenpruefung: Mindestanzahl Kurse je Signalreihe (Strategie braucht SMA/Momentum-Fenster + Reserve). Beginnt eine Reihe
# spaeter als beim letzten Lauf (abgeschnittene Yahoo-Antwort), wird ebenfalls nicht entschieden (Retry).
MIN_ROWS = 1000
