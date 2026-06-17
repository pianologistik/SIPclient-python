#!/usr/bin/env python3
"""
SIP Daemon — lauscht auf eingehende SIP-Calls und startet ein PHP-Script
mit der Rufnummer des Anrufers. Weder Annahme noch Ablehnung des Anrufs.

Sendet nur 100 Trying, um Retransmissions des Gegenstellers zu stoppen.
Optional: SIP-Registration beim Provider/PBX.
"""

import socket
import threading
import subprocess
import queue
import re
import logging
import logging.handlers
import signal
import sys
import configparser
import time
import os
import hashlib
import random
import string
import argparse


# ---------------------------------------------------------------------------
# SIP-Hilfsfunktionen
# ---------------------------------------------------------------------------

def _header(text: str, name: str) -> str:
    """Ersten passenden Header-Wert zurückgeben (case-insensitiv)."""
    name_lc = name.lower() + ':'
    for line in text.split('\r\n'):
        if line.lower().startswith(name_lc):
            return line.split(':', 1)[1].strip()
    return ''


def extract_caller(sip_text: str) -> str:
    """
    Rufnummer aus einem SIP-INVITE extrahieren.
    Reihenfolge: P-Asserted-Identity → Remote-Party-ID → From
    """
    for header in ('p-asserted-identity', 'remote-party-id', 'from'):
        val = _header(sip_text, header)
        if not val:
            continue
        # <sip:+41791234567@host> oder <tel:+41791234567>
        m = re.search(r'(?:sip|sips|tel):([+\d][\d\-\.\(\)]*)\b', val, re.I)
        if m:
            return re.sub(r'[^\d+]', '', m.group(1))
    return ''


def extract_call_id(sip_text: str) -> str:
    return _header(sip_text, 'call-id') or _header(sip_text, 'i')


def build_response(status: str, sip_text: str) -> bytes:
    """Minimale SIP-Antwort bauen (via/from/to/call-id/cseq aus dem Request)."""
    lines = sip_text.split('\r\n')

    # Alle Via-Zeilen kopieren (RFC 3261 §8.2.6)
    via_lines = [l for l in lines[1:] if l.lower().startswith(('via:', 'v:'))]

    resp  = f'SIP/2.0 {status}\r\n'
    resp += '\r\n'.join(via_lines) + '\r\n' if via_lines else ''

    for h in ('from', 'f'):
        v = _header(sip_text, h)
        if v:
            resp += f'From: {v}\r\n'
            break
    for h in ('to', 't'):
        v = _header(sip_text, h)
        if v:
            resp += f'To: {v}\r\n'
            break

    ci = extract_call_id(sip_text)
    if ci:
        resp += f'Call-ID: {ci}\r\n'

    cseq = _header(sip_text, 'cseq')
    if cseq:
        resp += f'CSeq: {cseq}\r\n'

    resp += 'Content-Length: 0\r\n\r\n'
    return resp.encode()


# ---------------------------------------------------------------------------
# SIP-Digest-Auth
# ---------------------------------------------------------------------------

def _md5(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()


def digest_response(username: str, password: str, realm: str,
                    nonce: str, method: str, uri: str,
                    algorithm: str = 'MD5',
                    qop: str = '', cnonce: str = '', nc: str = '') -> str:
    ha1 = _md5(f'{username}:{realm}:{password}')
    ha2 = _md5(f'{method}:{uri}')
    if qop in ('auth', 'auth-int'):
        return _md5(f'{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}')
    return _md5(f'{ha1}:{nonce}:{ha2}')


def build_auth_header(username: str, password: str, auth_hdr_val: str,
                      method: str, uri: str, hdr_name: str = 'Authorization') -> str:
    """Vollständigen Authorization-Header für Digest-Auth bauen (mit qop-Unterstützung)."""
    params  = parse_www_auth(auth_hdr_val)
    realm   = params.get('realm', '')
    nonce   = params.get('nonce', '')
    alg     = params.get('algorithm', 'MD5')
    qop_opt = params.get('qop', '')          # z.B. "auth" oder "auth,auth-int"
    opaque  = params.get('opaque', '')

    # qop=auth bevorzugen, falls angeboten
    qop    = 'auth' if 'auth' in qop_opt else ''
    cnonce = random_tag(16) if qop else ''
    nc     = '00000001'     if qop else ''

    dr = digest_response(username, password, realm, nonce, method, uri,
                         alg, qop, cnonce, nc)

    parts = [
        f'username="{username}"',
        f'realm="{realm}"',
        f'nonce="{nonce}"',
        f'uri="{uri}"',
        f'response="{dr}"',
        f'algorithm={alg}',
    ]
    if qop:
        parts += [f'qop={qop}', f'cnonce="{cnonce}"', f'nc={nc}']
    if opaque:
        parts.append(f'opaque="{opaque}"')

    return f'{hdr_name}: Digest ' + ','.join(parts)


def parse_www_auth(header_val: str) -> dict:
    """WWW-Authenticate-Header parsen (mit und ohne Anführungszeichen)."""
    result = {}
    for m in re.finditer(r'(\w+)\s*=\s*(?:"([^"]*)"|([\w\.\-\+/=]+))', header_val):
        result[m.group(1).lower()] = m.group(2) if m.group(2) is not None else m.group(3)
    return result


def random_tag(n: int = 8) -> str:
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))


def random_branch() -> str:
    return 'z9hG4bK' + ''.join(random.choices(string.hexdigits, k=16))


def detect_public_ip() -> str:
    """Öffentliche IP via STUN ermitteln (UDP, kein HTTP nötig)."""
    # Minimaler STUN Binding Request (RFC 5389)
    stun_servers = [
        ('stun.cloudflare.com', 3478),
        ('stun.l.google.com',   19302),
        ('stun1.l.google.com',  19302),
    ]
    msg = (b'\x00\x01'          # Binding Request
           b'\x00\x00'          # Message Length = 0
           b'\x21\x12\xa4\x42'  # Magic Cookie
           + random.randbytes(12))  # Transaction ID

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(3)
    try:
        for host, port in stun_servers:
            try:
                sock.sendto(msg, (host, port))
                data, _ = sock.recvfrom(512)
                # STUN-Antwort parsen: Attribute nach 20-Byte-Header
                i = 20
                while i + 4 <= len(data):
                    attr_type  = int.from_bytes(data[i:i+2], 'big')
                    attr_len   = int.from_bytes(data[i+2:i+4], 'big')
                    attr_val   = data[i+4:i+4+attr_len]
                    # 0x0001 = MAPPED-ADDRESS, 0x0020 = XOR-MAPPED-ADDRESS
                    if attr_type == 0x0020 and len(attr_val) >= 8:
                        # XOR-MAPPED-ADDRESS: IPv4
                        xport = int.from_bytes(attr_val[2:4], 'big') ^ 0x2112
                        xip   = bytes(b ^ m for b, m in zip(attr_val[4:8], b'\x21\x12\xa4\x42'))
                        return socket.inet_ntoa(xip)
                    if attr_type == 0x0001 and len(attr_val) >= 8:
                        return socket.inet_ntoa(attr_val[4:8])
                    i += 4 + attr_len + (attr_len % 4 and 4 - attr_len % 4)
            except Exception:
                continue
    finally:
        sock.close()
    return ''


# ---------------------------------------------------------------------------
# Haupt-Daemon
# ---------------------------------------------------------------------------

class SIPDaemon:

    def __init__(self, config_path: str):
        self.cfg = configparser.ConfigParser()
        self.cfg.read(config_path)
        self._setup_logging()
        self.running = False

        # Netzwerk
        self.bind_addr = self.cfg.get('sip', 'bind_address', fallback='0.0.0.0')
        self.bind_port = self.cfg.getint('sip', 'bind_port', fallback=5060)
        self.sock_udp: socket.socket | None = None
        self.sock_tcp: socket.socket | None = None

        # Öffentliche IP (für Contact-Header hinter NAT)
        cfg_pub = self.cfg.get('sip', 'public_address', fallback='').strip()
        if cfg_pub:
            self.public_addr = cfg_pub
        else:
            self.public_addr = detect_public_ip()

        # Registration (optional)
        self.do_register = self.cfg.getboolean('registration', 'enabled', fallback=False)
        self.reg_server  = self.cfg.get('registration', 'server', fallback='')
        self.reg_port    = self.cfg.getint('registration', 'port', fallback=5060)
        self.reg_user    = self.cfg.get('registration', 'username', fallback='')
        self.reg_pass    = self.cfg.get('registration', 'password', fallback='')
        self.reg_domain  = self.cfg.get('registration', 'domain', fallback='')
        self.reg_expires = self.cfg.getint('registration', 'expires', fallback=300)

        # Queue: UDP-Listener leitet SIP-Antworten (2xx/4xx) an Registration weiter
        self._reg_queue: queue.Queue = queue.Queue(maxsize=10)

        # PHP-Handler
        self.php_bin    = self.cfg.get('handler', 'php_binary', fallback='php')
        self.php_script = self.cfg.get('handler', 'php_script',
                                       fallback='/usr/local/share/sip-daemon/handler.php')

        # Deduplication: Call-ID → Zeitstempel
        self._seen: dict[str, float] = {}
        self._seen_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _setup_logging(self):
        log_file  = self.cfg.get('daemon', 'log_file', fallback='/var/log/sip-daemon.log')
        log_level = self.cfg.get('daemon', 'log_level', fallback='INFO').upper()

        fmt = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s')
        root = logging.getLogger()
        root.setLevel(getattr(logging, log_level, logging.INFO))

        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(fmt)
        root.addHandler(ch)

        try:
            fh = logging.handlers.RotatingFileHandler(
                log_file, maxBytes=5_000_000, backupCount=3)
            fh.setFormatter(fmt)
            root.addHandler(fh)
        except PermissionError:
            logging.warning(f'Kein Schreibzugriff auf {log_file}, nur stdout-Logging.')

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def _already_seen(self, call_id: str) -> bool:
        """True wenn dieser Call-ID innerhalb der letzten 120 s schon verarbeitet wurde."""
        now = time.time()
        with self._seen_lock:
            # altes aufräumen
            expired = [k for k, v in self._seen.items() if now - v > 120]
            for k in expired:
                del self._seen[k]
            if call_id in self._seen:
                return True
            self._seen[call_id] = now
            return False

    # ------------------------------------------------------------------
    # PHP aufrufen
    # ------------------------------------------------------------------

    def _run_php(self, number: str, sip_text: str):
        env = os.environ.copy()
        env['CALLER_NUMBER'] = number
        env['SIP_INVITE']    = sip_text[:4096]
        try:
            proc = subprocess.Popen(
                [self.php_bin, self.php_script, number],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logging.info(f'PHP-Handler gestartet (pid={proc.pid}) für Rufnummer {number}')
        except FileNotFoundError:
            logging.error(f'PHP-Binary nicht gefunden: {self.php_bin}')
        except Exception as e:
            logging.error(f'PHP-Handler Fehler: {e}')

    # ------------------------------------------------------------------
    # Eingehende Nachricht verarbeiten
    # ------------------------------------------------------------------

    def _process(self, data: bytes, send_fn):
        try:
            text = data.decode('utf-8', errors='replace')
        except Exception:
            return

        first = text.split('\r\n', 1)[0]

        # SIP-Antworten (z.B. "SIP/2.0 200 OK") an Registration weiterleiten
        if first.startswith('SIP/2.0'):
            try:
                self._reg_queue.put_nowait(data)
            except queue.Full:
                pass
            return

        if not first.startswith('INVITE '):
            return

        call_id = extract_call_id(text)
        if call_id and self._already_seen(call_id):
            # Retransmission — trotzdem 100 Trying schicken
            send_fn(build_response('100 Trying', text))
            return

        send_fn(build_response('100 Trying', text))

        number = extract_caller(text)
        if number:
            logging.info(f'Eingehender Anruf von {number}  (Call-ID: {call_id})')
            threading.Thread(target=self._run_php, args=(number, text),
                             daemon=True).start()
        else:
            logging.warning(f'INVITE ohne erkennbare Rufnummer (Call-ID: {call_id})')
            logging.debug(f'SIP-Rohtext (erste 400 Zeichen):\n{text[:400]}')

    # ------------------------------------------------------------------
    # UDP-Listener
    # ------------------------------------------------------------------

    def _udp_listener(self):
        self.sock_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock_udp.bind((self.bind_addr, self.bind_port))
        self.sock_udp.settimeout(1.0)
        logging.info(f'UDP SIP-Listener: {self.bind_addr}:{self.bind_port}')

        while self.running:
            try:
                data, addr = self.sock_udp.recvfrom(65535)
                def send(pkt, a=addr):
                    try:
                        self.sock_udp.sendto(pkt, a)
                    except Exception:
                        pass
                self._process(data, send)
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception as e:
                logging.debug(f'UDP-Listener Fehler: {e}')

    # ------------------------------------------------------------------
    # TCP-Listener
    # ------------------------------------------------------------------

    def _tcp_client(self, conn: socket.socket, addr):
        buf = b''
        conn.settimeout(30)
        try:
            while self.running:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buf += chunk
                # Einfache Heuristik: komplette SIP-Nachricht wenn \r\n\r\n enthalten
                while b'\r\n\r\n' in buf:
                    msg, buf = buf.split(b'\r\n\r\n', 1)
                    msg += b'\r\n\r\n'

                    def send(pkt, c=conn):
                        try:
                            c.sendall(pkt)
                        except Exception:
                            pass

                    self._process(msg, send)
        except Exception:
            pass
        finally:
            conn.close()

    def _tcp_listener(self):
        self.sock_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock_tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock_tcp.bind((self.bind_addr, self.bind_port))
        self.sock_tcp.listen(10)
        self.sock_tcp.settimeout(1.0)
        logging.info(f'TCP SIP-Listener: {self.bind_addr}:{self.bind_port}')

        while self.running:
            try:
                conn, addr = self.sock_tcp.accept()
                threading.Thread(target=self._tcp_client, args=(conn, addr),
                                 daemon=True).start()
            except socket.timeout:
                continue
            except OSError:
                break

    # ------------------------------------------------------------------
    # SIP-Registration
    # ------------------------------------------------------------------

    def _send_register(self, call_id: str, from_tag: str,
                       cseq: int, auth_header: str = '') -> bytes:
        """
        REGISTER über den Haupt-UDP-Socket (Port 5060) senden.
        Verwendet die öffentliche IP im Contact/Via-Header, damit der Provider
        INVITEs auch hinter NAT zustellen kann.
        call_id und from_tag bleiben über alle Versuche gleich (RFC 3261 §10.2).
        """
        branch     = random_branch()
        uri        = f'sip:{self.reg_domain}'
        public_ip  = self.public_addr or self.bind_addr
        contact    = f'sip:{self.reg_user}@{public_ip}:{self.bind_port}'

        msg  = f'REGISTER {uri} SIP/2.0\r\n'
        msg += (f'Via: SIP/2.0/UDP {public_ip}:{self.bind_port}'
                f';branch={branch};rport\r\n')
        msg += f'From: <sip:{self.reg_user}@{self.reg_domain}>;tag={from_tag}\r\n'
        msg += f'To: <sip:{self.reg_user}@{self.reg_domain}>\r\n'
        msg += f'Call-ID: {call_id}\r\n'
        msg += f'CSeq: {cseq} REGISTER\r\n'
        msg += f'Contact: <{contact}>\r\n'
        msg += f'Expires: {self.reg_expires}\r\n'
        msg += f'Max-Forwards: 70\r\n'
        msg += f'User-Agent: sip-daemon/1.0\r\n'
        if auth_header:
            msg += auth_header + '\r\n'
        msg += 'Content-Length: 0\r\n\r\n'

        logging.debug(f'REGISTER → (Contact: {contact})\n{msg}')

        if self.sock_udp:
            self.sock_udp.sendto(msg.encode(), (self.reg_server, self.reg_port))
        else:
            logging.error('UDP-Socket noch nicht bereit für REGISTER')
            return b''

        # Antwort kommt über den UDP-Listener in die Queue
        try:
            data = self._reg_queue.get(timeout=6)
            logging.debug(f'REGISTER ←\n{data.decode("utf-8", errors="replace")}')
            return data
        except queue.Empty:
            logging.warning('Keine Antwort auf REGISTER (Timeout)')
            return b''

    def _registration_loop(self):
        """
        Dauerhaft beim SIP-Server registrieren.
        Wartet bis der UDP-Socket bereit ist, dann sendet über denselben Socket
        (Port 5060), damit der Contact-Header mit der tatsächlichen Empfangsadresse
        übereinstimmt.
        """
        # Warten bis UDP-Listener gestartet ist
        for _ in range(30):
            if self.sock_udp:
                break
            time.sleep(0.5)
        else:
            logging.error('UDP-Socket nicht verfügbar – Registration abgebrochen')
            return

        if self.public_addr:
            logging.info(f'Öffentliche IP für SIP-Contact: {self.public_addr}')
        else:
            logging.warning('Öffentliche IP konnte nicht ermittelt werden – '
                            'verwende bind_address. Bei NAT bitte public_address in config.ini setzen.')

        while self.running:
            try:
                call_id  = f'{random_tag(20)}@{self.public_addr or self.bind_addr}'
                from_tag = random_tag(12)
                cseq     = 1
                uri      = f'sip:{self.reg_domain}'

                # ── Schritt 1: REGISTER ohne Auth ──────────────────────────
                resp  = self._send_register(call_id, from_tag, cseq)
                text  = resp.decode('utf-8', errors='replace')
                first = text.split('\r\n', 1)[0]

                # ── Schritt 2: Digest-Auth (401 oder 407) ──────────────────
                if '401' in first or '407' in first:
                    cseq += 1
                    auth_hdr_name = 'www-authenticate' if '401' in first else 'proxy-authenticate'
                    auth_val      = _header(text, auth_hdr_name)

                    if not auth_val:
                        logging.error('401 ohne WWW-Authenticate-Header erhalten')
                    else:
                        resp_hdr = 'Authorization' if '401' in first else 'Proxy-Authorization'
                        auth = build_auth_header(
                            self.reg_user, self.reg_pass,
                            auth_val, 'REGISTER', uri, resp_hdr)

                        resp  = self._send_register(call_id, from_tag, cseq, auth)
                        text  = resp.decode('utf-8', errors='replace')
                        first = text.split('\r\n', 1)[0]

                # ── Ergebnis auswerten ─────────────────────────────────────
                if '200' in first:
                    logging.info(f'SIP-Registration OK '
                                 f'({self.reg_user}@{self.reg_domain} → '
                                 f'{self.public_addr or self.bind_addr}:{self.bind_port})')
                elif first:
                    logging.warning(f'SIP-Registration fehlgeschlagen: {first.strip()}')
                    logging.debug(f'Antwort:\n{text[:800]}')
                else:
                    logging.warning('SIP-Registration: keine Antwort vom Server')

            except Exception as e:
                logging.error(f'Registration-Fehler: {e}')

            # Vor Ablauf erneuern
            sleep_for = max(30, self.reg_expires - 30)
            for _ in range(sleep_for):
                if not self.running:
                    break
                time.sleep(1)

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------

    def start(self):
        self.running = True
        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)

        threads = [
            threading.Thread(target=self._udp_listener, daemon=True, name='udp'),
            threading.Thread(target=self._tcp_listener, daemon=True, name='tcp'),
        ]
        if self.do_register:
            threads.append(threading.Thread(target=self._registration_loop,
                                            daemon=True, name='registration'))

        for t in threads:
            t.start()

        logging.info('SIP-Daemon gestartet.')
        while self.running:
            time.sleep(1)

    def _shutdown(self, sig, _frame):
        logging.info(f'Signal {sig} empfangen – beende Daemon.')
        self.running = False
        for s in (self.sock_udp, self.sock_tcp):
            if s:
                try:
                    s.close()
                except Exception:
                    pass
        sys.exit(0)


# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='SIP-Daemon – eingehende Anrufe → PHP')
    ap.add_argument('--config', default='/etc/sip-daemon/config.ini',
                    help='Pfad zur Konfigurationsdatei')
    args = ap.parse_args()

    if not os.path.exists(args.config):
        print(f'Konfigurationsdatei nicht gefunden: {args.config}', file=sys.stderr)
        sys.exit(1)

    SIPDaemon(args.config).start()
