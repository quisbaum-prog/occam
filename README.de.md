# Occam

**Token-Ökonomie für Claude Code.** Ein Regelwerk von rund 650 Tokens, das bei jedem Sessionstart geladen wird: weniger bauen, schlank arbeiten, knapp reden. Stdlib vor Abhängigkeit, generieren statt aufzählen, einmal prüfen und aufhören.

[English](README.md)

Gemessen in echten headless Claude-Code-Sessions auf **Claude Opus 5.5 mit Effort max** (18 Aufgabenpaare, 95 %-Konfidenzintervall):

| | Kosten vs. ohne Plugin | Thinking-Tokens | Turns | Tests bestanden |
|---|---|---|---|---|
| ohne Plugin | – | 21.8k | 13 | 89 % |
| **Occam** | **−51 %** [−58 … −42] | 11.9k | 6 | **100 %** |
| Ponytail 4.10 | −26 % [−35 … −14] | 15.0k | 10 | 100 % |

Occam direkt gegen Ponytail: **−34 %** Kosten [−41 … −25]. Bestätigt auf **ungesehenen Aufgaben** (Seed 3, 9 Paare): **−45 %** [−54 … −34], 9 von 9 bestanden (ohne Plugin 8 von 9). Thinking-Tokens und Turns sind Mediane pro Aufgabe.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/cost-per-scenario-dark.svg">
  <img alt="Median-Kosten pro Aufgabe auf Claude Opus 5.5: Occam ist in allen neun Szenarien am günstigsten" src="assets/cost-per-scenario-light.svg">
</picture>

## Warum das funktioniert

Eine Agent-Session zahlt dreimal:

1. **Output, vor allem Thinking.** Auf Opus 5.5 mit Effort max waren das in jedem Arm rund 47 % der Kosten.
2. **Cache-Writes.** Jeder neue Kontext (Tool-Output, Nachrichten, Thinking-Blöcke) wird einmal zum doppelten Input-Preis in den 1-Stunden-Cache geschrieben (35–42 %).
3. **Cache-Reads.** Danach liest *jeder weitere* Turn alles erneut (6–8 %).

Ponytail setzt beim Code an, den der Agent schreibt. Occam zusätzlich bei der Arbeitsweise: weniger Turns, gezieltes Lesen statt ganzer Dateien, leiser Tool-Output, keine Zweitmeinungen beim Prüfen, ein Generator statt dreißig handgeschriebener Dateien. Der Großteil der Ersparnis kommt aus halbiertem Thinking und halbierten Turns.

## Installation (Claude Code)

```
/plugin marketplace add quisbaum-prog/occam
/plugin install occam@occam
```

Ist Ponytail installiert, vorher entfernen (`/plugin uninstall ponytail@ponytail`), sonst lädt jede Session beide Regelwerke.

Ausprobieren ohne Installation, aus einem Klon: `claude --plugin-dir ./plugin`

Braucht nur `sh`, `cat` und `awk` (unter Windows Git Bash, das Claude Code ohnehin nutzt). Kein Node und kein Python für die Hooks.

## Bedienung

| | |
|---|---|
| `/occam:occam lite` | nur „Work lean“ und „Talk less“, baut normal |
| `/occam:occam full` | alles (Standard) |
| `/occam:occam off` | aus für diese Session |
| `"env": {"OCCAM_LEVEL": "lite"}` in `~/.claude/settings.json` | Standard-Level für neue Sessions (`full`, `lite`, `off`) |
| `/occam:audit 7` | wohin deine Tokens der letzten 7 Tage gingen |

Das Audit läuft auch direkt im Terminal: `python3 plugin/tools/audit.py --days 30`. Es liest deine Transkripte unter `~/.claude/projects` und zeigt Kosten nach Token-Typ, die **Kontext-Steuer** pro Tool (was ein Tool-Output kostet, weil jeder spätere Turn ihn erneut liest), die teuersten Einzel-Outputs und typische Muster wie ganz gelesene große Dateien, laute Installationen und doppelt gelesene Dateien. Vorher und nachher laufen lassen, dann siehst du die Wirkung an deinen eigenen Sessions.

## In der Claude-App (claude.ai, Desktop)

Hooks gibt es dort nicht. Zwei Wege:

- **Immer aktiv:** [`app/preferences.txt`](app/preferences.txt) (129 Wörter) in die persönlichen Präferenzen einfügen.
- **Auf Abruf:** [`app/occam/`](app/occam) als Skill hochladen. Skills laden nur, wenn das Modell sie für passend hält; JetBrains hat für Ponytail als reinen Skill null Aktivierungen in zehn Sessions gemessen. Der Präferenztext ist deshalb der verlässlichere Weg.

## Die Regeln

[`plugin/skills/occam/rules.md`](plugin/skills/occam/rules.md) ist das ganze Regelwerk, 30 Zeilen, auf Englisch, weil es so ans Modell geht:

- **Weniger bauen:** eine Leiter (jetzt nicht nötig → schon im Code → Stdlib → Plattform-Feature → installierte Abhängigkeit → minimaler Code), keine ungefragten Abstraktionen oder Dateien, Wiederholtes per Schleife oder Seed erzeugen, Bugs an der Wurzel fixen samt kopierter Logik, eine kleine ausführbare Prüfung hinterlassen.
- **Schlank arbeiten:** unabhängige Tool-Calls bündeln, erst suchen, dann lesen, nie große Dateien, Logs oder Daten in den Kontext kippen, leise Befehle, editieren statt neu schreiben, einmal prüfen und aufhören, nur dort scharf nachdenken, wo es das Ergebnis ändert.
- **Knapp reden:** kein Vorspann, keine Ankündigungen, keine Zusammenfassung; am Ende Ergebnis, Übersprungenes, echte Vorbehalte.
- **Nie gekürzt:** das Problem verstehen, Validierung an Vertrauensgrenzen, Schutz vor Datenverlust, Security, Barrierefreiheit, alles ausdrücklich Gewünschte.

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
app/                       Präferenztext und Skill für die Claude-App
bench/                     der Benchmark, nur Stdlib
assets/                    README-Grafik, erzeugt von bench/chart.py
```

## Benchmark

`bench/` erzeugt neun Szenarien **prozedural aus einem Seed**. Jeder Arm bekommt byte-identische Aufgaben, jede Session läuft headless mit eigenem HOME, eigener Config und frischem venv. So sickert kein Plugin in die Baseline, und kein vorinstalliertes Paket verzerrt ein Ergebnis. Die Arme werden per `--plugin-dir` geladen; eine Vorabprüfung hat bestätigt, dass jeder Arm nur sein eigenes Regelwerk sieht.

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

Ein versteckter Verifier bewertet jeden Lauf. Jeder Verifier ist selbst getestet: Er muss am unberührten Workspace scheitern und mit einer Referenzlösung bestehen (`python3 bench/selftest.py`, 54/54).

Median-Kosten pro Aufgabe auf Opus 5.5 mit Effort max (USD zum Listenpreis, zwei Seeds):

| Szenario | ohne Plugin | Occam | Ponytail |
|---|--:|--:|--:|
| bigfile | 0,44 | **0,17** | 0,26 |
| data | 0,94 | **0,57** | 0,86 |
| feature | 0,94 | **0,50** | 0,53 |
| fixtures | 1,60 | **0,48** | 1,09 |
| question | 0,08 | **0,08** | 0,11 |
| refactor | 1,18 ✗ | **0,52** | 0,99 |
| rootcause | 0,79 | **0,36** | 0,59 |
| security | 1,09 | **0,51** | 0,70 |
| texture | 1,25 | **0,63** | 0,74 |

✗ = Tests nicht bestanden: Ohne Plugin hat Opus die Exporter-Datei beim „Aufräumen“ *länger* gemacht (77 → 83 und 88 Zeilen), auf Seed 3 nur auf 65 gekürzt.

Wohin das Geld geht (Summe über 18 Aufgaben, ohne Plugin → Occam): Thinking 8,03 $ → 3,58 $, Cache-Writes 5,23 $ → 2,83 $, sonstiger Output 2,16 $ → 0,88 $, Cache-Reads 1,19 $ → 0,36 $. Die Aufschlüsselung aus den Token-Zählern ergibt die gemeldeten Kosten auf den Cent.

Weitere Runden:

- **Haiku 4.5** (18 Paare): Occam kostenneutral (−2 %, nicht signifikant), −10 % Output, −28 % Tool-Output, 13 statt 10 von 18 bestanden. Ponytail +30 %.
- **Variante v2** mit zusätzlicher „Verify in proportion“-Regel: ×0,99 [0,89–1,12] gegenüber v1, kein Unterschied. Übernommen wurde nur ihre präzisere Root-Cause-Regel („copied logic“). Sie liegt unter `bench/variants/v2`.
- **Ungesehener Seed 3** mit dem finalen Regelwerk: −45 % [−54 … −34], Turns 14 → 6, 9 von 9 bestanden (ohne Plugin 8 von 9).

### Rohdaten

`bench/results/*.jsonl` enthält eine Zeile pro Session: alle Metriken (Tokens nach Typ, Kosten, Turns, Tool-Calls, Tool-Output-Größe), das Verifier-Ergebnis, die Schlussantwort des Agenten und seinen vollständigen Code-Diff. `python3 bench/bench.py report bench/results/opus-r1.jsonl` erzeugt die Tabellen oben neu. Die vollständigen Session-Transkripte sind nicht veröffentlicht, weil sie kontospezifische Daten enthalten; wer den Benchmark laufen lässt, bekommt seine eigenen.

### Selbst laufen lassen

> **Achtung:** Der Benchmark startet Claude Code mit `--permission-mode bypassPermissions` in temporären Workspaces. Nur in einer Wegwerf-VM oder einem Container ausführen.

Jede Session bekommt ein frisches HOME und sieht deinen normalen Claude-Code-Login deshalb nicht. `ANTHROPIC_API_KEY` exportieren, oder mit `claude setup-token` ein Abo-Token erzeugen und als `CLAUDE_CODE_OAUTH_TOKEN` exportieren.

```
cd bench
python3 selftest.py
python3 bench.py run --model claude-opus-5-5 --effort max \
  --arms baseline,occam=../plugin,ponytail=/pfad/zu/ponytail --seeds 1 2 --jobs 5 --out runs/meins
python3 bench.py report runs/meins
```

Eine Opus-5.5-Session mit Effort max kostet zum Listenpreis etwa 0,07–2,00 $, die volle Drei-Arm-Matrix über zwei Seeds etwa 36 $. Mit Abo zählt das stattdessen gegen das Nutzungslimit.

## Grenzen

- Einzel-Prompt-Aufgaben. Pro Turn wirkt es in langen Sessions genauso, aber ob die Regeln über Stunden gleich gut greifen, misst der Benchmark nicht. Dafür ist `/occam:audit` da.
- Neun Szenarien, überwiegend Python. Frontend-Aufgaben, bei denen Ponytail mit nativen HTML-Elementen glänzt, fehlen.
- Gemessen mit Claude Code 2.1.283. Thinking-Inhalte sind nicht einsehbar, nur ihre Länge.
- Kosten sind Listenpreis-Schätzungen aus den Session-Metadaten.

## Credits

- [Ponytail](https://github.com/DietrichGebert/ponytail) von Dietrich Gebert: die „Lazy Senior Dev“-Leiter und das Muster, Regeln per SessionStart-Hook einzuspielen. Occam übernimmt die Idee, nicht den Code.
- [Der unabhängige Ponytail-Benchmark von JetBrains](https://blog.jetbrains.com/ai/2026/07/ponytail-skill-claude-tested/), der gezeigt hat, dass das erneute Lesen des Kontexts die Rechnung eines Agenten dominiert.

## Lizenz

[MIT](LICENSE)
