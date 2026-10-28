# levSpyBits (wikifolio: levTipsRegime) — Signalbot

Discord- und ntfy-Signalbot (GitHub Actions) für die freigegebene **levSpyBits**-Strategie (Stand 29.09.2026).
**KEINE ANLAGEBERATUNG.**

## Strategie (eine Maschine, täglich, drei Zustände)
- **MARKT**, wenn **S&P 500 Total Return (`^SP500TR`) > SMA280** **und** **US-TIPS (`TIP`) > SMA220** →
  **3x S&P 500 + 1x Bitcoin** (Bitcoin nur im Markt, kein Buy & Hold).
- **3x IEF (neu ab 28.10.2026)**, wenn **US-TIPS (`TIP`) < SMA220** **und** **US-Treasury 20y+ (`TLT`) > SMA200** →
  **100 % WisdomTree US Treasuries 10Y 3x Daily Leveraged** (3TYL, IE00BKT09032; dasselbe Produkt wie in levGTAA).
- **Sonst 100 % Cash** (z. B. TIPS über der Linie, aber S&P darunter; oder TIPS und TLT beide unter der Linie).
- **Gewichtung frei (seit 17.10.2026):** Bot, ntfy, Discord und Dashboard nennen im Markt nur die beiden Assets,
  ohne Prozentangabe. Die Aufteilung zwischen 3x S&P 500 und 1x Bitcoin legst du selbst fest.
- **Cooldown 10:** Nach jedem Wechsel (zwischen allen drei Zuständen) sind die nächsten 10 Handelstage gesperrt; der
  früheste nächste Wechsel ist am 11. Handelstag möglich (exakt wie im Backtest).
- **Zeitplan:** Signal = Schlusskurs Tag d, Handel an Tag d+1.
- Bitcoin-Kurs nur als Info, kein Signal.
- **Signalquellen = Backtest:** `^SP500TR` (S&P 500 Total Return, USD), `TIP` (iShares TIPS, adjustiert, USD) und für den
  IEF-Zustand `TLT` (iShares 20+ Year Treasury, adjustiert, USD — wie das Anleihe-Signal in levGTAA).
- **Push (ntfy):** bei jedem echten Wechsel — „BUY – heute in den Markt“, „WECHSEL – heute in 3x IEF“, „SELL – heute in Cash“.

**Prüfung der IEF-Erweiterung (28.10.2026):** Bot-Maschine gegen eine unabhängige Nachrechnung über 9.273 Handelstage:
0 Abweichungen; nach jedem Wechsel genau 10 Sperrtage; ohne den IEF-Zweig ist die Maschine identisch zur alten Regel.
Anteil der Tage seit 10/2004: Markt 63,8 %, 3x IEF 6,7 %, Cash 29,4 %.

Referenz-Backtest mit 75 % 3x S&P 500 / 25 % 1x Bitcoin (nur Referenz, keine Vorgabe) 1987+: CAGR 30,1 %, MaxDD −50 %, Sortino 0,93, z31 2,85, z4 3,02, P(DD<−50 %) 7,7 %, P(DD<−75 %) 0 %;
Bitcoin ohne Drift 27,2 % / Sortino 0,85. Realistische Erwartung eher 26–28 %.

**Geprüft:** Die Bot-Maschine ist ab Oktober 2004 Tag für Tag identisch mit der Backtest-Maschine (5.448 Handelstage,
0 Abweichungen; vorher nur Anlaufphase, weil die TIP-Historie erst 2003 beginnt).

## Was sich gegenüber der alten Version geändert hat
- SMA160/160 → **SMA280 (S&P) / SMA220 (TIPS)**, Freeze 15 → **Cooldown 10**.
- Cooldown-Zählung korrigiert: Die alte Version erlaubte den nächsten Wechsel einen Tag früher als der Backtest
  („Freeze 15“ entsprach dort 14 Sperrtagen).
- Die Allokation wird bei jedem Lauf aus der vollen Historie neu berechnet (deterministisch, gleich dem Backtest).
- **ntfy nur bei tatsächlichem Handel:** Vergleich mit der zuletzt gemeldeten Allokation (`notify_state_levspybits.json`).
  Damit gibt es keine Doppelmeldungen am Wochenende oder bei Retries und keinen verpassten Wechsel, wenn Yahoo einen Tag
  zu spät liefert. ntfy nur mit frischen Daten.
- **ntfy nur an echten Handelstagen (NYSE):** Wechsel auf den Freitagsschluss → Push am Montagmorgen („heute handeln“),
  nicht am Samstag. Discord zeigt am Wochenende „⏳ Wechsel … — handeln am …“. Fehlen am Handelstag frische Daten, holt
  der nächste Handelstag die Meldung nach („verspätet“). Zustand wird erst nach erfolgreichem Push gespeichert.
- **Cooldown-Zähler robust:** Rechengitter = NYSE-Handelstage. Fehlt bei Yahoo ein Tag (^SP500TR oder TIP), bleibt der
  Tag im Gitter (letzter Kurs fortgeschrieben) und der Cooldown zählt ihn mit — der alte Fehler (Schnittmenge der
  Kursdaten → fehlender Tag fiel raus → Zähler „hing“ einen Tag) ist behoben (Test: `t_cool.py`).
- Schmale, handytaugliche Nachricht; Datenprüfung (letzter Kurs, Lücken, Sprünge > 30 %).
- `letsgo_status.json` enthält jetzt auch Allokation, Cooldown und die letzten 120 Handelstage für den Zeitbalken im
  Dashboard. Im Markt steht dort `"weight": null` je Asset und `"weightFree": true` (Gewichtung offen).

## Dateien
```
main.py / send_ntfy.py
strategies/constants.py      ALLE Parameter
strategies/levspybits.py     Kern + Runner
strategies/common.py         Kalender, Download, Datenprüfung (gleich in allen Bots)
.github/workflows/notify2.yaml
letsgo_status.json, history_280_220_10_USD.txt (Spalten: Datum, S&P, TIPS, S&P-SMA, TIPS-SMA, Cooldown, Zustand, TLT, TLT-SMA),
notify_state_levspybits.json  (vom Bot geschrieben)
```
Secrets: `DISCORD_WEBHOOK_URL`, `NTFY_TOPIC` (optional `NTFY_SERVER`), `PAT_PUSH`. Workflow permissions: Read and write.

## Ausfallsicherheit und Datenprüfung (Stand 29.09.2026)
- **Vor jeder Berechnung** je Kursreihe: Datum des letzten Kurses (US: zuletzt erwartete NYSE-Sitzung; Sensex/Xetra/FX:
  max. 4 Kalendertage alt), fehlende Handelstage, Sprünge > 30 %, Mindestlänge der Historie und Vergleich des
  Historienbeginns mit dem letzten Lauf (abgeschnittene Yahoo-Antwort), bei Indizes Schluss = Vortag (Platzhalter).
- **Keine Entscheidung und keine ntfy**, wenn eine Prüfung fehlschlägt (veraltet, abgeschnitten, unplausibler Sprung am
  jüngsten Tag, Kalender nicht ladbar): `needsRetry` → 2 Wiederholungen im Abstand von 30 Min, zusätzlich
  **Sicherheitslauf 11:47 UTC** (läuft nur, wenn der Morgenlauf nicht erfolgreich war). Fehlt bei einem US-Signal der
  jüngste Tag, rechnet der Bot nur bis zum letzten gemeinsamen Tag (keine fortgeschriebenen Kurse als Entscheidungsbasis).
- **Download fehlgeschlagen**: kein Handel, keine ntfy; letzter gültiger Stand bleibt im Dashboard (Handelsanweisung wird
  entfernt), Discord meldet den Fehler. Der nächste erfolgreiche Lauf rechnet alles aus der vollen Historie neu (auch den
  Cooldown) und holt eine fällige ntfy-Meldung am nächsten Handelstag nach („verspätet“).
- **Workflow-Fehler** (Installation/Start): Discord bekommt eine Fehlermeldung; Discord- und Commit-Schritt laufen immer
  (`if: always()`), Push mit 3 Versuchen — der ntfy-Zustand geht nicht verloren (keine Doppelmeldung).
- **Erststart/verlorener Zustand**: Ist ein Wechsel noch nicht gehandelt, wird er trotzdem gemeldet.
- Ist dauerhaft kein `NTFY_TOPIC` gesetzt, gilt die Meldung als erledigt (nur Discord), statt täglich „verspätet“ zu wiederholen.
