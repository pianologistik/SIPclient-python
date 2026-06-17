# SIP-Daemon

Leichtgewichtiger SIP-Daemon für Ubuntu 22.04, der bei eingehenden Anrufen ein PHP-Script mit der Rufnummer des Anrufers aufruft. Der Anruf wird weder angenommen noch abgelehnt.

---

## Installation

### Voraussetzungen

- Ubuntu 22.04
- Root-Zugriff
- Port 5060 UDP/TCP von aussen erreichbar (Firewall / Router-Portweiterleitung)

### Schritte

```bash
# 1. Repository klonen
git clone https://github.com/DEIN-USERNAME/SIPclient.git
cd SIPclient

# 2. Installationsskript ausführen (installiert Python3, PHP-CLI, legt
#    Systembenutzer an, kopiert Dateien, richtet systemd-Service ein)
sudo bash install.sh
```

Das Skript legt folgende Dateien an:

| Pfad | Beschreibung |
|---|---|
| `/usr/local/sbin/sip_daemon.py` | Daemon-Hauptprogramm |
| `/etc/sip-daemon/config.ini` | Konfigurationsdatei |
| `/usr/local/share/sip-daemon/handler.php` | PHP-Handler (Beispiel) |
| `/etc/systemd/system/sip-daemon.service` | Systemd-Unit |

---

## Konfiguration

Alle Einstellungen befinden sich in `/etc/sip-daemon/config.ini`.

### SIP-Zugangsdaten

```ini
[registration]
enabled  = true
server   = business2.voipgateway.org
port     = 5060
username = 41345116490
password = DEIN_PASSWORT
domain   = business2.voipgateway.org
expires  = 300
```

### PHP-Handler

```ini
[handler]
php_binary = php
php_script = /usr/local/share/sip-daemon/handler.php
```

Der Handler unter `/usr/local/share/sip-daemon/handler.php` wird bei jedem eingehenden Anruf ausgeführt:

```php
$rufnummer = $argv[1];             // z.B. +41791234567
$rufnummer = $_ENV['CALLER_NUMBER']; // alternativ als Umgebungsvariable
```

### Öffentliche IP (NAT)

Der Daemon erkennt die öffentliche IP automatisch via STUN. Falls das fehlschlägt (kein STUN-Zugriff), manuell eintragen:

```ini
[sip]
public_address = 1.2.3.4
```

### Logging

```ini
[daemon]
log_file  = /var/log/sip-daemon.log
log_level = INFO   # DEBUG für detaillierte SIP-Nachrichten
```

---

## Betrieb

```bash
# Starten
sudo systemctl start sip-daemon

# Beim Systemstart aktivieren (bereits durch install.sh erledigt)
sudo systemctl enable sip-daemon

# Status prüfen
sudo systemctl status sip-daemon

# Live-Logs
journalctl -u sip-daemon -f

# Anruf-Log
tail -f /var/log/sip-calls.log

# Beenden
sudo systemctl stop sip-daemon
```

### Erwartete Log-Ausgabe bei erfolgreicher Registration

```
INFO  Öffentliche IP für SIP-Contact: 185.x.x.x
INFO  UDP SIP-Listener: 0.0.0.0:5060
INFO  TCP SIP-Listener: 0.0.0.0:5060
INFO  SIP-Registration OK (41345116490@business2.voipgateway.org → 185.x.x.x:5060)
```

### Eingehender Anruf

```
INFO  Eingehender Anruf von +41791234567  (Call-ID: abc123@provider)
INFO  PHP-Handler gestartet (pid=12345) für Rufnummer +41791234567
```

---

## Fehlersuche

| Problem | Lösung |
|---|---|
| `SIP-Registration fehlgeschlagen: 401` | Zugangsdaten in `config.ini` prüfen |
| `SIP-Registration fehlgeschlagen: 403` | Benutzername/Domain beim Provider prüfen |
| Anruf kommt an, PHP startet nicht | Pfad zu `php_script` und `php_binary` prüfen |
| "nicht erreichbar" beim Anrufen | Port 5060 UDP in Firewall öffnen; `public_address` manuell setzen |
| Keine Antwort auf REGISTER | `log_level = DEBUG` → rohe SIP-Nachrichten prüfen |
