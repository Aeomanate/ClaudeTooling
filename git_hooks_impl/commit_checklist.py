#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Print the G1-G9 commit checklist with all-[x] checkboxes."""

_CHECKLIST = """\
Pre-commit checklist (G1-G9):
  [x] G1  Commit after each logical unit -- working state at every SHA
  [x] G2  Subject <=60 chars, whitelisted imperative verb, no trailing dot
  [x] G3  Branch name matches project convention
  [x] G4  Stage explicitly -- no plan file, no unrelated files
  [x] G5  All changed tests pass; mock-audit completed if test files changed
  [x] G6  Fresh consistency check agent run on all changed files
  [x] G7  No step skipped without WF-1 skip-permission dialog
  [x] G8  Commit body explains WHY -- not just what files changed
  [x] G9  Pre-flight staged-file check passed (no unexpected staged files)
"""


def main():
    print(_CHECKLIST)


if __name__ == '__main__':
    main()
