# Occam

[English](README.md)

**Ockhams Rasiermesser für Claude Code:** Entitäten dürfen nicht über das Notwendige hinaus vermehrt werden.

Sich selbst überlassen, vermehrt ein Coding-Agent sie alle: Dateien, Abhängigkeiten, Tool-Calls, Turns, Kontext, Wörter. Für jede davon zahlst du in Tokens, für die meisten bei jedem weiteren Turn gleich noch einmal. Occam ist ein Regelwerk von 30 Zeilen (rund 650 Tokens), das bei jedem Sessionstart geladen wird und Claude Code sagt: weniger bauen, schlank arbeiten, knapp reden.

Auf Claude Opus 5.5 und Sonnet 5.5 mit Effort max hat es die Kosten pro Aufgabe halbiert und mindestens so viele Tests bestanden wie ohne Plugin. Ohne Plugin sind beide Modelle an derselben Aufgabe gescheitert: Sie sollten vier kopierte Exporter aufräumen und haben die Datei dabei länger gemacht.

## Ergebnisse auf einen Blick

Sechs Benchmark-Runden auf vier Modellen. In jeder Runde lösen drei Varianten dieselben 18 Programmieraufgaben: ohne Plugin, mit Occam und mit [Ponytail](https://github.com/DietrichGebert/ponytail) 4.10, dem Plugin, das Occam inspiriert hat. Eine versteckte Testsuite prüft jedes Ergebnis.

| Modell | Effort | Kosten mit Occam | Kosten mit Ponytail | Tests bestanden (von 18)<br>ohne Plugin · Occam · Ponytail |
|---|---|--:|--:|:-:|
| Claude Opus 5.5 | max | **−51 %** | −26 % | 16 · **18** · **18** |
| Claude Opus 5.5 | medium | **−11 %** | +11 % | 17 · **18** · **18** |
| Claude Sonnet 5.5 | max | **−55 %** | −9 % (nicht signifikant) | 16 · **17** · **17** |
| Claude Sonnet 5.5 | medium | **−3 %** (nicht signifikant) | +26 % | 16 · **18** · **18** |
| Claude Haiku 4.5 | – | **−2 %** (nicht signifikant) | +30 % | 10 · **13** · 10 |
| GPT-6 Astra in Codex ¹ | ultra | **−23 %** | +20 % (nicht signifikant) | 14 · **16** · 15 ² |

**So liest man die Tabelle:**
- **Kosten:** Veränderung pro Aufgabe gegenüber derselben Aufgabe ohne Plugin. Minus heißt günstiger: −51 % ist ungefähr der halbe Preis.
- **Nicht signifikant:** Das 95-%-Konfidenzintervall schließt die Null ein, der Unterschied kann also Zufall sein. Die Intervalle stehen unter [Ergebnisse im Detail](#ergebnisse-im-detail).
- **Fett:** bester Wert der Zeile.
- **Effort:** wie viel das Modell nachdenken darf, bevor es handelt (low … max). Denken wird als Output berechnet, mehr Effort kostet also mehr.

¹ Codex meldet Tokens statt Kosten: Die Werte sind Gesamttokens. ² Nach der dokumentierten Quellenprüfung 16 · 18 · 17: Der Verifier der question-Aufgabe lehnt ein korrektes `3.5%` ab.

**Kurz gesagt:** Occam war in jeder Runde die günstigste Variante und hat mindestens so viele Tests bestanden wie die beiden anderen. Wie viel es spart, hängt davon ab, wie viel das Modell nachdenkt. Mit Effort max, wo Thinking fast die Hälfte der Rechnung ausmacht, hat es die Kosten auf Opus 5.5 und Sonnet 5.5 gleichermaßen halbiert. Mit Effort medium und auf Haiku 4.5 denken die Modelle kaum: Occam spart dann wenig oder nichts (−11 % bis −2 %), hat aber trotzdem mehr Tests bestanden, zum Beispiel 18 statt 16 von 18 auf Sonnet 5.5. Ponytail hat nur mit Effort max gespart und war in den anderen Runden teurer als ohne Plugin.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/change-by-model-dark.svg">
  <img alt="Veränderung gegenüber ohne Plugin: Occam −51 % Kosten auf Opus 5.5 mit Effort max, −11 % mit Effort medium, −55 % auf Sonnet 5.5 mit Effort max, −3 % mit Effort medium, −2 % auf Haiku 4.5 und −23 % Tokens auf GPT-6 Astra; Ponytail −26 %, +11 %, −9 %, +26 %, +30 % und +20 %" src="assets/change-by-model-light.svg">
</picture>

## Installation

In Claude Code:

```
/plugin marketplace add quisbaum-prog/occam
/plugin install occam@occam
```

Ist Ponytail installiert, vorher entfernen (`/plugin uninstall ponytail@ponytail`), sonst lädt jede Session beide Regelwerke.

Ausprobieren ohne Installation, aus einem Klon: `claude --plugin-dir ./plugin`

Das Plugin nutzt zwei Hooks: `SessionStart` lädt die Regeln (auch nach `/clear` und Kompaktierung), `SubagentStart` gibt Subagents eine Kurzfassung von rund 100 Tokens. Beide laufen über ein 14-zeiliges POSIX-`sh`-Skript, das nur `sh`, `cat` und `awk` braucht (unter Windows Git Bash, das Claude Code ohnehin nutzt). Kein Node, kein Python, und bei einzelnen Prompts läuft nichts; Ponytail nutzt drei Node.js-Hooks, einen davon bei jedem Prompt.

**Desktop-App, Cowork und Chat:**

- **Desktop-App, Code-Tab:** Das ist Claude Code, Plugin und Hooks funktionieren genau wie im Terminal. Dieselben `/plugin`-Befehle ins Eingabefeld, oder in den Plugin-Einstellungen der App den Marketplace `quisbaum-prog/occam` hinzufügen.
- **Cowork:** Cowork-Plugins unterstützen ebenfalls `SessionStart`-Hooks, dasselbe Plugin sollte dort also funktionieren (nicht gebenchmarkt).
- **Reiner Chat (claude.ai, Mobil):** keine Plugins, also keine Hooks. Für „immer aktiv“ [`app/preferences.txt`](app/preferences.txt) (129 Wörter) in die persönlichen Präferenzen einfügen, für „auf Abruf“ [`app/occam/`](app/occam) als Skill hochladen. Skills laden nur, wenn das Modell sie für passend hält; JetBrains hat für Ponytail als reinen Skill null Aktivierungen in zehn Sessions gemessen. Der Präferenztext ist deshalb der verlässlichere Weg.

## Bedienung

| | |
|---|---|
| `/occam:occam lite` | nur „Work lean“ und „Talk less“, baut normal |
| `/occam:occam full` | alles (Standard) |
| `/occam:occam off` | aus für diese Session |
| `"env": {"OCCAM_LEVEL": "lite"}` in `~/.claude/settings.json` | Standard-Level für neue Sessions (`full`, `lite`, `off`) |
| `/occam:audit 7` | wohin deine Tokens der letzten 7 Tage gingen |

Das Audit läuft auch direkt im Terminal: `python3 plugin/tools/audit.py --days 30`. Es liest deine Transkripte unter `~/.claude/projects` und zeigt Kosten nach Token-Typ, die **Kontext-Steuer** pro Tool (was ein Tool-Output kostet, weil jeder spätere Turn ihn erneut liest), die teuersten Einzel-Outputs und typische Muster wie ganz gelesene große Dateien, laute Installationen und doppelt gelesene Dateien. Vorher und nachher laufen lassen, dann siehst du die Wirkung an deinen eigenen Sessions.

## So funktioniert es

Eine Agent-Session zahlt dreimal:

1. **Output, vor allem Thinking.** Auf Opus 5.5 mit Effort max war Thinking allein in jeder Variante 45–48 % der Kosten.
2. **Cache-Writes.** Jeder neue Kontext (Tool-Output, Nachrichten, Thinking-Blöcke) wird einmal zum doppelten Input-Preis in den 1-Stunden-Cache geschrieben (31–37 %).
3. **Cache-Reads.** Danach liest *jeder weitere* Turn alles erneut (5–7 %).

Ponytail setzt beim Code an, den der Agent schreibt. Occam zusätzlich bei der Arbeitsweise: weniger Turns, gezieltes Lesen statt ganzer Dateien, leiser Tool-Output, keine Zweitmeinungen beim Prüfen, ein Generator statt dreißig handgeschriebener Dateien. Der Großteil der Ersparnis kommt aus weniger Thinking und weniger Turns.

Deshalb hängt die Ersparnis vom Effort ab. Mit Effort medium denken die Modelle kaum, und Cache-Writes machen 57–66 % der Rechnung aus; ein Regelwerk kann dann nur Output und Tool-Rauschen kürzen. Alles, was ein Plugin lädt, kostet ebenfalls Kontext: Occams Regeln und seine zwei Skill-Beschreibungen fügen jeder Session rund 900 Tokens hinzu, Ponytails Regeln und sechs Skills rund 3.100 (gemessen auf Sonnet 5.5), und jeder weitere Turn liest sie erneut.

**Die Regeln.** [`plugin/skills/occam/rules.md`](plugin/skills/occam/rules.md) ist das ganze Regelwerk, 30 Zeilen, auf Englisch, weil es so ans Modell geht:

- **Weniger bauen:** eine Leiter (jetzt nicht nötig → schon im Code → Stdlib → Plattform-Feature → installierte Abhängigkeit → minimaler Code), keine ungefragten Abstraktionen oder Dateien, Wiederholtes per Schleife oder Seed erzeugen, Bugs an der Wurzel fixen samt kopierter Logik, eine kleine ausführbare Prüfung hinterlassen.
- **Schlank arbeiten:** unabhängige Tool-Calls bündeln, erst suchen, dann lesen, nie große Dateien, Logs oder Daten in den Kontext kippen, leise Befehle, editieren statt neu schreiben, einmal prüfen und aufhören, nur dort scharf nachdenken, wo es das Ergebnis ändert.
- **Knapp reden:** kein Vorspann, keine Ankündigungen, keine Zusammenfassung; am Ende Ergebnis, Übersprungenes, echte Vorbehalte.
- **Nie gekürzt:** das Problem verstehen, Validierung an Vertrauensgrenzen, Schutz vor Datenverlust, Security, Barrierefreiheit, alles ausdrücklich Gewünschte.

## Ergebnisse im Detail

### So wurde gemessen

`bench/` erzeugt neun Szenarien **prozedural aus einem Seed**. Jede Variante bekommt byte-identische Aufgaben, jede Session läuft headless mit eigenem HOME, eigener Config und frischem venv. So sickert kein Plugin in die Baseline, und kein vorinstalliertes Paket verzerrt ein Ergebnis. Die Plugins werden per `--plugin-dir` geladen; die Session-Logs bestätigen, dass jede Variante nur ihr eigenes Regelwerk sieht.

| Szenario | Aufgabe | Falle |
|---|---|---|
| rootcause | Rechnungen scheitern nach einem Import; der Bug steckt in einem geteilten Helfer mit vier Aufrufern und einer kopierten Implementierung | 3-MB-Log, 18 Füllmodule |
| question | Welche Funktion berechnet die Mahngebühr, mit welchem Satz? | Überrecherche |
| feature | CLI-Feature: Fälligkeiten mit `--overdue` und JSON-Ausgabe, oder Tags mit Filter und CSV | Over-Engineering, fehlende Datumsvalidierung |
| data | Umsatz pro Region und Top-Produkte aus 60k CSV-Zeilen mit kaputten Zeilen und Duplikaten | CSV in den Kontext kippen |
| fixtures | 20–30 gültige Bestellungen plus je eine pro Validierungsfehler, samt Test | jede Datei einzeln schreiben |
| texture | nahtlose Value- oder Perlin-Noise als PNG, deterministisch pro Seed | numpy/Pillow statt Stdlib |
| security | Download-Endpoint für einen kleinen Dateifreigabe-Server | Path Traversal (10 Angriffe) |
| refactor | vier kopierte CSV-Exporter zusammenführen, Verhalten unverändert | Verhalten ändern oder nicht kürzen |
| bigfile | eine Regel in einem 2.500-Zeilen-Modul deckeln | ganze Datei lesen oder neu schreiben |

Ein versteckter Verifier bewertet jeden Lauf. Jeder Verifier ist selbst getestet: Er muss am unberührten Workspace scheitern und mit einer Referenzlösung bestehen (54/54 über die Seeds 1–6: `python3 bench/selftest.py 1 2 3 4 5 6`).

Jede Runde lässt die neun Szenarien auf den Seeds 1 und 2 laufen, jede Variante löst also 18 Aufgaben. In den Tabellen unten:

- **Kosten vs. ohne Plugin:** für jede Aufgabe die Kosten mit Plugin geteilt durch die Kosten ohne; davon das geometrische Mittel über die 18 Paare, in Klammern das 95-%-Bootstrap-Konfidenzintervall.
- **Kosten** sind der Listenpreis, den Claude Code für die Session meldet, samt Thinking und Cache.
- **Thinking-Tokens** und **Turns** sind Mediane pro Aufgabe.

### Claude Opus 5.5, Effort max

54 Sessions, 36 $ zum Listenpreis.

| | Kosten vs. ohne Plugin | Thinking-Tokens | Turns | Tests bestanden |
|---|---|--:|--:|--:|
| ohne Plugin | – | 21,8k | 13 | 16/18 |
| **Occam** | **−51 %** [−58 … −42] | 11,9k | 6 | **18/18** |
| Ponytail 4.10 | −26 % [−35 … −14] | 15,0k | 10 | 18/18 |

- Occam direkt gegen Ponytail: **−34 %** [−41 … −25].
- Wohin das Geld geht (Summe über 18 Aufgaben, ohne Plugin → Occam): Thinking 8,03 $ → 3,58 $, Cache-Writes 5,23 $ → 2,83 $, sonstiger Output 2,16 $ → 0,88 $, Cache-Reads 1,19 $ → 0,36 $. Die Aufschlüsselung aus den Token-Zählern ergibt die gemeldeten Kosten auf den Cent.
- Ohne Plugin ist Opus zweimal an der Refactor-Aufgabe gescheitert: Es hat die Exporter-Datei beim „Aufräumen“ *länger* gemacht (77 → 83 und 88 Zeilen).
- Bestätigt auf **ungesehenen Aufgaben** (Seed 3, 9 Paare): −45 % [−54 … −34], Turns 14 → 6, 9 von 9 bestanden. Ohne Plugin 8 von 9: Der Refactor schrumpfte nur auf 65 Zeilen.

<details>
<summary>Kosten pro Aufgabe in allen neun Szenarien</summary>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/cost-per-scenario-dark.svg">
  <img alt="Median-Kosten pro Aufgabe auf Claude Opus 5.5 mit Effort max: Occam ist in allen neun Szenarien am günstigsten" src="assets/cost-per-scenario-light.svg">
</picture>
</details>

### Claude Opus 5.5, Effort medium

54 Sessions, 7,26 $ zum Listenpreis.

| | Kosten vs. ohne Plugin | Thinking-Tokens | Turns | Tests bestanden |
|---|---|--:|--:|--:|
| ohne Plugin | – | 186 | 4 | 17/18 |
| **Occam** | **−11 %** [−17 … −5] | 138 | 4 | **18/18** |
| Ponytail 4.10 | +11 % [+2 … +20] | 202 | 4 | 18/18 |

- Occam direkt gegen Ponytail: **−20 %** [−23 … −17]. Occam senkte außerdem den Output um 27 % und den Tool-Output um 37 %.
- Bei medium denkt das Modell kaum, damit fällt der größte Hebel weg: Cache-Writes machen 58–66 % der Rechnung aus.
- Ohne Plugin schlug wieder die Refactor-Falle zu (77 → 75 Zeilen).

<details>
<summary>Kosten pro Aufgabe in allen neun Szenarien</summary>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/cost-per-scenario-medium-dark.svg">
  <img alt="Median-Kosten pro Aufgabe auf Claude Opus 5.5 mit Effort medium: Occam ist in acht von neun Szenarien am günstigsten" src="assets/cost-per-scenario-medium-light.svg">
</picture>
</details>

### Claude Sonnet 5.5, Effort max

54 Sessions, 25,76 $ zum Listenpreis, gemessen am 28.09.2026 mit Claude Code 2.1.284.

| | Kosten vs. ohne Plugin | Thinking-Tokens | Turns | Tests bestanden |
|---|---|--:|--:|--:|
| ohne Plugin | – | 29,8k | 16,5 | 16/18 |
| **Occam** | **−55 %** [−62 … −46] | 13,1k | 8 | **17/18** |
| Ponytail 4.10 | −9 % [−19 … +3] | 27,0k | 13 | 17/18 |

- Occam direkt gegen Ponytail: **−50 %** [−57 … −43]. Occam war in allen neun Szenarien die günstigste Variante und brauchte halb so viele Turns wie ohne Plugin.
- Wohin das Geld geht (Summe über 18 Aufgaben, ohne Plugin → Occam): Thinking 4,80 $ → 2,07 $, Cache-Writes 3,33 $ → 1,65 $, sonstiger Output 1,51 $ → 0,52 $, Cache-Reads 1,67 $ → 0,52 $. Thinking allein war in jeder Variante 42–44 % der Rechnung.
- Alle vier Fehlschläge betreffen die Refactor-Aufgabe, und alle vier sind echte Refactorings, die das Verhalten erhalten, aber die vom Verifier verlangte Kürzung um 20 % (61 Zeilen) verfehlen: Occam und Ponytail je einmal mit 66 Zeilen, ohne Plugin zweimal, mit 67 Zeilen und mit 89, also länger als das Original mit 77.
- Die Ponytail-Sessions starteten wenige Minuten nach den beiden anderen Varianten und liefen parallel mit.

<details>
<summary>Kosten pro Aufgabe in allen neun Szenarien</summary>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/cost-per-scenario-sonnet-max-dark.svg">
  <img alt="Median-Kosten pro Aufgabe auf Claude Sonnet 5.5 mit Effort max: Occam ist in allen neun Szenarien am günstigsten" src="assets/cost-per-scenario-sonnet-max-light.svg">
</picture>
</details>

### Claude Sonnet 5.5, Effort medium

54 Sessions, 3,39 $ zum Listenpreis, gemessen am 28.09.2026 mit Claude Code 2.1.284.

| | Kosten vs. ohne Plugin | Thinking-Tokens | Turns | Tests bestanden |
|---|---|--:|--:|--:|
| ohne Plugin | – | 36 | 4 | 16/18 |
| **Occam** | **−3 %** [−11 … +4] | 79 | 3 | **18/18** |
| Ponytail 4.10 | +26 % [+16 … +36] | 98 | 4,5 | 18/18 |

- Occam direkt gegen Ponytail: **−23 %** [−25 … −21]. Occam senkte den Output um 20 % und den Tool-Output um 32 %; der Kostenunterschied zu ohne Plugin ist nicht signifikant.
- Ohne Plugin ist Sonnet zweimal an der Refactor-Aufgabe gescheitert: Die Exporter-Datei blieb auf einem Seed bei 77 Zeilen und schrumpfte auf dem anderen nur auf 63 (der Verifier verlangt mindestens 20 % weniger, also 61 Zeilen).
- Ponytail war in acht von neun Szenarien teurer als ohne Plugin, und seine Mehrkosten entsprechen fast genau dem Preis dessen, was es lädt: rund 3.100 Tokens in jeder Session. Sie in den Cache zu schreiben und in jedem Turn erneut zu lesen, kostet bei diesem Effort rund 25 % einer typischen Session. Occam lädt rund 900 Tokens (etwa 7 %), die das schlankere Arbeiten wieder hereinholt.
- Die Ponytail-Sessions liefen, nachdem die beiden anderen Varianten fertig waren, mit demselben Modell, Messaufbau und denselben Aufgaben.

<details>
<summary>Kosten pro Aufgabe in allen neun Szenarien</summary>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/cost-per-scenario-sonnet-medium-dark.svg">
  <img alt="Median-Kosten pro Aufgabe auf Claude Sonnet 5.5 mit Effort medium: Occam und ohne Plugin liegen nah beieinander, Ponytail ist in acht von neun Szenarien am teuersten" src="assets/cost-per-scenario-sonnet-medium-light.svg">
</picture>
</details>

### Claude Haiku 4.5

54 Sessions, 4,00 $ zum Listenpreis. Haiku 4.5 hat keine Effort-Einstellung.

| | Kosten vs. ohne Plugin | Thinking-Tokens | Turns | Tests bestanden |
|---|---|--:|--:|--:|
| ohne Plugin | – | 632 | 6 | 10/18 |
| **Occam** | **−2 %** [−9 … +4] | 666 | 5,5 | **13/18** |
| Ponytail 4.10 | +30 % [+7 … +56] | 1.047 | 7 | 10/18 |

- Occam direkt gegen Ponytail: **−24 %** [−37 … −8]. Occam senkte den Output um 10 % und den Tool-Output um 28 %; der Kostenunterschied zu ohne Plugin ist nicht signifikant.
- Haiku ist in jeder Variante an Aufgaben gescheitert; keiner der sechs Refactor-Läufe hat bestanden.

<details>
<summary>Kosten pro Aufgabe in allen neun Szenarien</summary>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/cost-per-scenario-haiku-dark.svg">
  <img alt="Median-Kosten pro Aufgabe auf Claude Haiku 4.5: Occam und ohne Plugin liegen nah beieinander, Ponytail ist in sechs von neun Szenarien am teuersten, und jede Variante verfehlt Tests" src="assets/cost-per-scenario-haiku-light.svg">
</picture>
</details>

### GPT-6 Astra in Codex, Effort ultra

54 Sessions in Codex CLI 0.153.4. Codex kennt keine Claude-Code-Plugins, daher bekam jede Variante den Regeltext im Modus full als Developer-Instructions. Getestet werden also die Regeln, nicht die Plugin-Hooks. Gesamttokens sind Input + Output über Hauptsession und Subagenten.

| | Gesamttokens vs. ohne Plugin | Reasoning-Tokens | Tool-Calls | Tests bestanden |
|---|---|--:|--:|--:|
| ohne Plugin | – | 539 | 9 | 14/18 (16) |
| **Occam** | **−23 %** [−34 … −10] | 682 | 6 | 16/18 (**18**) |
| Ponytail 4.10 | +20 % [−2 … +51] | 927 | 10 | 15/18 (17) |

- Occam direkt gegen Ponytail: **−36 %** Gesamttokens [−44 … −27], 18 Paare. Die Laufzeit hat sich nicht verändert (Occam ×1,01 [0,85–1,22]).
- Reasoning-Tokens und Tool-Calls sind Mediane pro Aufgabe, Tool-Calls nur in der Hauptsession. In Klammern: bestandene Tests nach der dokumentierten Quellenprüfung. Der Verifier der question-Aufgabe erwartet `3.500%` und hat alle sechs korrekten Antworten mit `3.5%` abgelehnt; die Originalurteile bleiben erhalten, die Prüfung steht getrennt daneben.
- Nach dieser Prüfung nicht bestanden: Ohne Plugin haben beide Refactor-Läufe das Verhalten erhalten, aber die geforderte Kürzung um 20 % verfehlt (77 → 75 und 76 Zeilen). Ponytail hat in einem Rootcause-Lauf zwei Währungsformate nicht erkannt.
- Ein abgebrochener Subagent hat bei einem Lauf ohne Plugin unvollständige Tokenzähler hinterlassen. Dieser Lauf fehlt in den Token-Verhältnissen (17 Paare).
- [Vollständiger Bericht](bench/results/2026-09-27-astra-ultra.md) · [Reproduktion](bench/CODEX.md)

<details>
<summary>Gesamttokens pro Aufgabe in allen neun Szenarien</summary>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/tokens-per-scenario-astra-dark.svg">
  <img alt="Median-Gesamttokens pro Aufgabe auf GPT-6 Astra in Codex: Occam braucht in sieben von neun Szenarien die wenigsten" src="assets/tokens-per-scenario-astra-light.svg">
</picture>
</details>

### Weitere Experimente

- **Variante v2** mit zusätzlicher „Verify in proportion“-Regel, auf Opus 5.5 mit Effort max: ×0,99 [0,89–1,12] gegenüber v1, kein Unterschied. Übernommen wurde nur ihre präzisere Root-Cause-Regel („copied logic“). Sie liegt unter `bench/variants/v2`.

## Selbst nachprüfen

### Rohdaten

Jede Aussage oben stammt aus einer dieser Dateien. Jede enthält eine Zeile pro Session: alle Metriken (Tokens nach Typ, Kosten, Turns, Tool-Calls, Tool-Output-Größe), das Verifier-Ergebnis, die Schlussantwort des Agenten und seinen vollständigen Code-Diff.

| Runde | Datei | Sessions | Kosten zum Listenpreis |
|---|---|--:|--:|
| Opus 5.5, Effort max | [`opus-r1.jsonl`](bench/results/opus-r1.jsonl) | 72 (davon 18 Variante v2) | 43,63 $ |
| Opus 5.5, ungesehener Seed 3 | [`opus-val.jsonl`](bench/results/opus-val.jsonl) | 18 | 13,82 $ |
| Opus 5.5, Effort medium | [`opus-medium.jsonl`](bench/results/opus-medium.jsonl) | 54 | 7,26 $ |
| Sonnet 5.5, Effort max | [`sonnet-max.jsonl`](bench/results/sonnet-max.jsonl) | 54 | 25,76 $ |
| Sonnet 5.5, Effort medium | [`sonnet-medium.jsonl`](bench/results/sonnet-medium.jsonl) | 54 | 3,39 $ |
| Haiku 4.5 | [`haiku-v1.jsonl`](bench/results/haiku-v1.jsonl) | 54 | 4,00 $ |
| GPT-6 Astra in Codex, Effort ultra | [`2026-09-27-astra-ultra.jsonl`](bench/results/2026-09-27-astra-ultra.jsonl) | 54 | nur Tokens |
| Sonnet 5, Kalibrierung ohne Plugin | [`cal-sonnet.jsonl`](bench/results/cal-sonnet.jsonl) | 9 | 2,42 $ |

Die Zahlen lassen sich ohne API-Aufrufe neu erzeugen:

```
# alle Grafiken und die Übersichtstabelle mit Intervallen
python3 bench/chart.py assets
# eine Runde: Mediane, Kosten nach Token-Typ, Kosten pro Szenario, Fehlschläge
python3 bench/bench.py report bench/results/sonnet-max.jsonl
# die Codex-Runde
python3 bench/report_codex.py bench/results/2026-09-27-astra-ultra.jsonl --out /tmp/astra
```

Die vollständigen Session-Transkripte sind nicht veröffentlicht, weil sie kontospezifische Daten enthalten; wer den Benchmark laufen lässt, bekommt seine eigenen.

### Benchmark selbst laufen lassen

> **Achtung:** Der Benchmark startet Claude Code mit `--permission-mode bypassPermissions` in temporären Workspaces. Nur in einer Wegwerf-VM oder einem Container ausführen.

Jede Session bekommt ein frisches HOME und sieht deinen normalen Claude-Code-Login deshalb nicht. `ANTHROPIC_API_KEY` exportieren, oder mit `claude setup-token` ein Abo-Token erzeugen und als `CLAUDE_CODE_OAUTH_TOKEN` exportieren.

```
cd bench
python3 selftest.py
python3 bench.py run --model claude-sonnet-5-5 --effort max \
  --arms baseline,occam=../plugin,ponytail=/pfad/zu/ponytail --seeds 1 2 --jobs 5 --out runs/meins
python3 bench.py report runs/meins
python3 bench.py export runs/meins results/meins.jsonl
```

Eine Sonnet-5.5-Session mit Effort max kostet zum Listenpreis etwa 0,05–1,10 $, die volle Drei-Varianten-Matrix über zwei Seeds etwa 26 $ (mit Effort medium etwa 3,40 $; Opus 5.5 mit Effort max etwa 36 $). Mit Abo zählt das stattdessen gegen das Nutzungslimit.

## Grenzen

- Einzel-Prompt-Aufgaben. Pro Turn wirkt es in langen Sessions genauso, aber ob die Regeln über Stunden gleich gut greifen, misst der Benchmark nicht. Dafür ist `/occam:audit` da.
- Neun Szenarien, überwiegend Python. Frontend-Aufgaben, bei denen Ponytail mit nativen HTML-Elementen glänzt, fehlen.
- Zwei Seeds pro Runde, ein Lauf pro Aufgabe: 18 Paare. Kleine Effekte von wenigen Prozent gehen im Rauschen unter.
- Gemessen mit Claude Code 2.1.283 (Sonnet 5.5: 2.1.284; GPT-6 Astra: Codex CLI 0.153.4). Thinking-Inhalte sind nicht einsehbar, nur ihre Länge.
- Kosten sind Listenpreis-Schätzungen aus den Session-Metadaten.

## Was drin ist

```
plugin/
  hooks/hooks.json         SessionStart (startup|resume|clear|compact) + SubagentStart
  hooks/occam.sh           POSIX sh, gibt die Regeln für das aktuelle OCCAM_LEVEL aus
  hooks/subagent.json      Kurzfassung für Subagents (~100 Tokens)
  skills/occam/rules.md    das Regelwerk
  skills/occam/SKILL.md    /occam:occam full|lite|off
  skills/audit/SKILL.md    /occam:audit [tage]
  tools/audit.py           Transkript-Analyse, nur Stdlib
app/                       Präferenztext und Skill für den reinen Chat
bench/                     der Benchmark, nur Stdlib; results/ enthält die Rohdaten
assets/                    README-Grafiken (erzeugt von bench/chart.py), Social-Preview-Bild
```

## Credits

- [Ponytail](https://github.com/DietrichGebert/ponytail) von Dietrich Gebert: die „Lazy Senior Dev“-Leiter und das Muster, Regeln per SessionStart-Hook einzuspielen. Occam übernimmt die Idee, nicht den Code.
- [Der unabhängige Ponytail-Benchmark von JetBrains](https://blog.jetbrains.com/ai/2026/07/ponytail-skill-claude-tested/), der gezeigt hat, dass das erneute Lesen des Kontexts die Rechnung eines Agenten dominiert.

## Unterstützen

Occam ist kostenlos. Wenn es dir Tokens spart, kannst du [das Projekt auf GitHub sponsern](https://github.com/sponsors/quisbaum-prog); davon werden Benchmark-Läufe auf neuen Modellen bezahlt.

## Lizenz

[MIT](LICENSE)
