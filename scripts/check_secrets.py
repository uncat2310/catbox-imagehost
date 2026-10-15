"""Reject runtime files and recognizable credentials without printing their values."""
import argparse
import json
from pathlib import PurePosixPath
import re
import subprocess
import sys

PATTERNS = {
    'cloudflare-token': re.compile(rb'cfut_[A-Za-z0-9_-]{35,}'),
    'github-token': re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})'),
    'private-key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----'),
}


def check(history=False, known=()):
    paths = subprocess.check_output(['git', 'ls-files', '-z']).decode().split('\0')
    findings = []
    for path in filter(None, paths):
        name = PurePosixPath(path).name
        if (name == '.env' or name.startswith('.env.') and name != '.env.example'
                or path in {'config/settings.json', 'config/settings.db'}
                or name.endswith(('.pem', '.key', '.sqlite', '.sqlite3'))):
            findings.append({'path': path, 'kind': 'runtime-or-key-file'})
    if history:
        objects = subprocess.check_output(['git', 'rev-list', '--objects', '--all']).decode().splitlines()
        targets = [line.split(' ', 1) for line in objects]
    else:
        targets = [[path, path] for path in filter(None, paths)]
    scanned = 0
    for target in targets:
        if len(target) != 2:
            continue
        ref, path = target
        if history:
            kind = subprocess.check_output(['git', 'cat-file', '-t', ref]).strip()
            if kind != b'blob':
                continue
            content = subprocess.check_output(['git', 'cat-file', 'blob', ref])
        else:
            from pathlib import Path
            content = Path(path).read_bytes()
        scanned += 1
        for name, pattern in PATTERNS.items():
            if pattern.search(content):
                findings.append({'path': path, 'kind': name, 'object': ref if history else None})
        if any(secret and secret in content for secret in known):
            findings.append({'path': path, 'kind': 'known-private-value', 'object': ref if history else None})
    print(json.dumps({'scanned_blobs': scanned, 'findings': findings}, indent=2))
    return bool(findings)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--history', action='store_true')
    parser.add_argument('--known-from-stdin', action='store_true')
    args = parser.parse_args()
    known = [value.encode() for value in json.load(sys.stdin)] if args.known_from_stdin else []
    sys.exit(check(args.history, known))
