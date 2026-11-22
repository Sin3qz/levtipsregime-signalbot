# ============================================================================
#  levSpyBits (wikifolio: levTipsRegime) — freigegeben 29.09.2026 (Stand Backtest-Runde 16)
#  Ab 28.10.2026: im Markt 100 % 3x S&P 500, ohne Bitcoin (SPX_WEIGHT; < 1 = Rest 1x Bitcoin).
#  Single Source of Truth fuer alle Parameter und Anzeigen.
#
#  EINE Maschine, taegliche Entscheidung auf USD-1x-Schlusskursen, drei Zustaende:
#     MARKT  =  S&P 500 Total Return (^SP500TR) > SMA220   UND   US-TIPS (TIP) > SMA190
#               -> 100 % 3x-S&P 500   (optional mit 1x-Bitcoin-Anteil ueber SPX_WEIGHT)
#     IEF    =  (ab 28.10.2026) US-TIPS (TIP) < SMA190   UND   US-Treasury 20y+ (TLT) > SMA200
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

SPY_SMA = 220                     # ab 22.11.2026 (vorher 280), siehe unten
TIPS_SMA = 190                    # ab 22.11.2026 (vorher 220), siehe unten
TLT_SMA = 200                     # IEF-Zustand: TIPS < SMA_TIPS und TLT > SMA200
# Parameter 22.11.2026 aus der Langzeitpruefung 1987-2026 (ab 2001 mit echten TIPS-Reihen, Dashboard-Repo
# studien/STUDIE.md): gemeinsames Feinraster S&P x TIPS x TLT x Cooldown (1.485 Varianten), Auswahl = Mitte der
# robusten Umgebung (Mittel ueber S&P +-20, TIPS +-20, Cooldown +-3), nicht der Einzelgipfel.
#   S&P: zwei Plateaus 200-240 und 280-300; das untere ist breiter und in der Umgebung besser -> Mitte 220.
#   TIPS: flach 170-210, Kante ab 230 -> Mitte 190.   TLT: flach -> 200.   Cooldown: Mitte 10.
# 220/190 gegen 280/220: Sharpe 0,737 vs 0,724, MaxDD -56,4 vs -58,7 %, ab 2001 Sharpe 0,871 vs 0,828
# (nicht signifikant, Bootstrap P 0,61 - Wahl der Plateau-Mitte statt Randlage). Zwei oder drei Varianten
# gemischt brachten keinen signifikanten Vorteil (P 0,85 bzw. 0,79) -> eine Variante.
COOLDOWN_DAYS = 10

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
