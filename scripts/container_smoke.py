"""Verify the built container with ephemeral fake credentials and no real uploads."""
import base64
import json
import secrets
import subprocess
import time
import urllib.error
import urllib.request

password = secrets.token_urlsafe(32)
name = 'catbox-smoke-' + secrets.token_hex(4)
image = 'catbox-smoke:ci'
credential = 'smoke-only-not-a-real-catbox-credential'


def request(port, path, auth=False):
    headers = {}
    if auth:
        headers['Authorization'] = 'Basic ' + base64.b64encode(('admin:' + password).encode()).decode()
    try:
        response = urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}' + path, headers=headers), timeout=4)
    except urllib.error.HTTPError as error:
        response = error
    return response.code, response.read()


try:
    subprocess.run(['docker', 'run', '-d', '--name', name, '-p', '127.0.0.1::7800',
                    '-e', 'CATBOX_USERHASH=' + credential, '-e', 'APP_PASSWORD=' + password, image], check=True, capture_output=True)
    mapping = subprocess.check_output(['docker', 'port', name, '7800']).decode().strip()
    port = int(mapping.rsplit(':', 1)[1])
    for _ in range(30):
        try:
            status, body = request(port, '/api/health')
            if status == 200 and json.loads(body)['version'] == '4.1.0':
                break
        except (OSError, ValueError):
            pass
        time.sleep(.5)
    else:
        raise RuntimeError('Container failed to become healthy')
    assert request(port, '/')[0] == 401
    status, body = request(port, '/', True)
    assert status == 200
    assert b'btn-export' not in body and b'btn-import' not in body
    assert password.encode() not in body and credential.encode() not in body
    assert request(port, '/api/history', True)[0] == 200
    assert request(port, '/api/export', True)[0] == 404
    command = subprocess.check_output(['docker', 'exec', name, 'sh', '-c', "grep '^Uid:' /proc/1/status"]).decode().split()
    assert command[1] != '0', 'Application is running as root'
    subprocess.run(['docker', 'restart', name], check=True, capture_output=True)
    for _ in range(30):
        try:
            if request(port, '/api/history', True)[0] == 200:
                break
        except OSError:
            pass
        time.sleep(.5)
    else:
        raise RuntimeError('Container failed after restart')
    print('Container authentication, private settings, non-root process, and restart checks passed.')
finally:
    subprocess.run(['docker', 'rm', '-f', name], check=False, capture_output=True)
