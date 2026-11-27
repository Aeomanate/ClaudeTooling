#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Shared hook dispatcher — delegates to cli.py main().

Direct invocation:  python .git-hooks/hooks/entry_points/ai_tooling_hooks.py <command> [args]
"""

if __name__ == '__main__':
    import os
    import sys
    # entry_points/ -> hooks/ -> .git-hooks/
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))
    from git_hooks_impl.entry_points.cli import main
    sys.exit(main())
