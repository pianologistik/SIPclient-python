#!/usr/bin/env python3
"""
SIP-Daemon Call-Handler — FileMaker Data API
Aufruf: handler.py <rufnummer>
"""
import sys
import json
import base64
import urllib.request
import urllib.error
import ssl

NUMBER = sys.argv[1] if len(sys.argv) > 1 else ''

# ── Konfiguration ────────────────────────────────────────────────────────────
FM_HOST   = 'mein-filemaker-server'
FM_DB     = 'MeineDB'
FM_LAYOUT = 'Anrufe'
FM_USER   = 'admin'
FM_PASS   = 'geheim'

# Auf True setzen wenn selbstsigniertes Zertifikat
FM_SKIP_SSL = False
# ─────────────────────────────────────────────────────────────────────────────

BASE = f'https://{FM_HOST}/fmi/data/v2/databases/{fm_db}'

def fm_request(url, data=None, headers=None, method=None):
    ctx = ssl.create_default_context()
    if FM_SKIP_SSL:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    return json.loads(urllib.request.urlopen(req, timeout=5, context=ctx).read())

def get_token():
    creds = base64.b64encode(f'{FM_USER}:{FM_PASS}'.encode()).decode()
    r = fm_request(
        f'https://{FM_HOST}/fmi/data/v2/databases/{FM_DB}/sessions',
        data=b'{}',
        headers={'Content-Type': 'application/json', 'Authorization': f'Basic {creds}'}
    )
    return r['response']['token']

def create_record(token, number):
    fm_request(
        f'https://{FM_HOST}/fmi/data/v2/databases/{FM_DB}/layouts/{FM_LAYOUT}/records',
        data=json.dumps({'fieldData': {'Rufnummer': number}}).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'}
    )

def logout(token):
    fm_request(
        f'https://{FM_HOST}/fmi/data/v2/databases/{FM_DB}/sessions/{token}',
        method='DELETE',
        headers={'Content-Type': 'application/json'}
    )

token = get_token()
try:
    create_record(token, NUMBER)
finally:
    logout(token)
