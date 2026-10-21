#!/usr/bin/env python3
"""
SIP-Daemon Call-Handler — FileMaker Data API
Aufruf: handler.py <rufnummer>
Zugangsdaten werden aus /etc/sip-daemon/config.ini gelesen.
"""
import sys
import json
import base64
import configparser
import urllib.request
import urllib.error
import ssl

NUMBER = sys.argv[1] if len(sys.argv) > 1 else ''

cfg = configparser.ConfigParser()
cfg.read('/etc/sip-daemon/config.ini')

FM_HOST     = cfg.get('filemaker', 'host')
FM_DB       = cfg.get('filemaker', 'database')
FM_LAYOUT   = cfg.get('filemaker', 'layout')
FM_USER     = cfg.get('filemaker', 'username')
FM_PASS     = cfg.get('filemaker', 'password')
FM_SKIP_SSL = cfg.getboolean('filemaker', 'skip_ssl', fallback=False)


def fm_request(url, data=None, headers=None, method=None):
    ctx = ssl.create_default_context()
    if FM_SKIP_SSL:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        return json.loads(urllib.request.urlopen(req, timeout=5, context=ctx).read())
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        print(f'HTTP {e.code} {e.reason}\n{body}', file=sys.stderr)
        raise

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
        data=json.dumps({'fieldData': {'fanrTelefonnummer': number}}).encode(),
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
