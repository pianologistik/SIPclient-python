# SIP-Daemon (Python)

SIP-Daemon für Ubuntu 22.04 — kein PHP erforderlich. Bei eingehenden Anrufen wird ein Python-Handler aufgerufen, der ein FileMaker-Script via Data API ausführt.

---

## Installation

### Voraussetzungen

- Ubuntu 22.04
- Root-Zugriff
- Port 5060 UDP/TCP von aussen erreichbar

```bash
git clone https://github.com/pianologistik/SIPclient-python.git
cd SIPclient-python
sudo bash install.sh
```

---

## Konfiguration

```bash
sudo nano /etc/sip-daemon/config.ini
```

Vorlage: `config.ini.example`. Minimale Pflichtfelder:

```ini
[registration]
enabled  = true
server   = business2.voipgateway.org
username = 41345116490
password = DEIN_PASSWORT
domain   = business2.voipgateway.org

[filemaker]
host     = claris.example.com
database = MeineDB
layout   = MeinLayout
script   = scrAnruflisteEinfuegenClient
username = api-benutzer
password = api-passwort
skip_ssl = false        ; true bei selbstsigniertem Zertifikat
```

---

## Betrieb

```bash
# Starten / Stoppen / Neustarten
sudo systemctl start sip-daemon
sudo systemctl stop sip-daemon
sudo systemctl restart sip-daemon

# Autostart prüfen
systemctl is-enabled sip-daemon

# Handler manuell testen
python3 /usr/local/share/sip-daemon/handler.py 0344456667
```

---

## Debugging & Logs

### Daemon-Status

```bash
systemctl status sip-daemon
```

### Live-Log (SIP-Ereignisse, Registration, Fehler)

```bash
journalctl -u sip-daemon -f
```

### Daemon-Logdatei

```bash
tail -f /var/log/sip-daemon.log
```

### Letzte 10 Anrufe

```bash
cat /var/log/sip-calls.json
```

Beispiel-Ausgabe:
```json
[
  {"number": "0344456667", "timestamp": "2026-10-21 21:02:41"},
  {"number": "0791234567", "timestamp": "2026-10-21 21:15:03"}
]
```

### Detailliertes Logging (SIP-Rohdaten)

In `/etc/sip-daemon/config.ini`:
```ini
[daemon]
log_level = DEBUG
```
Dann: `sudo systemctl restart sip-daemon`

---

## Fehlersuche

| Problem | Lösung |
|---|---|
| `SIP-Registration fehlgeschlagen: 401` | Zugangsdaten in `[registration]` prüfen |
| `SIP-Registration fehlgeschlagen: 403` | Benutzername/Domain beim Provider prüfen |
| `HTTP 500 Field is missing` | Feldname im Layout prüfen |
| `HTTP 500 Script is missing` | `script` in `[filemaker]` prüfen — exakter FM-Scriptname |
| `HTTP 401` von FileMaker | FM-Benutzer braucht Berechtigung `fmrest` (Datei → Verwalten → Sicherheit) |
| "nicht erreichbar" beim Anrufen | Port 5060 in Firewall öffnen; `public_address` in `[sip]` setzen |
| Handler startet nicht | `python3 /usr/local/share/sip-daemon/handler.py 0300000000` manuell testen |
