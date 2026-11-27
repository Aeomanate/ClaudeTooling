#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Corner-case tests for extract-plan: cmd_planget(), the MR-only PLAN.md
extraction path with no AI generation fallback.

Run:  python -m unittest discover -s .git-hooks/hooks/tests -t .git-hooks -p "test_*.py" -v
"""

import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from git_hooks_impl.entry_points.extract_plan import cmd_planget
from git_hooks_impl.tests.utils import build_mr_description

# Silence ALL logging functions imported by extract_plan, plan_merge, plan_cache
# to prevent any output to TESTS.log.  Tests that assert on specific log calls
# (e.g. mock_flog.assert_any_call) use their own @patch which overrides these.
_log_patchers = [
    # git_hooks_impl.entry_points.extract_plan imports: config, dbg, err, log, ok, warn
    patch('git_hooks_impl.entry_points.extract_plan.log'),
    patch('git_hooks_impl.entry_points.extract_plan.warn'),
    patch('git_hooks_impl.entry_points.extract_plan.err'),
    patch('git_hooks_impl.entry_points.extract_plan.dbg'),
    patch('git_hooks_impl.entry_points.extract_plan.ok'),
    # git_hooks_impl.plan.merge imports: dbg, log, warn
    patch('git_hooks_impl.plan.merge.log'),
    patch('git_hooks_impl.plan.merge.warn'),
    patch('git_hooks_impl.plan.merge.dbg'),
    # git_hooks_impl.plan.cache imports: dbg, log, ok, warn
    patch('git_hooks_impl.plan.cache.log'),
    patch('git_hooks_impl.plan.cache.warn'),
    patch('git_hooks_impl.plan.cache.dbg'),
    patch('git_hooks_impl.plan.cache.ok'),
    # git_hooks_impl.branch_utils imports: dbg, log, warn
    patch('git_hooks_impl.branch_utils.log'),
    patch('git_hooks_impl.branch_utils.warn'),
    patch('git_hooks_impl.branch_utils.dbg'),
    # git_hooks_impl.utils imports: dbg
    patch('git_hooks_impl.utils.dbg'),
]


def setUpModule():
    for p in _log_patchers:
        p.start()


def tearDownModule():
    for p in _log_patchers:
        p.stop()


# ---------------------------------------------------------------------------
#  cmd_planget — extract PLAN.md from MR body with no AI generation
# ---------------------------------------------------------------------------


def _mr_body_with_plan(plan_content):
    """Build an MR description carrying the given plan content."""
    return build_mr_description(plan_content)


class TestCmdPlanget(unittest.IsolatedAsyncioTestCase):
    """Tests for cmd_planget(): MR-only PLAN.md extraction, no AI fallback."""

    @patch('git_hooks_impl.entry_points.extract_plan._discover_branch_and_ticket',
           return_value=(None, None, None))
    async def test_branch_none_returns_0(self, mock_discover):
        """Branch detection fails -> returns 0 immediately, no glab calls.

        When _discover_branch_and_ticket returns (None, None, None), the
        function exits before any network calls.

        Function under test: cmd_planget()
        """
        result = await cmd_planget()
        self.assertEqual(result, 0)

    @patch('git_hooks_impl.entry_points.extract_plan.find_tool', return_value=None)
    @patch('git_hooks_impl.entry_points.extract_plan._discover_branch_and_ticket',
           return_value=('productname/fixes/PROJECTNAME-1_fix', 'fix', 'PROJECTNAME-1'))
           return_value=('productname/fixes/PROJECTNAME-1_fix', 'fix', 'PROJECTNAME-1'))
    async def test_glab_missing_returns_0(self, mock_discover, mock_tool):
        """Glab not in PATH -> warns and returns 0 without calling run().

        Function under test: cmd_planget()
        """
        with patch('git_hooks_impl.entry_points.extract_plan.warn') as mock_warn:
            result = await cmd_planget()
        self.assertEqual(result, 0)
        warn_messages = [str(c) for c in mock_warn.call_args_list]
        self.assertTrue(any('glab not found' in m for m in warn_messages))

    @patch('git_hooks_impl.entry_points.extract_plan.run_async', new_callable=AsyncMock,
           return_value=(0, '[]', ''))
    @patch('git_hooks_impl.entry_points.extract_plan.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.extract_plan._discover_branch_and_ticket',
           return_value=('productname/fixes/PROJECTNAME-1_fix', 'fix', 'PROJECTNAME-1'))
           return_value=('productname/fixes/PROJECTNAME-1_fix', 'fix', 'PROJECTNAME-1'))
    async def test_no_open_mr_returns_0(self, mock_discover, mock_tool, mock_run):
        """Glab returns empty list (no open MR) -> logs message, returns 0.

        Function under test: cmd_planget()
        """
        with patch('git_hooks_impl.entry_points.extract_plan.log') as mock_log:
            result = await cmd_planget()
        self.assertEqual(result, 0)
        log_messages = [str(c) for c in mock_log.call_args_list]
        self.assertTrue(any('No open MR' in m for m in log_messages))

    @patch('git_hooks_impl.entry_points.extract_plan.run_async', new_callable=AsyncMock,
           return_value=(0, '[{"iid":1},{"iid":2}]', ''))
    @patch('git_hooks_impl.entry_points.extract_plan.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.extract_plan._discover_branch_and_ticket',
           return_value=('productname/fixes/PROJECTNAME-1_fix', 'fix', 'PROJECTNAME-1'))
           return_value=('productname/fixes/PROJECTNAME-1_fix', 'fix', 'PROJECTNAME-1'))
    async def test_multiple_mrs_warns_and_returns_0(self, mock_discover, mock_tool, mock_run):
        """Glab returns 2 open MRs -> warns about ambiguity, returns 0.

        Function under test: cmd_planget()
        """
        with patch('git_hooks_impl.entry_points.extract_plan.warn') as mock_warn:
            result = await cmd_planget()
        self.assertEqual(result, 0)
        warn_messages = [str(c) for c in mock_warn.call_args_list]
        self.assertTrue(any('Multiple' in m for m in warn_messages))

    @patch('git_hooks_impl.entry_points.extract_plan.run_async', new_callable=AsyncMock,
           return_value=(0, '[{"iid":1,"description":"No plan section here"}]', ''))
    @patch('git_hooks_impl.entry_points.extract_plan.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.extract_plan._discover_branch_and_ticket',
           return_value=('productname/fixes/PROJECTNAME-1_fix', 'fix', 'PROJECTNAME-1'))
           return_value=('productname/fixes/PROJECTNAME-1_fix', 'fix', 'PROJECTNAME-1'))
    async def test_no_plan_section_logs_and_returns_0(self, mock_discover, mock_tool, mock_run):
        """MR exists but has no PLAN.md section -> reports it, returns 0, no write.

        Unlike gen_plan, cmd_planget does not fall back to AI generation.

        Function under test: cmd_planget()
        """
        with patch('git_hooks_impl.entry_points.extract_plan._write_plan') as mock_write, \
             patch('git_hooks_impl.entry_points.extract_plan.log') as mock_log:
            result = await cmd_planget()
        self.assertEqual(result, 0)
        mock_write.assert_not_called()
        log_messages = [str(c) for c in mock_log.call_args_list]
        self.assertTrue(any('No PLAN.md section' in m for m in log_messages))

    @patch('git_hooks_impl.entry_points.extract_plan._write_plan')
    @patch('git_hooks_impl.entry_points.extract_plan._save_cache')
    @patch('git_hooks_impl.entry_points.extract_plan.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.extract_plan._discover_branch_and_ticket',
           return_value=('productname/fixes/PROJECTNAME-1_fix', 'fix', 'PROJECTNAME-1'))
           return_value=('productname/fixes/PROJECTNAME-1_fix', 'fix', 'PROJECTNAME-1'))
    async def test_plan_section_extracted_and_written(self, mock_discover, mock_tool,
                                                 mock_cache, mock_write):
        """MR has PLAN section and no local file -> extracts and writes plan.

        Function under test: cmd_planget()
        """
        plan_body = '# Plan\n\n- [ ] Step 1\n- [ ] Step 2\n' + 'x' * 100
        description = _mr_body_with_plan(plan_body)
        mr_json = json.dumps([{'iid': 7, 'description': description}])

        with patch('git_hooks_impl.entry_points.extract_plan.run_async', new_callable=AsyncMock,
                   return_value=(0, mr_json, '')), \
             patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', '/nonexistent/PLAN.md'):
            result = await cmd_planget()

        self.assertEqual(result, 0)
        mock_write.assert_called_once()

    @patch('git_hooks_impl.entry_points.extract_plan._write_plan')
    @patch('git_hooks_impl.entry_points.extract_plan._save_cache')
    @patch('git_hooks_impl.entry_points.extract_plan.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.extract_plan._discover_branch_and_ticket',
           return_value=('productname/fixes/PROJECTNAME-1_fix', 'fix', 'PROJECTNAME-1'))
           return_value=('productname/fixes/PROJECTNAME-1_fix', 'fix', 'PROJECTNAME-1'))
    async def test_local_plan_identical_to_mr_is_noop(self, mock_discover, mock_tool,
                                                  mock_cache, mock_write):
        """Local plan matches MR content -> reports up-to-date, no write.

        When strip_meta(local) == strip_meta(remote), cmd_planget skips
        the write and reports the plan is already current.

        Function under test: cmd_planget()
        """
        plan_body = '# Plan\n\n- [ ] Step 1\n' + 'x' * 100
        description = _mr_body_with_plan(plan_body)
        mr_json = json.dumps([{'iid': 7, 'description': description}])

        with tempfile.TemporaryDirectory() as tmp:
            plan_file = os.path.join(tmp, 'PLAN.md')
            # Write same content locally (strip_meta will match)
            with open(plan_file, 'w') as f:
                f.write(plan_body)
            with patch('git_hooks_impl.entry_points.extract_plan.run_async', new_callable=AsyncMock,
                       return_value=(0, mr_json, '')), \
                 patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.entry_points.extract_plan.ok') as mock_ok:
                result = await cmd_planget()

        self.assertEqual(result, 0)
        mock_write.assert_not_called()
        ok_messages = [str(c) for c in mock_ok.call_args_list]
        self.assertTrue(any('up to date' in m for m in ok_messages))

    @patch('git_hooks_impl.entry_points.extract_plan._write_plan')
    @patch('git_hooks_impl.entry_points.extract_plan._save_cache')
    @patch('git_hooks_impl.entry_points.extract_plan.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.extract_plan._discover_branch_and_ticket',
           return_value=('productname/fixes/PROJECTNAME-1_fix', 'fix', 'PROJECTNAME-1'))
           return_value=('productname/fixes/PROJECTNAME-1_fix', 'fix', 'PROJECTNAME-1'))
    async def test_local_differs_user_declines_keeps_local(self, mock_discover, mock_tool,
                                                      mock_cache, mock_write):
        """Local plan differs from MR, user declines -> plan NOT overwritten.

        When the user answers no to the prompt, the function returns 0 without
        writing the MR version to disk.

        Function under test: cmd_planget()
        """
        local_plan = '# Local Plan\n\n- [x] Old step\n' + 'a' * 100
        mr_plan = '# MR Plan\n\n- [ ] New step\n' + 'b' * 100
        description = _mr_body_with_plan(mr_plan)
        mr_json = json.dumps([{'iid': 7, 'description': description}])

        with tempfile.TemporaryDirectory() as tmp:
            plan_file = os.path.join(tmp, 'PLAN.md')
            with open(plan_file, 'w') as f:
                f.write(local_plan)
            with patch('git_hooks_impl.entry_points.extract_plan.run_async', new_callable=AsyncMock,
                       return_value=(0, mr_json, '')), \
                 patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.entry_points.extract_plan._print_diff'), \
                 patch('git_hooks_impl.entry_points.extract_plan.prompt_yn', return_value=False), \
                 patch('git_hooks_impl.entry_points.extract_plan.sys.stdin') as mock_stdin:
                mock_stdin.isatty.return_value = True
                result = await cmd_planget()

        self.assertEqual(result, 0)
        mock_write.assert_not_called()

    @patch('git_hooks_impl.entry_points.extract_plan._write_plan')
    @patch('git_hooks_impl.entry_points.extract_plan._save_cache')
    @patch('git_hooks_impl.entry_points.extract_plan.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.extract_plan._discover_branch_and_ticket',
           return_value=('productname/fixes/PROJECTNAME-1_fix', 'fix', 'PROJECTNAME-1'))
           return_value=('productname/fixes/PROJECTNAME-1_fix', 'fix', 'PROJECTNAME-1'))
    async def test_local_differs_user_accepts_overwrites(self, mock_discover, mock_tool,
                                                    mock_cache, mock_write):
        """Local plan differs from MR, user accepts -> plan overwritten.

        When the user answers yes to the prompt, the MR plan is written.

        Function under test: cmd_planget()
        """
        local_plan = '# Local Plan\n\n- [x] Old step\n' + 'a' * 100
        mr_plan = '# MR Plan\n\n- [ ] New step\n' + 'b' * 100
        description = _mr_body_with_plan(mr_plan)
        mr_json = json.dumps([{'iid': 7, 'description': description}])

        with tempfile.TemporaryDirectory() as tmp:
            plan_file = os.path.join(tmp, 'PLAN.md')
            with open(plan_file, 'w') as f:
                f.write(local_plan)
            with patch('git_hooks_impl.entry_points.extract_plan.run_async', new_callable=AsyncMock,
                       return_value=(0, mr_json, '')), \
                 patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.entry_points.extract_plan._print_diff'), \
                 patch('git_hooks_impl.entry_points.extract_plan.prompt_yn', return_value=True), \
                 patch('git_hooks_impl.entry_points.extract_plan.sys.stdin') as mock_stdin:
                mock_stdin.isatty.return_value = True
                result = await cmd_planget()

        self.assertEqual(result, 0)
        mock_write.assert_called_once()

    @patch('git_hooks_impl.entry_points.extract_plan._write_plan')
    @patch('git_hooks_impl.entry_points.extract_plan._save_cache')
    @patch('git_hooks_impl.entry_points.extract_plan.find_tool', return_value='/usr/bin/glab')
    @patch('git_hooks_impl.entry_points.extract_plan._discover_branch_and_ticket',
           return_value=('productname/fixes/PROJECTNAME-1_fix', 'fix', 'PROJECTNAME-1'))
           return_value=('productname/fixes/PROJECTNAME-1_fix', 'fix', 'PROJECTNAME-1'))
    async def test_non_interactive_with_local_plan_overwrites_without_prompt(
            self, mock_discover, mock_tool, mock_cache, mock_write):
        """Non-interactive shell (isatty=False) with differing local plan -> overwrites.

        In CI or pipe contexts, no prompt is shown; the MR version always wins.

        Function under test: cmd_planget()
        """
        local_plan = '# Local Plan\n\n- [x] Old step\n' + 'a' * 100
        mr_plan = '# MR Plan\n\n- [ ] New step\n' + 'b' * 100
        description = _mr_body_with_plan(mr_plan)
        mr_json = json.dumps([{'iid': 7, 'description': description}])

        with tempfile.TemporaryDirectory() as tmp:
            plan_file = os.path.join(tmp, 'PLAN.md')
            with open(plan_file, 'w') as f:
                f.write(local_plan)
            with patch('git_hooks_impl.entry_points.extract_plan.run_async', new_callable=AsyncMock,
                       return_value=(0, mr_json, '')), \
                 patch('git_hooks_impl.entry_points.extract_plan.PLAN_FILE', plan_file), \
                 patch('git_hooks_impl.entry_points.extract_plan._print_diff'), \
                 patch('git_hooks_impl.entry_points.extract_plan.prompt_yn') as mock_prompt, \
                 patch('git_hooks_impl.entry_points.extract_plan.sys.stdin') as mock_stdin:
                mock_stdin.isatty.return_value = False
                result = await cmd_planget()

        self.assertEqual(result, 0)
        mock_prompt.assert_not_called()
        mock_write.assert_called_once()

    @patch('git_hooks_impl.entry_points.extract_plan._discover_branch_and_ticket',
           side_effect=RuntimeError('unexpected failure'))
    async def test_exception_returns_0_never_blocks(self, mock_discover):
        """Unexpected exception in cmd_planget -> returns 0, never raises.

        The outer try/except ensures git hooks are never blocked by errors.

        Function under test: cmd_planget()
        """
        result = await cmd_planget()
        self.assertEqual(result, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
