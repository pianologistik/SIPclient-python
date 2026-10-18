# SIP-Daemon (Python)

SIP-Daemon für Ubuntu 22.04 — kein PHP erforderlich. Bei eingehenden Anrufen wird ein Python-Handler aufgerufen, der die Rufnummer an die FileMaker Data API weitergibt.

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

### `/etc/sip-daemon/config.ini`

```ini
[registration]
enabled  = true
server   = business2.voipgateway.org
username = 41345116490
password = DEIN_PASSWORT
domain   = business2.voipgateway.org

[handler]
handler_binary = python3
handler_script = /usr/local/share/sip-daemon/handler.py
```

### `/usr/local/share/sip-daemon/handler.py`

FileMaker-Zugangsdaten eintragen:

```python
FM_HOST   = 'mein-filemaker-server'
FM_DB     = 'MeineDB'
FM_LAYOUT = 'Anrufe'
FM_USER   = 'admin'
FM_PASS   = 'geheim'
FM_SKIP_SSL = False  # True bei selbstsigniertem Zertifikat
```

Der Handler erstellt bei jedem Anruf einen neuen Datensatz im angegebenen Layout. Feld `Rufnummer` wird mit der Anrufernummer (10 Stellen, beginnt mit 0) befüllt.

---

## Betrieb

```bash
sudo systemctl start sip-daemon
sudo systemctl stop sip-daemon
journalctl -u sip-daemon -f
```

---

## Fehlersuche

| Problem | Lösung |
|---|---|
| Registration schlägt fehl | `log_level = DEBUG` in config.ini |
| FileMaker-Fehler | SSL-Zertifikat prüfen; `FM_SKIP_SSL = True` bei selbstsigniertem Cert |
| "nicht erreichbar" | Port 5060 öffnen; `public_address` in config.ini manuell setzen |
