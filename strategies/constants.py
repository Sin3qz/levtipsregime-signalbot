# ============================================================================
#  levSpyBits (wikifolio: levTipsRegime) — freigegeben 29.09.2026 (Stand Backtest-Runde 16)
#  Ab 28.10.2026: im Markt 100 % 3x S&P 500, ohne Bitcoin (SPX_WEIGHT; < 1 = Rest 1x Bitcoin).
#  Single Source of Truth fuer alle Parameter und Anzeigen.
#
#  EINE Maschine, taegliche Entscheidung auf USD-1x-Schlusskursen, drei Zustaende:
#     MARKT  =  S&P 500 Total Return (^SP500TR) > SMA220   UND   US-TIPS (TIP) > SMA180
#               -> 100 % 3x-S&P 500   (optional mit 1x-Bitcoin-Anteil ueber SPX_WEIGHT)
#     IEF    =  (ab 28.10.2026) US-TIPS (TIP) < SMA180   UND   US-Treasury 20y+ (TLT) > SMA200
#               -> 100 % 3x US-Treasury 7-10y (WisdomTree 3TYL, wie in levGTAA)
#     sonst  -> 100 % Cash
#  Cooldown: nach jedem Wechsel zwischen MARKT, IEF und CASH sind die naechsten 10 Handelstage gesperrt
#  (frueheste Gegenbewegung am 11. Handelstag) — exakt wie im Backtest.
#  Zeitplan: Signal = Schlusskurs Tag d, Handel = Tag d+1.
#
#  Referenz-Backtest (alte Regel ohne IEF) mit 75 % 3x-S&P 500 / 25 % 1x-Bitcoin:
#  Backtest 1987+: CAGR 30,1 %, MaxDD -50 %, Sortino 0,93, z31 2,85, z4 3,02,
#     P(DD<-50 %) 7,7 %, P(DD<-75 %) 0 %; BTC ohne Drift 27,2 % / Sortino 0,85.
#  Realistische Erwartung eher 26-28 % (Laengenwahl nur schwach vorhersagbar).
#  KEINE ANLAGEBERATUNG.
# ============================================================================
STRAT_NAME = "levSpyBits"
STRAT_ASCII = "levSpyBits"

SPY_SMA = 220                     # ab Entscheidung 30.11.2026 (vorher 280), siehe unten
TIPS_SMA = 180                    # ab Entscheidung 30.11.2026 (vorher 220), siehe unten
TLT_SMA = 200                     # IEF-Zustand: TIPS < SMA_TIPS und TLT > SMA200
# Parameter 28.11.2026 (Langzeitpruefung 1987-2026, ab 2001 echte TIPS; Dashboard-Repo studien/STUDIE.md):
#  - Das Zickzack im Ergebnis ueber die SMA-Laenge (z. B. Delle bei TIPS 200) wiederholt sich zwischen unabhaengigen
#    Zeitraeumen nicht (Korrelation ~0) -> Rauschen einzelner Episoden; bewertet wird der geglaettete Verlauf.
#  - Das Optimum wandert mit den Marktphasen -> Auswahl nach Minimax-Regret ueber 1987-2000 / 2001-08 / 2009-17 /
#    2018-26 (in keiner Phase weit vom Bestwert), ohne katastrophale Drawdowns in der Umgebung.
#  S&P 220: beste Sharpe, kleinster Rueckstand und kleinster MaxDD, 30 Tage ueber der Klippe 170-200 (2000-03 bis -80 %).
#  TIPS 180: gesamt flach 150-200; 1987-2000/2009-17 wollen ~200, 2018-26 ~150 -> Mitte 180.
#  TLT 200 (Zacken, geglaettet flach), Cooldown 10 (Mitte 8-12).
COOLDOWN_DAYS = 10
# Stichtag: Entscheidungen auf Schlusskursen vor PARAM_SWITCH mit den alten Linien (so wurde gehandelt), ab dann
# 220/180. Am Stichtag zeigen alte und neue Regel denselben Zustand (Cash) -> kein Handel durch die Umstellung.
PARAM_SWITCH = "2026-11-30"
OLD_SMA = (280, 220)              # (S&P, TIPS) fuer Entscheidungen bis 27.11.2026

# Anteil 3x S&P 500 im Markt; der Rest (1 - SPX_WEIGHT) waere 1x Bitcoin. 1.0 = nur S&P 500, kein Bitcoin.
SPX_WEIGHT = 1.0
MARKET_ASSETS_TEXT = ("100 % 3x S&P 500" if SPX_WEIGHT >= 1 else
                      f"{SPX_WEIGHT:.0%} 3x S&P 500 + {1 - SPX_WEIGHT:.0%} 1x Bitcoin".replace("%", " %"))

SPY_TICKER = "^SP500TR"
TIPS_TICKER = "TIP"
TLT_TICKER = "TLT"                # Signal fuer den IEF-Zustand (adjustiert, USD; wie das Anleihe-Signal in levGTAA)
BTC_TICKER = "BTC-USD"            # nur Info, kein Signal (nur geladen, wenn SPX_WEIGHT < 1)

SPY_PRODUCT = "WisdomTree S&P 500 3x Daily Leveraged (3USL)"
SPY_ISIN = "IE00B7Y34M31"
BTC_PRODUCT = "1x-Bitcoin-ETP"
IEF_PRODUCT = "WisdomTree US Treasuries 10Y 3x Daily Leveraged"
IEF_ISIN = "IE00BKT09032"
IEF_TEXT = "3x US-Treasury 7-10y (IEF)"

TRY_COUNT = 3
GRID_START = "1990-01-02"
STATUS_FILE = "letsgo_status.json"          # Dateiname bleibt (Dashboard-Kompatibilitaet)
NOTIFY_FILE = "notify_state_levspybits.json"
HISTORY_FILE = f"history_{SPY_SMA}_{TIPS_SMA}_{COOLDOWN_DAYS}_USD.txt"
INFO_FOOTER = "Hebel-ETPs: Pfad-/Emittentenrisiko. KEINE ANLAGEBERATUNG."

# Datenpruefung: Mindestanzahl Kurse je Signalreihe (Strategie braucht SMA/Momentum-Fenster + Reserve). Beginnt eine Reihe
# spaeter als beim letzten Lauf (abgeschnittene Yahoo-Antwort), wird ebenfalls nicht entschieden (Retry).
MIN_ROWS = 1000
