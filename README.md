# 🌍 GeoGuessr Discord Stats Bot

Ein Discord-Bot, der automatisch GeoGuessr-Spielstatistiken sammelt, in einer lokalen SQLite-Datenbank speichert und über Slash-Commands als Text oder generierte Diagramme ausgibt.

## Voraussetzungen

- **Raspberry Pi** mit Raspberry Pi OS (Debian-basiert)
- **Python 3.10+** (getestet mit 3.13.5)
- **Discord Bot Token** — erstellt über das [Discord Developer Portal](https://discord.com/developers/applications)
- **GeoGuessr `_ncfa` Cookie** — aus dem Browser extrahiert (siehe unten)

---

## 🛠️ Installation auf dem Raspberry Pi

### 1. Projekt klonen / kopieren

```bash
cd /home/damian
# Option A: Git Clone
git clone <dein-repo-url> DiscordBot

# Option B: Manuell kopieren (z.B. via SCP)
scp -r ./DiscordBot damian@<pi-ip>:/home/damian/DiscordBot
```

### 2. Virtuelle Umgebung erstellen

```bash
cd /home/damian/DiscordBot
python3 -m venv venv
source venv/bin/activate
```

### 3. Abhängigkeiten installieren

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

> **Hinweis für Raspberry Pi:** Falls `matplotlib` oder `numpy` beim Installieren Fehler werfen, installiere zuerst die System-Bibliotheken:
> ```bash
> sudo apt update
> sudo apt install -y python3-dev libatlas-base-dev libopenblas-dev
> ```

### 4. Konfiguration erstellen

```bash
cp .env.example .env
nano .env
```

Trage ein:
```env
DISCORD_TOKEN=dein_discord_bot_token
GEOGUESSR_NCFA=dein_ncfa_cookie_wert
GUILD_ID=1516349812566659155
DB_PATH=./data/geoguessr_stats.db
```

### 5. Datenverzeichnis erstellen

```bash
mkdir -p data
```

### 6. Manueller Teststart

```bash
source venv/bin/activate
python bot.py
```

Der Bot sollte sich in Discord anmelden und die Slash-Commands registrieren. Teste mit `/link` in Discord.

Stoppe mit `Ctrl+C`.

---

## 📦 SQLite-Datenbank einrichten

Die Datenbank wird **automatisch beim ersten Start** erstellt. Du musst nichts manuell konfigurieren.

**Speicherort:** `./data/geoguessr_stats.db` (konfigurierbar in `.env`)

**Schema:**
- **`players`** — Verknüpfung Discord-ID ↔ GeoGuessr-ID
- **`games`** — Chronologische Spielhistorie mit Elo-Daten

**Datenbank inspizieren:**
```bash
sqlite3 data/geoguessr_stats.db
.tables
SELECT * FROM players;
SELECT COUNT(*) FROM games;
.quit
```

**Backup:**
```bash
cp data/geoguessr_stats.db data/geoguessr_stats.db.backup
```

---

## 🔄 Hintergrund-Task (Automatisches Polling)

Der Bot fragt **exakt alle 10 Minuten** die GeoGuessr-API für alle registrierten Spieler ab.

**Ablauf:**
1. Alle registrierten Spieler aus der Datenbank laden
2. Für jeden Spieler den Activity-Feed abrufen
3. Neue Spiele erkennen (Duplikat-Check über `game_id`)
4. Detaillierte Spieldaten abrufen (Elo-Werte, Ergebnis)
5. In die Datenbank speichern
6. 2 Sekunden Pause zwischen Spielern (Rate-Limit-Schutz)

**Logs einsehen:**
```bash
journalctl -u geoguessr_bot -f
```

---

## ⚙️ Als Systemdienst einrichten (systemd)

Damit der Bot beim Booten automatisch startet und im Hintergrund läuft:

### 1. Service-Datei kopieren

```bash
sudo cp /home/damian/DiscordBot/geoguessr_bot.service /etc/systemd/system/
```

### 2. systemd neu laden

```bash
sudo systemctl daemon-reload
```

### 3. Dienst aktivieren (Autostart)

```bash
sudo systemctl enable geoguessr_bot
```

### 4. Dienst starten

```bash
sudo systemctl start geoguessr_bot
```

### 5. Status prüfen

```bash
sudo systemctl status geoguessr_bot
```

**Erwartete Ausgabe:**
```
● geoguessr_bot.service - GeoGuessr Discord Stats Bot
     Loaded: loaded (/etc/systemd/system/geoguessr_bot.service; enabled)
     Active: active (running) since ...
```

### Nützliche Befehle

| Befehl | Beschreibung |
|--------|-------------|
| `sudo systemctl start geoguessr_bot` | Bot starten |
| `sudo systemctl stop geoguessr_bot` | Bot stoppen |
| `sudo systemctl restart geoguessr_bot` | Bot neu starten |
| `sudo systemctl status geoguessr_bot` | Status anzeigen |
| `journalctl -u geoguessr_bot -f` | Live-Logs anzeigen |
| `journalctl -u geoguessr_bot --since "1 hour ago"` | Logs der letzten Stunde |

---

## 🍪 GeoGuessr `_ncfa` Cookie erneuern

Der `_ncfa`-Cookie hat eine begrenzte Lebensdauer. Wenn der Bot `401 Unauthorized`-Fehler loggt, muss er erneuert werden.

### Cookie extrahieren:

1. Öffne **https://www.geoguessr.com** im Browser und logge dich ein
2. Öffne die **Entwicklertools** (`F12`)
3. Gehe zum Tab **Application** → **Cookies** → `https://www.geoguessr.com`
4. Finde den Cookie `_ncfa`
5. Kopiere den **Value**
6. Trage ihn in `/home/damian/DiscordBot/.env` ein:
   ```
   GEOGUESSR_NCFA=neuer_cookie_wert
   ```
7. Starte den Bot neu:
   ```bash
   sudo systemctl restart geoguessr_bot
   ```

---

## 🤖 Slash-Commands

| Command | Beschreibung |
|---------|-------------|
| `/link <geoguessr_id>` | Discord-Account mit GeoGuessr verknüpfen |
| `/unlink` | Verknüpfung lösen |
| `/profile [@user]` | Profildaten anzeigen |
| `/recent [@user]` | Letzte 5 Spiele als Tabelle |
| `/winrate [@user]` | Win/Loss-Ratio als Text |
| `/activity [@user]` | 📊 Aktivitätsdiagramm (7 Tage) |
| `/elo [@user]` | 📈 Elo-Verlauf |
| `/winrate_chart [@user]` | 🏆 Win/Loss-Diagramm nach Modus |
| `/heatmap [@user]` | 🔥 Jahres-Aktivitäts-Heatmap |

> Alle Commands ohne `@user` zeigen die eigenen Daten an.

---

## 📁 Projektstruktur

```
DiscordBot/
├── bot.py                  # Haupteinstiegspunkt
├── config.py               # Konfiguration aus .env
├── database.py             # SQLite-Datenbank
├── geoguessr_api.py        # Async API-Client
├── cogs/
│   ├── __init__.py
│   ├── registration.py     # /link, /unlink, /profile
│   ├── stats.py            # /recent, /winrate
│   └── charts.py           # /activity, /elo, /winrate_chart, /heatmap
├── utils/
│   ├── __init__.py
│   └── chart_generator.py  # matplotlib Chart-Erzeugung
├── data/
│   └── geoguessr_stats.db  # SQLite-Datenbank (automatisch erstellt)
├── .env                    # Konfiguration (nicht committen!)
├── .env.example            # Vorlage
├── requirements.txt        # Python-Abhängigkeiten
├── README.md               # Diese Datei
└── geoguessr_bot.service   # systemd Service-Datei
```

---

## ⚠️ Hinweise

- **Inoffizielle API:** GeoGuessr hat keine offizielle öffentliche API. Alle Endpoints sind reverse-engineered und können sich jederzeit ändern.
- **Rate Limiting:** Der Bot wartet 2 Sekunden zwischen Spieler-Abfragen und pollt nur alle 10 Minuten.
- **Team Duels:** Der Bot nutzt die rohen API-Daten für korrekte Elo-Berechnung — die GeoGuessr-UI zeigt bei Team Duels oft gedeckelte Weekly Points statt echtem Elo.
- **Datenschutz:** Die `.env`-Datei enthält sensible Daten. Niemals committen!
