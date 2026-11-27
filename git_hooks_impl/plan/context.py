#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Plan context dataclasses — pure data containers shared by multiple modules.

Extracted from content_extractor.py so the data model is importable
without pulling in extraction logic (Jira/GitLab API calls, etc.).
"""

import dataclasses
import json


@dataclasses.dataclass
class Evidence:
    """One piece of external evidence fetched for plan enrichment."""
    source_type: str        # 'jira_ticket', 'gitlab_mr', 'text_file', 'image'
    source_id: str          # 'PROJECTNAME-43106', '10659', 'screenshot.png'
    title: str              # short description
    relation: str           # 'clones', 'mentioned in comments'
    mentioned_in: str       # 'PROJECTNAME-43118 Linked Issues section'
    content: str = ''       # text content (empty for images)
    image_bytes: bytes = b''  # raw bytes (empty for text)
    mime_type: str = ''


@dataclasses.dataclass
class AvailableResources:
    """Resources discovered in a Jira ticket, available for download."""
    jira_tickets: list = dataclasses.field(default_factory=list)
    gitlab_mrs: list = dataclasses.field(default_factory=list)
    attachments: list = dataclasses.field(default_factory=list)
    external_links: list = dataclasses.field(default_factory=list)

    def to_json(self):
        """Serialize for prompt injection."""
        return json.dumps(dataclasses.asdict(self), indent=2)


@dataclasses.dataclass
class PlanContext:
    """All context needed by PlanGenerator to produce a plan.

    Also carries MR metadata (labels, assignees) downstream so callers
    like create_mr() don't need to re-fetch from template_skeleton().
    """
    jira_ticket: str = ''
    jira_summary: str = ''
    jira_content: str = ''
    mr_body_template: str = ''
    existing_mr_body: str = ''
    branch_diffs: str = ''
    commit_messages: str = ''
    available_resources: AvailableResources = dataclasses.field(
        default_factory=AvailableResources)
    file_paths_manifest: str = ''
    plan_template: str = ''
    plan_rules: str = ''
    labels: list = dataclasses.field(default_factory=list)
    assignees: list = dataclasses.field(default_factory=list)
    current_branch_diff_stats: str = ''
    stacked_branch_warning: str = ''
    parent_branch_name: str = ''
    parent_branch_sha: str = ''
