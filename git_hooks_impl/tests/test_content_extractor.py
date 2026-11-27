#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Unit tests for content_extractor.py — Jira/GitLab context extraction.

Run: python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_content_extractor.py" -v
"""

import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from git_hooks_impl.content_extractor import (
    _discover_sub_resources,
    _download_attachment,
    _parse_jira_links,
    _parse_required_resources,
    _write_resources_debug_cache,
)
from git_hooks_impl.plan.context import AvailableResources, Evidence

# ---------------------------------------------------------------------------
#  Module-level log silencing — prevent TESTS.log pollution
# ---------------------------------------------------------------------------

_log_patchers = []

def setUpModule():
    targets = [
        'git_hooks_impl.content_extractor.dbg',
        'git_hooks_impl.content_extractor.log',
        'git_hooks_impl.content_extractor.warn',
    ]
    for t in targets:
        p = patch(t)
        p.start()
        _log_patchers.append(p)

def tearDownModule():
    for p in _log_patchers:
        p.stop()
    _log_patchers.clear()


# ---------------------------------------------------------------------------
#  Jira link parsing
# ---------------------------------------------------------------------------

class TestJiraLinkParsing(unittest.TestCase):
    """Parse linked tickets and attachments from Jira raw JSON."""

    def test_extracts_linked_tickets(self):
        """Issuelinks with outwardIssue -> ticket ID + relation."""
        raw = json.dumps({'fields': {'issuelinks': [{
            'type': {'outward': 'clones'},
            'outwardIssue': {
                'key': 'PROJ-123',
                'fields': {'summary': 'Related bug'},
            },
        }]}})
        resources = _parse_jira_links(raw)
        self.assertEqual(len(resources.jira_tickets), 1)
        self.assertEqual(resources.jira_tickets[0]['id'], 'PROJ-123')
        self.assertEqual(resources.jira_tickets[0]['relation'], 'clones')

    def test_extracts_inward_links(self):
        """Issuelinks with inwardIssue -> ticket ID + inward relation."""
        raw = json.dumps({'fields': {'issuelinks': [{
            'type': {'inward': 'is cloned by'},
            'inwardIssue': {
                'key': 'PROJ-456',
                'fields': {'summary': 'Clone source'},
            },
        }]}})
        resources = _parse_jira_links(raw)
        self.assertEqual(resources.jira_tickets[0]['id'], 'PROJ-456')

    def test_extracts_attachments(self):
        """fields.attachment array -> filename, type, size, url."""
        raw = json.dumps({'fields': {'attachment': [{
            'filename': 'screenshot.png',
            'mimeType': 'image/png',
            'size': 28000,
            'content': 'https://jira.example.com/attachment/123/screenshot.png',
        }]}})
        resources = _parse_jira_links(raw)
        self.assertEqual(len(resources.attachments), 1)
        self.assertEqual(resources.attachments[0]['filename'], 'screenshot.png')
        self.assertEqual(resources.attachments[0]['type'], 'image/png')

    def test_extracts_mr_references_from_description(self):
        """!10659 in description -> gitlab_mrs list."""
        raw = json.dumps({'fields': {
            'description': 'See MR !10659 for the change',
        }})
        resources = _parse_jira_links(raw)
        self.assertEqual(len(resources.gitlab_mrs), 1)
        self.assertEqual(resources.gitlab_mrs[0]['id'], '10659')

    def test_extracts_mr_from_comments(self):
        """!456 in comment body -> gitlab_mrs list."""
        raw = json.dumps({'fields': {
            'comment': {'comments': [
                {'body': 'Check !456 and !789'},
            ]},
        }})
        resources = _parse_jira_links(raw)
        mr_ids = {m['id'] for m in resources.gitlab_mrs}
        self.assertIn('456', mr_ids)
        self.assertIn('789', mr_ids)

    def test_empty_json_returns_empty(self):
        """Malformed JSON -> empty AvailableResources."""
        resources = _parse_jira_links('not json')
        self.assertEqual(len(resources.jira_tickets), 0)
        self.assertEqual(len(resources.attachments), 0)

    def test_no_links_returns_empty(self):
        """Ticket with no links or attachments -> empty lists."""
        raw = json.dumps({'fields': {}})
        resources = _parse_jira_links(raw)
        self.assertEqual(len(resources.jira_tickets), 0)


# ---------------------------------------------------------------------------
#  Required resources parsing
# ---------------------------------------------------------------------------

class TestRequiredResourcesParsing(unittest.TestCase):
    """Parse REQUIRED_RESOURCES JSON from step 1 output."""

    def _make_available(self):
        return AvailableResources(
            jira_tickets=[{'id': 'PROJ-123', 'relation': 'clones', 'summary': ''}],
            gitlab_mrs=[{'id': '456', 'title': '', 'state': '', 'mentioned_in': ''}],
            attachments=[
                {'filename': 'research.md', 'type': 'text', 'size': 11000, 'url': ''},
                {'filename': 'chart.png', 'type': 'image/png', 'size': 83000, 'url': ''},
            ],
        )

    def test_parses_valid_json(self):
        """Valid REQUIRED_RESOURCES JSON -> list of (type, id) tuples."""
        output = (
            '<!-- PLAN_CONTENT -->\n# Plan\n<!-- PLAN_STEP: OK -->\n'
            '<!-- REQUIRED_RESOURCES -->\n'
            '{"jira_tickets": ["PROJ-123"], "gitlab_mrs": ["456"], '
            '"attachments": ["research.md"]}\n'
            '<!-- /REQUIRED_RESOURCES -->'
        )
        result = _parse_required_resources(output, self._make_available())
        self.assertEqual(len(result), 3)
        self.assertIn(('jira_ticket', 'PROJ-123'), result)
        self.assertIn(('gitlab_mr', '456'), result)
        self.assertIn(('attachment', 'research.md'), result)

    def test_ignores_malformed_ids(self):
        """Malformed ID (doesn't match Jira ticket pattern) -> silently ignored."""
        output = (
            '<!-- REQUIRED_RESOURCES -->\n'
            '{"jira_tickets": ["not-a-ticket"]}\n'
            '<!-- /REQUIRED_RESOURCES -->'
        )
        result = _parse_required_resources(output, self._make_available())
        self.assertEqual(len(result), 0)

    def test_well_formed_ticket_not_in_pool_is_validated_on_demand(self):
        """Well-formed ticket ID not pre-discovered -> validated (on-demand fetch)."""
        output = (
            '<!-- REQUIRED_RESOURCES -->\n'
            '{"jira_tickets": ["PROJECTNAME-9999"]}\n'
            '<!-- /REQUIRED_RESOURCES -->'
        )
        result = _parse_required_resources(output, self._make_available())
        self.assertIn(('jira_ticket', 'PROJECTNAME-9999'), result)

    def test_well_formed_mr_id_not_in_pool_is_validated_on_demand(self):
        """Well-formed numeric MR id not pre-discovered -> validated (on-demand fetch)."""
        output = (
            '<!-- REQUIRED_RESOURCES -->\n'
            '{"gitlab_mrs": ["789"]}\n'
            '<!-- /REQUIRED_RESOURCES -->'
        )
        result = _parse_required_resources(output, self._make_available())
        self.assertIn(('gitlab_mr', '789'), result)

    def test_malformed_mr_id_is_dropped(self):
        """Non-numeric MR id -> dropped."""
        output = (
            '<!-- REQUIRED_RESOURCES -->\n'
            '{"gitlab_mrs": ["not-a-number"]}\n'
            '<!-- /REQUIRED_RESOURCES -->'
        )
        result = _parse_required_resources(output, self._make_available())
        self.assertEqual(len(result), 0)

    def test_empty_json_returns_empty(self):
        """Empty JSON object -> empty list."""
        output = '<!-- REQUIRED_RESOURCES -->\n{}\n<!-- /REQUIRED_RESOURCES -->'
        result = _parse_required_resources(output, self._make_available())
        self.assertEqual(len(result), 0)

    def test_malformed_json_returns_empty(self):
        """Invalid JSON -> warning, empty list."""
        output = '<!-- REQUIRED_RESOURCES -->\nnot json\n<!-- /REQUIRED_RESOURCES -->'
        result = _parse_required_resources(output, self._make_available())
        self.assertEqual(len(result), 0)

    def test_no_section_returns_empty(self):
        """No REQUIRED_RESOURCES tags -> empty list."""
        output = '# Plan content without resources section'
        result = _parse_required_resources(output, self._make_available())
        self.assertEqual(len(result), 0)

    def test_mixed_types_all_validated(self):
        """Tickets + MRs + attachments -> all resolved."""
        output = (
            '<!-- REQUIRED_RESOURCES -->\n'
            '{"jira_tickets": ["PROJ-123"], "gitlab_mrs": ["456"], '
            '"attachments": ["research.md", "chart.png"]}\n'
            '<!-- /REQUIRED_RESOURCES -->'
        )
        result = _parse_required_resources(output, self._make_available())
        self.assertEqual(len(result), 4)


# ---------------------------------------------------------------------------
#  Resources debug cache
# ---------------------------------------------------------------------------

class TestWriteResourcesDebugCache(unittest.TestCase):
    """_write_resources_debug_cache — writes debug info to gen_cache/resources.json."""

    def test_writes_valid_json_with_expected_keys(self):
        """Normal debug_info -> gen_cache/resources.json with the four keys."""


        debug_info = {
            'available': {'jira_tickets': ['PROJ-1'], 'gitlab_mrs': [], 'attachments': []},
            'requested': {'jira_tickets': ['PROJ-1']},
            'validated': [('jira_ticket', 'PROJ-1')],
            'dropped': [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('git_hooks_impl.content_extractor._CACHE_DIR', tmpdir), \
                 patch('git_hooks_impl.content_extractor.run',
                       return_value=(0, 'feature/my-branch\n', '')):
                _write_resources_debug_cache(debug_info)

            sanitized = 'feature_mybranch'
            cache_path = os.path.join(tmpdir, sanitized, 'gen_cache', 'resources.json')
            self.assertTrue(os.path.isfile(cache_path))
            with open(cache_path, encoding='utf-8') as f:
                parsed = json.load(f)
            self.assertEqual(
                set(parsed.keys()), {'available', 'requested', 'validated', 'dropped'})

    def test_empty_debug_info_is_noop(self):
        """Falsy debug_info -> no file written, no exception."""


        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('git_hooks_impl.content_extractor._CACHE_DIR', tmpdir), \
                 patch('git_hooks_impl.content_extractor.run',
                       return_value=(0, 'feature/my-branch\n', '')):
                _write_resources_debug_cache({})

            entries = os.listdir(tmpdir)
            self.assertEqual(entries, [])

    def test_oserror_on_write_is_swallowed(self):
        """OSError while writing -> swallowed, no exception propagates."""


        with tempfile.TemporaryDirectory() as tmpdir, \
             patch('git_hooks_impl.content_extractor._CACHE_DIR', tmpdir), \
             patch('git_hooks_impl.content_extractor.run',
                   return_value=(0, 'feature/my-branch\n', '')), \
             patch('builtins.open', side_effect=OSError('disk full')):
            _write_resources_debug_cache({'available': {}, 'requested': {},
                                          'validated': [], 'dropped': []})
            # No exception raised — test passes by reaching this point.


# ---------------------------------------------------------------------------
#  Evidence data class
# ---------------------------------------------------------------------------

class TestEvidence(unittest.TestCase):
    """Evidence dataclass field defaults."""

    def test_text_evidence_defaults(self):
        """Text evidence has empty image_bytes."""
        evidence = Evidence(
            source_type='jira_ticket', source_id='PROJ-123',
            title='Bug', relation='clones', mentioned_in='PROJ-100',
            content='ticket content',
        )
        self.assertEqual(evidence.image_bytes, b'')
        self.assertEqual(evidence.content, 'ticket content')

    def test_image_evidence_defaults(self):
        """Image evidence has empty content string."""
        evidence = Evidence(
            source_type='image', source_id='screenshot.png',
            title='screenshot.png', relation='attachment',
            mentioned_in='PROJ-100',
            image_bytes=b'\x89PNG', mime_type='image/png',
        )
        self.assertEqual(evidence.content, '')
        self.assertEqual(evidence.image_bytes, b'\x89PNG')


# ---------------------------------------------------------------------------
#  AvailableResources serialization
# ---------------------------------------------------------------------------

class TestAvailableResources(unittest.TestCase):
    """AvailableResources JSON serialization."""

    def test_to_json_roundtrip(self):
        """to_json() produces parseable JSON with all fields."""
        resources = AvailableResources(
            jira_tickets=[{'id': 'PROJ-1', 'relation': 'clones', 'summary': 'x'}],
            gitlab_mrs=[{'id': '42', 'title': 'Fix', 'state': 'merged', 'mentioned_in': 'desc'}],
        )
        parsed = json.loads(resources.to_json())
        self.assertEqual(parsed['jira_tickets'][0]['id'], 'PROJ-1')
        self.assertEqual(parsed['gitlab_mrs'][0]['id'], '42')


# ---------------------------------------------------------------------------
#  ADF (Atlassian Document Format) dict handling
# ---------------------------------------------------------------------------

class TestParseJiraLinksADFFormat(unittest.TestCase):
    """Jira Cloud returns ADF dicts for description/body; old Jira Server returns strings."""

    def test_adf_description_does_not_crash(self):
        """ADF dict as description -> stringified, ticket ID still found."""
        adf_raw = json.dumps({
            'fields': {
                'description': {
                    'type': 'doc',
                    'content': [{'type': 'paragraph', 'content': [
                        {'type': 'text', 'text': 'Related to PROJECTNAME-12345'}
                    ]}]
                },
                'issuelinks': [],
                'attachment': [],
                'comment': {'comments': []},
            }
        })
        resources = _parse_jira_links(adf_raw)
        ticket_ids = {t['id'] for t in resources.jira_tickets}
        self.assertIn('PROJECTNAME-12345', ticket_ids)

    def test_adf_comment_body_does_not_crash(self):
        """ADF dict as comment body -> stringified, MR reference still found."""
        adf_raw = json.dumps({
            'fields': {
                'description': '',
                'issuelinks': [],
                'attachment': [],
                'comment': {'comments': [{
                    'body': {
                        'type': 'doc',
                        'content': [{'type': 'paragraph', 'content': [
                            {'type': 'text', 'text': 'See !4242'}
                        ]}]
                    }
                }]},
            }
        })
        resources = _parse_jira_links(adf_raw)
        mr_ids = {mr['id'] for mr in resources.gitlab_mrs}
        self.assertIn('4242', mr_ids)


class TestDownloadAttachmentAsync(unittest.IsolatedAsyncioTestCase):
    """_download_attachment(attachment_meta, original_ticket) uses aiohttp.ClientSession."""

    def _make_session_mock(self, read_bytes):
        """Build aiohttp ClientSession mock for async-with double-context pattern."""
        mock_response = MagicMock()
        mock_response.read = AsyncMock(return_value=read_bytes)

        mock_get_ctx = MagicMock()
        mock_get_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_get_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_get_ctx)

        return mock_session

    async def test_image_attachment_returns_evidence_with_image_bytes(self):
        """Aiohttp GET success for image -> Evidence with image_bytes set."""

        png_bytes = b'\x89PNG\r\n'
        attachment_meta = {
            'url': 'https://jira.example.com/attach/1',
            'filename': 'screenshot.png',
            'type': 'image/png',
            'size': len(png_bytes),
        }
        mock_session = self._make_session_mock(png_bytes)

        with patch('git_hooks_impl.content_extractor.aiohttp.ClientSession',
                   return_value=mock_session), \
             patch.dict(os.environ, {'JIRA_API_TOKEN': 'fake-token'}):
            result = await _download_attachment(attachment_meta, 'PROJECTNAME-1')

        self.assertIsNotNone(result)
        self.assertIsInstance(result, Evidence)
        self.assertEqual(result.source_type, 'image')
        self.assertEqual(result.image_bytes, png_bytes)

    async def test_missing_token_returns_none(self):
        """JIRA_API_TOKEN not set -> returns None without making network call."""

        attachment_meta = {
            'url': 'https://jira.example.com/attach/2',
            'filename': 'doc.png',
            'type': 'image/png',
            'size': 100,
        }
        env_without_token = {k: v for k, v in os.environ.items()
                             if k != 'JIRA_API_TOKEN'}
        with patch.dict(os.environ, env_without_token, clear=True):
            result = await _download_attachment(attachment_meta, 'PROJECTNAME-1')

        self.assertIsNone(result)


# ---------------------------------------------------------------------------
#  _discover_sub_resources — parallel fetch
# ---------------------------------------------------------------------------

class TestDiscoverSubResources(unittest.IsolatedAsyncioTestCase):
    """_discover_sub_resources uses asyncio.gather for parallel network calls."""

    async def test_merges_sub_ticket_attachments_and_mr_refs(self):
        """Linked Jira ticket's attachments + MR refs are merged into available."""

        linked_raw = json.dumps({
            'fields': {
                'description': 'See !99',
                'issuelinks': [],
                'attachment': [{'filename': 'shot.png', 'mimeType': 'image/png',
                                'size': 100, 'content': 'https://jira/shot.png'}],
                'comment': {'comments': []},
            }
        })
        available = AvailableResources(
            jira_tickets=[{'id': 'PROJ-2', 'relation': 'clones', 'summary': ''}],
            gitlab_mrs=[],
            attachments=[],
        )

        with patch('git_hooks_impl.content_extractor.run_async',
                   new_callable=AsyncMock,
                   return_value=(0, linked_raw, '')), \
             patch('git_hooks_impl.content_extractor.find_tool', return_value=''), \
             patch('git_hooks_impl.content_extractor.log'), \
             patch('git_hooks_impl.content_extractor.dbg'):
            await _discover_sub_resources(available)

        self.assertEqual(len(available.attachments), 1)
        self.assertEqual(available.attachments[0]['filename'], 'shot.png')
        self.assertEqual(available.attachments[0]['via'], 'PROJ-2')
        mr_ids = {m['id'] for m in available.gitlab_mrs}
        self.assertIn('99', mr_ids)

    async def test_empty_available_is_noop(self):
        """No linked tickets + no MRs -> run_async never called."""

        available = AvailableResources()
        mock_run = AsyncMock()
        with patch('git_hooks_impl.content_extractor.run_async', mock_run), \
             patch('git_hooks_impl.content_extractor.find_tool', return_value=''), \
             patch('git_hooks_impl.content_extractor.log'), \
             patch('git_hooks_impl.content_extractor.dbg'):
            await _discover_sub_resources(available)

        mock_run.assert_not_called()

    async def test_failed_jira_fetch_is_skipped(self):
        """Jira ticket fetch failure (exit_code != 0) -> ticket skipped, no crash."""

        available = AvailableResources(
            jira_tickets=[{'id': 'PROJ-3', 'relation': 'clones', 'summary': ''}],
        )
        with patch('git_hooks_impl.content_extractor.run_async',
                   new_callable=AsyncMock,
                   return_value=(1, '', 'error')), \
             patch('git_hooks_impl.content_extractor.find_tool', return_value=''), \
             patch('git_hooks_impl.content_extractor.log'), \
             patch('git_hooks_impl.content_extractor.dbg'):
            await _discover_sub_resources(available)

        self.assertEqual(len(available.attachments), 0)
