#!/usr/bin/env bash
# SIP-Daemon Installationsskript für Ubuntu 22.04
# Muss als root ausgeführt werden: sudo bash install.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Prüfungen ────────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    echo "Bitte als root ausführen: sudo bash install.sh" >&2
    exit 1
fi

echo "=== SIP-Daemon Installation ==="

# ── Abhängigkeiten ──────────────────────────────────────────────────────────
echo "[1/6] Pakete installieren ..."
apt-get update -qq
apt-get install -y python3 php-cli

# ── Systembenutzer ──────────────────────────────────────────────────────────
echo "[2/6] Systembenutzer 'sip-daemon' anlegen ..."
if ! id sip-daemon &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin sip-daemon
fi

# ── Verzeichnisse ────────────────────────────────────────────────────────────
echo "[3/6] Verzeichnisse anlegen ..."
install -d -m 755 /etc/sip-daemon
install -d -m 755 /usr/local/share/sip-daemon
install -d -m 775 -o sip-daemon -g sip-daemon /var/log

# ── Dateien kopieren ────────────────────────────────────────────────────────
echo "[4/6] Dateien installieren ..."
install -m 755 "${SCRIPT_DIR}/sip_daemon.py"  /usr/local/sbin/sip_daemon.py

# Config nur wenn noch nicht vorhanden (überschreibt keine bestehende)
if [[ ! -f /etc/sip-daemon/config.ini ]]; then
    install -m 640 -o root -g sip-daemon "${SCRIPT_DIR}/config.ini" /etc/sip-daemon/config.ini
    echo "    → /etc/sip-daemon/config.ini angelegt. Bitte anpassen!"
else
    echo "    → /etc/sip-daemon/config.ini bereits vorhanden, wird nicht überschrieben."
fi

# PHP-Handler nur wenn noch nicht vorhanden
if [[ ! -f /usr/local/share/sip-daemon/handler.php ]]; then
    install -m 755 "${SCRIPT_DIR}/handler.php" /usr/local/share/sip-daemon/handler.php
    echo "    → /usr/local/share/sip-daemon/handler.php angelegt."
fi

# Log-Datei anlegen und Rechte setzen
touch /var/log/sip-daemon.log
chown sip-daemon:sip-daemon /var/log/sip-daemon.log
touch /var/log/sip-calls.log
chown sip-daemon:sip-daemon /var/log/sip-calls.log

# ── Systemd Service ─────────────────────────────────────────────────────────
echo "[5/6] Systemd-Service einrichten ..."
install -m 644 "${SCRIPT_DIR}/sip-daemon.service" /etc/systemd/system/sip-daemon.service
systemctl daemon-reload
systemctl enable sip-daemon

# ── Firewall (ufw) ──────────────────────────────────────────────────────────
echo "[6/6] Firewall-Regel für SIP (Port 5060 UDP+TCP) ..."
if command -v ufw &>/dev/null; then
    ufw allow 5060/udp comment "SIP-Daemon" || true
    ufw allow 5060/tcp comment "SIP-Daemon" || true
fi

echo ""
echo "=== Installation abgeschlossen ==="
echo ""
echo "Nächste Schritte:"
echo "  1. Konfiguration anpassen:  nano /etc/sip-daemon/config.ini"
echo "  2. PHP-Handler anpassen:    nano /usr/local/share/sip-daemon/handler.php"
echo "  3. Daemon starten:          systemctl start sip-daemon"
echo "  4. Status prüfen:           systemctl status sip-daemon"
echo "  5. Logs verfolgen:          journalctl -u sip-daemon -f"
echo "                              tail -f /var/log/sip-daemon.log"
echo ""
