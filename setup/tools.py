#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Install glab, jira, claude CLIs; prompt for token values.

Port of git_hooks_impl/entry_points/check_tools.py extended with token-
prompting from setup_env.py. Tokens are collected into a dict and handed
to install_profiles.write_managed_block for insertion in ~/.bashrc.

No .env/env writes — the .env/ loader system is dropped per master plan.
"""

import io
import os
import platform
import shutil
import socket
import stat
import sys
import tarfile
import urllib.request
import webbrowser
import zipfile

from git_hooks_impl.glab import GITLAB_HOST, GLAB_PAT_URL
from git_hooks_impl.jira import JIRA_PAT_URL, JIRA_SERVER, JIRA_VERSION
from git_hooks_impl.logger import dbg, err, log, ok, warn
from git_hooks_impl.utils import add_env_path, prompt_input, prompt_yn, run, run_interactive
from setup.install_profiles import write_managed_block

# ---------------------------------------------------------------------------
#  glab installation / auth
# ---------------------------------------------------------------------------

def _install_glab_windows() -> bool:
    """Install glab on Windows via winget. Returns True on success."""
    if not shutil.which('winget'):
        err('winget not found — cannot auto-install glab')
        err('  Manual install: https://gitlab.com/gitlab-org/cli/-/releases')
        return False
    log('Installing glab via winget...')
    if run_interactive(['winget', 'install', 'GLab.GLab']) != 0:
        err('winget install failed')
        return False
    local_app_data = os.environ.get('LOCALAPPDATA', '')
    if local_app_data:
        glab_dir = os.path.join(local_app_data, 'Programs', 'glab')
        add_env_path(glab_dir)
    return True


def _install_glab_unix() -> bool:
    """Install glab on macOS/Linux via Homebrew. Returns True on success."""
    if not shutil.which('brew'):
        err('Homebrew not found — cannot auto-install glab')
        err('  Manual install: https://gitlab.com/gitlab-org/cli/-/releases')
        return False
    log('Installing glab via brew...')
    if run_interactive(['brew', 'install', 'glab']) != 0:
        err('brew install failed')
        return False
    return True


def _install_glab() -> bool:
    """Install glab. Returns True on success."""
    match sys.platform:
        case 'win32':
            ok_install = _install_glab_windows()
        case _:
            ok_install = _install_glab_unix()
    if not ok_install:
        return False
    ok('glab installed')
    return _auth_glab()


def _auth_glab() -> bool:
    """Run glab auth login interactively. Returns True on success."""
    log('Opening browser to create a GitLab PAT...')
    log('  Required scopes: api, read_repository, write_repository')
    webbrowser.open(GLAB_PAT_URL)
    log('Paste the token when prompted below:')
    exit_code = run_interactive(['glab', 'auth', 'login', '--hostname', GITLAB_HOST])
    if exit_code != 0:
        err('glab authentication failed')
        return False
    ok(f'glab authenticated to {GITLAB_HOST}')
    return True


def _prompt_glab_token(tokens: dict) -> None:
    """Prompt for GLAB_TOKEN and record in tokens dict."""
    existing = os.environ.get('GLAB_TOKEN', '')
    if existing:
        dbg('GLAB_TOKEN already set — skipping prompt')
        tokens['GLAB_TOKEN'] = existing
        return
    log('Opening browser to create a GitLab PAT (scopes: api, read_repository, write_repository)...')
    webbrowser.open(GLAB_PAT_URL)
    value = prompt_input('Paste your GLAB_TOKEN')
    if value:
        tokens['GLAB_TOKEN'] = value


# ---------------------------------------------------------------------------
#  jira installation / setup
# ---------------------------------------------------------------------------

def _jira_download_url(os_name: str, arch: str) -> str:
    ext = 'zip' if os_name == 'windows' else 'tar.gz'
    return (
        f'https://github.com/ankitpokhrel/jira-cli/releases/download/'
        f'v{JIRA_VERSION}/jira_{JIRA_VERSION}_{os_name}_{arch}.{ext}'
    )


def _extract_jira_windows(archive_data: io.BytesIO, target: str) -> bool:
    """Extract jira.exe from zip archive."""
    with zipfile.ZipFile(archive_data) as zf:
        exe_entry = next((n for n in zf.namelist() if n.endswith('jira.exe')), None)
        if not exe_entry:
            err('Could not find jira.exe in downloaded archive')
            return False
        with zf.open(exe_entry) as src, open(target, 'wb') as dst:
            dst.write(src.read())
    return True


def _extract_jira_unix(archive_data: io.BytesIO, target: str) -> bool:
    """Extract jira binary from tar.gz archive and make it executable."""
    with tarfile.open(fileobj=archive_data, mode='r:gz') as tf:
        exe_member = next(
            (m for m in tf.getmembers() if m.name.endswith('/jira') or m.name == 'jira'),
            None,
        )
        if not exe_member:
            err('Could not find jira binary in downloaded archive')
            return False
        src = tf.extractfile(exe_member)
        with open(target, 'wb') as dst:
            dst.write(src.read())
    os.chmod(target, os.stat(target).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return True


def _install_jira() -> bool:
    """Download and install jira CLI. Returns True on success."""
    bin_dir = os.path.expanduser('~/bin')
    os.makedirs(bin_dir, exist_ok=True)

    match sys.platform:
        case 'win32':
            os_name, arch, exe, extract = 'windows', 'x86_64', 'jira.exe', _extract_jira_windows
        case 'darwin':
            machine = platform.machine().lower()
            arch = 'arm64' if machine in ('arm64', 'aarch64') else 'x86_64'
            os_name, exe, extract = 'darwin', 'jira', _extract_jira_unix
        case _:
            machine = platform.machine().lower()
            arch = 'arm64' if machine in ('arm64', 'aarch64') else 'x86_64'
            os_name, exe, extract = 'linux', 'jira', _extract_jira_unix

    url = _jira_download_url(os_name, arch)
    target = os.path.join(bin_dir, exe)

    log(f'Downloading jira CLI v{JIRA_VERSION} for {os_name}/{arch}...')
    try:
        archive_data = io.BytesIO(urllib.request.urlopen(url, timeout=30).read())
    except Exception as exc:
        err(f'Download failed: {exc}')
        err(f'  Manual download: {url}')
        return False
    if not extract(archive_data, target):
        return False

    ok(f'jira installed to {target}')
    add_env_path(bin_dir)
    return True


def _setup_jira(tokens: dict) -> bool:
    """Configure jira CLI config file. Returns True on success."""
    # PAT
    token = tokens.get('JIRA_API_TOKEN') or os.environ.get('JIRA_API_TOKEN', '')
    if not token:
        log('Opening browser to Jira (log in if not already)...')
        webbrowser.open(JIRA_PAT_URL)
        log('  Walk: Profile image -> Account settings -> Security -> Manage API tokens')
        log("  Name the token: 'Jira API cloud token'")
        token = prompt_input('Paste your Jira PAT')
        if not token:
            warn('Empty token — skipped. Set JIRA_API_TOKEN manually later.')
            return False
    tokens['JIRA_API_TOKEN'] = token

    # Email (Cloud login)
    email = prompt_input('Your Jira login email')
    if not email:
        warn('Empty email — skipped')
        return False

    # Default project
    project = prompt_input('Default Jira project', default='PROJECTNAME')

    # Write config (same format as `jira init` produces)
    config_dir = os.path.expanduser('~/.config/.jira')
    os.makedirs(config_dir, exist_ok=True)
    config_path = os.path.join(config_dir, '.config.yml')
    config = (
        f'installation: Cloud\n'
        f'server: {JIRA_SERVER}\n'
        f'login: {email}\n'
        f'project: {project}\n'
        f'board:\n'
        f'  id: 0\n'
        f'  name: ""\n'
        f'  type: ""\n'
        f'auth_type: basic\n'
    )
    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(config)
    ok(f'jira config written to {config_path}')

    # Verify (inject token into env so jira-cli subprocess can authenticate)
    os.environ['JIRA_API_TOKEN'] = token
    log('Verifying jira connection...')
    exit_code, _out, stderr = run(['jira', 'issue', 'list', '-p', project, '--paginate', '1'])
    if exit_code == 0:
        ok(f'jira connection verified ({project})')
    else:
        is_html = "invalid character '<'" in stderr
        if is_html:
            warn('Jira returned HTML — check installation: Cloud in config, PAT expiry, or VPN')
        else:
            warn(f'Verification failed (exit_code={exit_code}): {stderr.strip()}')
    return True


# ---------------------------------------------------------------------------
#  claude installation / setup
# ---------------------------------------------------------------------------

def _install_claude() -> bool:
    """Install Claude CLI. Returns True on success."""
    log('Installing Claude CLI...')
    match sys.platform:
        case 'win32':
            exit_code = run_interactive([
                'powershell.exe', '-NoProfile', '-Command',
                '& ([scriptblock]::Create((irm https://claude.ai/install.ps1)))',
            ])
        case _:
            if not shutil.which('curl'):
                err('curl not found — cannot auto-install claude')
                err('  Manual install: https://claude.ai/install.sh')
                return False
            exit_code = run_interactive(
                ['bash', '-c', 'curl -fsSL https://claude.ai/install.sh | bash']
            )
    if exit_code != 0:
        err('Claude CLI installation failed')
        return False
    ok('claude installed')
    return True


def _setup_claude_env(tokens: dict) -> bool:
    """Prompt for Anthropic auth token at CompanyName AI_PROXY portal.
    """Prompt for Anthropic auth token at CompanyName AI_PROXY portal.

    Claude Code via the AI_PROXY gateway uses ANTHROPIC_AUTH_TOKEN exclusively.
    We do not collect or set ANTHROPIC_API_KEY — that's the standard-Anthropic
    credential name and isn't needed when routing through AI_PROXY.
    """
    token = tokens.get('ANTHROPIC_AUTH_TOKEN') or os.environ.get('ANTHROPIC_AUTH_TOKEN', '')
    if token:
        dbg('ANTHROPIC_AUTH_TOKEN already set — skipping prompt')
    else:
        log('ANTHROPIC_AUTH_TOKEN is not set.')
        log('  Generate from https://reponameq.companyname.io/developer (Profile -> API key)')
        webbrowser.open('https://reponameq.companyname.io/developer')
        token = prompt_input('Paste your Anthropic auth token (from AI_PROXY)')
        if not token:
            warn('Empty token — skipped. Set ANTHROPIC_AUTH_TOKEN manually later.')
            return False
    tokens['ANTHROPIC_AUTH_TOKEN'] = token
    return True


# ---------------------------------------------------------------------------
#  VPN / network check
# ---------------------------------------------------------------------------

def _check_companyname_network() -> bool:
    """Try a TCP connect to GITLAB_HOST:443. Returns True if reachable."""
    try:
        with socket.create_connection((GITLAB_HOST, 443), timeout=3):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
#  Entry point
# ---------------------------------------------------------------------------

def cmd_install_tools(ai_tooling_src: str) -> int:
    """Install CLIs, prompt for tokens, write ~/.bashrc managed block.

    Replaces both check_tools.py (CLI install/auth) and setup_env.py
    (token prompting + profile writing).
    Returns 0 if all required tools are ready, 1 otherwise.
    """
    tokens: dict = {}

    warn('Make sure you are connected to the CompanyName VPN before installing or authenticating tools.')
    warn('Make sure you are connected to the CompanyName VPN before installing or authenticating tools.')

    log(f'Checking CompanyName network ({GITLAB_HOST})...')
    log(f'Checking CompanyName network ({GITLAB_HOST})...')
    if _check_companyname_network():
        ok(f'CompanyName network reachable ({GITLAB_HOST})')
        ok(f'CompanyName network reachable ({GITLAB_HOST})')
    else:
        err(f'Cannot reach {GITLAB_HOST} — you may be off VPN.')
        err('  Tool downloads (jira, claude) will work without VPN.')
        err('  Auth steps (glab auth login, jira verify) will fail until you connect.')
        if not prompt_yn('Continue anyway?', default_yes=False):
            return 1

    all_ok = True

    # glab — required
    if shutil.which('glab'):
        exit_code, _, _stderr = run(['glab', 'auth', 'status', '--hostname', GITLAB_HOST])
        if exit_code == 0:
            ok(f'glab: installed and authenticated to {GITLAB_HOST}')
            _prompt_glab_token(tokens)
        else:
            err(f'glab: installed but NOT authenticated to {GITLAB_HOST}')
            if prompt_yn('Authenticate glab now?'):
                if _auth_glab():
                    ok(f'glab: now authenticated to {GITLAB_HOST}')
                    _prompt_glab_token(tokens)
                else:
                    all_ok = False
            else:
                all_ok = False
    else:
        err('glab: NOT FOUND (required)')
        if prompt_yn('Install glab?'):
            if _install_glab():
                ok('glab: ready')
                _prompt_glab_token(tokens)
            else:
                all_ok = False
        else:
            all_ok = False

    # jira — optional
    if shutil.which('jira'):
        token = tokens.get('JIRA_API_TOKEN') or os.environ.get('JIRA_API_TOKEN', '')
        if token:
            tokens['JIRA_API_TOKEN'] = token
            ok('jira: installed, JIRA_API_TOKEN set')
        else:
            warn('jira: installed but JIRA_API_TOKEN not set')
            if prompt_yn('Configure Jira auth now?'):
                _setup_jira(tokens)
    else:
        warn('jira: NOT FOUND (optional — needed for AI-assisted MR description)')
        if prompt_yn('Install jira CLI?'):
            if _install_jira():
                _setup_jira(tokens)

    # claude — optional
    if shutil.which('claude'):
        token = tokens.get('ANTHROPIC_AUTH_TOKEN') or os.environ.get('ANTHROPIC_AUTH_TOKEN', '')
        if token:
            tokens['ANTHROPIC_AUTH_TOKEN'] = token
            ok('claude: installed, ANTHROPIC_AUTH_TOKEN set')
        else:
            warn('claude: installed but ANTHROPIC_AUTH_TOKEN not set')
            if prompt_yn('Configure Claude auth token now?'):
                _setup_claude_env(tokens)
    else:
        warn('claude: NOT FOUND (optional — needed for AI-assisted MR description)')
        if prompt_yn('Install Claude CLI?'):
            if _install_claude():
                _setup_claude_env(tokens)

    # Write ~/.bashrc managed block with all collected tokens
    write_managed_block(ai_tooling_src, tokens)

    if all_ok:
        ok('All required tools ready.')
    else:
        err('Some required tools are missing or misconfigured.')

    return 0 if all_ok else 1


if __name__ == '__main__':
    src = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('AI_TOOLING_SRC', '')
    sys.exit(cmd_install_tools(src))
