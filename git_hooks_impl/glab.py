#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""GitLab CLI (glab) wrappers — API GET/POST and current user lookup.
"""

import contextlib
import json
import re

from git_hooks_impl.logger import warn
from git_hooks_impl.utils import run_async

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

GITLAB_HOST = 'gitlab.companyname.com'
GLAB_PAT_URL = f'https://{GITLAB_HOST}/-/user_settings/personal_access_tokens'


# ---------------------------------------------------------------------------
#  API helpers
# ---------------------------------------------------------------------------

async def glab_api(path):
    """GET a GitLab API path. Returns parsed JSON or None on failure."""
    exit_code, out, stderr = await run_async(['glab', 'api', path, '--hostname', GITLAB_HOST])
    if exit_code != 0:
        warn(f"glab api '{path}' failed (exit_code={exit_code}): {stderr.strip()}")
        return None
    try:
        return json.loads(out)
    except (json.JSONDecodeError, ValueError) as exc:
        warn(f"glab api '{path}' returned invalid JSON: {exc}")
        return None


async def glab_api_post(path, fields):
    """POST to GitLab API with JSON body via stdin. Returns parsed JSON or None.

    Delegates to glab_api_write for stdin-based delivery,
    avoiding Windows 32K CLI argument limit.

    glab_api_post('projects/:id/merge_requests/5/discussions', {'body': 'hello'})
    -> {'id': 'abc123', ...}
    """
    exit_code, parsed, stderr = await glab_api_write(path, fields, method='POST')
    if exit_code != 0:
        warn(f"glab api POST '{path}' failed (exit_code={exit_code}): {stderr.strip()}")
        return None
    return parsed


async def glab_api_write(path, body_dict, method='POST'):
    """POST/PUT to GitLab API with JSON body via stdin.

    Avoids Windows 32K command-line argument limit by piping JSON
    through stdin instead of passing as CLI arguments.

    Returns (exit_code, parsed_response_or_None, stderr).
    """
    body_json = json.dumps(body_dict)
    exit_code, stdout, stderr = await run_async(
        ['glab', 'api', path, '--method', method,
         '--hostname', GITLAB_HOST,
         '--header', 'Content-Type: application/json',
         '--input', '-'],
        input=body_json,
    )
    parsed = None
    if exit_code == 0 and stdout.strip():
        with contextlib.suppress(json.JSONDecodeError):
            parsed = json.loads(stdout)
    return exit_code, parsed, stderr


async def current_user():
    """Return the glab-authenticated username, or empty string on failure."""
    data = await glab_api('user')
    if isinstance(data, dict):
        username = data.get('username', '')
        if username:
            return username
        warn("glab api 'user' returned no username field")
    else:
        warn('Could not fetch current user from GitLab API')
    return ''


# ---------------------------------------------------------------------------
#  Git remote helpers
# ---------------------------------------------------------------------------

async def get_project_path():
    """Return the GitLab project path from the git remote URL.

    'git@gitlab.companyname.com:group/productname/reponame.git' -> 'group/productname/reponame'
    'git@gitlab.companyname.com:group/productname/reponame.git' -> 'group/productname/reponame'
    Returns empty string on failure.
    """
    exit_code, remote_url, _ = await run_async(['git', 'remote', 'get-url', 'origin'])
    if exit_code != 0 or not remote_url.strip():
        warn('Could not determine remote URL')
        return ''
    remote_url = remote_url.strip()
    project_match = re.search(r'[:/]([^:/]+/[^/]+?)(?:\.git)?$', remote_url)
    if not project_match:
        warn(f"Could not parse project path from '{remote_url}'")
        return ''
    return project_match.group(1)
