#!/usr/bin/env python3
"""Post a CI failure log tail to the PR (used by the integration job).

Usage: python3 ci/post_failure.py <pr-number> <log-file>

The PR number may be empty: the script then resolves it through the GitHub API
using GITHUB_REPOSITORY and GITHUB_REF_NAME (works for both push and
pull_request events, with no dependency on the gh CLI).

Exits 0 even when the post fails: diagnostics are best-effort and must never
mask the real test failure.
"""
import json
import os
import sys
import urllib.error
import urllib.request

API_URL = os.environ.get('GITHUB_API_URL', 'https://api.github.com')
REPOSITORY = os.environ.get('GITHUB_REPOSITORY', '')
TOKEN = os.environ.get('GITHUB_TOKEN', '')


def _get_json(url: str) -> list:
    request = urllib.request.Request(
        url,
        headers={
            'Authorization': f'token {TOKEN}',
            'Accept': 'application/vnd.github+json',
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def resolve_pr(provided: str) -> str:
    if provided:
        return str(provided)
    if not (REPOSITORY and TOKEN):
        return ''
    ref = os.environ.get('GITHUB_REF_NAME', '')
    if not ref:
        return ''
    try:
        pulls = _get_json(f'{API_URL}/repos/{REPOSITORY}/pulls?state=open&head={REPOSITORY}:{ref}')
    except (urllib.error.URLError, ValueError) as exc:
        print('PR resolution failed:', exc)
        return ''
    if pulls:
        return str(pulls[0]['number'])
    return ''


def main() -> int:
    if len(sys.argv) < 3:
        print('usage: post_failure.py <pr-number> <log-file>')
        return 2
    pr, log_file = resolve_pr(sys.argv[1]), sys.argv[2]
    if not pr:
        print('no PR found; skipping diagnostics post')
        return 0
    if not (REPOSITORY and TOKEN):
        print('GITHUB_REPOSITORY/GITHUB_TOKEN not set; skipping post')
        return 0
    try:
        log = open(log_file, errors='replace').read()[-8000:]
    except OSError as exc:
        print('cannot read log:', exc)
        return 0
    body = {'body': 'CI failure diagnostics (log tail):\n\n```\n' + log + '\n```'}
    request = urllib.request.Request(
        f'{API_URL}/repos/{REPOSITORY}/issues/{pr}/comments',
        data=json.dumps(body).encode(),
        headers={
            'Authorization': f'token {TOKEN}',
            'Content-Type': 'application/json',
            'Accept': 'application/vnd.github+json',
        },
    )
    try:
        urllib.request.urlopen(request, timeout=30)
        print(f'posted diagnostics to PR #{pr}')
    except urllib.error.HTTPError as exc:
        print(f'diagnostics post failed: HTTP {exc.code} {exc.reason}')
        try:
            print(exc.read().decode(errors='replace')[:500])
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        print('diagnostics post failed:', exc)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
