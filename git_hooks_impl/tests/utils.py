#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Shared utilities for integration tests.
Not imported by production code.
"""

import io
import os
import shutil
import sys
import urllib.request

from git_hooks_impl.branch_utils import _embed_body_hash
from git_hooks_impl.entry_points.sync_mr import _map_plan_to_body
from git_hooks_impl.plan.parser import plan_footer, visible_plan_body


def build_mr_description(plan_content):
    """Build an MR description as create_mr() assembles it for a plan-only body.

    plan_content: raw PLAN.md content.
    """
    return visible_plan_body(plan_content) + plan_footer(plan_content)


def build_full_mr_description(plan_content, clean_body=''):
    """Build an MR description via the same assembly as update_mr().

    plan_content: raw PLAN.md content.
    clean_body:   existing MR body with managed sections stripped (may
                  contain a Checklist section to preserve).
    """

    base_desc = _map_plan_to_body(clean_body, plan_content)
    new_desc = base_desc + plan_footer(plan_content)
    return _embed_body_hash(new_desc)


def download(url):
    """Download url and return BytesIO. Raises on failure."""
    response = urllib.request.urlopen(url, timeout=60)
    return io.BytesIO(response.read())


def uninstall_jira():
    """Remove jira binary and config. Returns True if binary was present."""
    exe = 'jira.exe' if sys.platform == 'win32' else 'jira'
    binary = os.path.join(os.path.expanduser('~/bin'), exe)
    config_dir = os.path.expanduser('~/.config/.jira')

    removed = False
    if os.path.isfile(binary):
        os.remove(binary)
        removed = True

    if os.path.isdir(config_dir):
        shutil.rmtree(config_dir)

    return removed


def uninstall_glab():
    """Remove glab auth config directory. Returns True if it existed."""
    glab_config = os.path.join(
        os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
        'glab-cli',
    )
    if os.path.isdir(glab_config):
        shutil.rmtree(glab_config)
        return True
    return False
