#!/usr/bin/env python
"""install_profiles.py - write ~/.bashrc managed block with ai_tooling env vars.

Idempotent: re-running replaces the existing block in place (no duplication).
The managed block contains env vars and the `mr` shell function wrapper.
"""

import os
import sys
from pathlib import Path

_BLOCK_BEGIN = '# >>> ai-tooling (managed) >>>'
_BLOCK_END   = '# <<< ai-tooling (managed) <<<'


def _to_mingw_path(win_path: str) -> str:
    """Convert C:/foo/bar -> /c/foo/bar for bash PATH compatibility on MINGW.

    Bash's PATH separator is ':', which collides with the drive-letter colon in
    C:/... paths. PATH entries must use MINGW-style /c/... so the colon doesn't
    split the entry into two broken pieces.
    """
    if len(win_path) >= 2 and win_path[1] == ':':
        return '/' + win_path[0].lower() + win_path[2:]
    return win_path


def _bashrc_path() -> Path:
    return Path(os.path.expanduser('~/.bashrc'))


def _read_lines(path: Path) -> list:
    if not path.exists():
        return []
    return path.read_text(encoding='utf-8').splitlines(keepends=True)


def _strip_existing_block(lines: list) -> list:
    """Remove the existing managed block from `lines` (in place)."""
    out = []
    inside = False
    for line in lines:
        s = line.rstrip('\n')
        if s == _BLOCK_BEGIN:
            inside = True
            continue
        if s == _BLOCK_END:
            inside = False
            continue
        if inside:
            continue
        out.append(line)
    return out


def _locate_managed_block(lines: list) -> tuple | None:
    """Return (begin_idx, end_idx) of the interior of the managed block.

    begin_idx: index of the line after _BLOCK_BEGIN sentinel.
    end_idx:   index of the _BLOCK_END sentinel line (exclusive interior end).
    Returns None if the block sentinels are not both found.
    """
    begin_idx = None
    for i, line in enumerate(lines):
        s = line.rstrip('\n')
        if s == _BLOCK_BEGIN:
            begin_idx = i + 1
        elif s == _BLOCK_END and begin_idx is not None:
            return (begin_idx, i)
    return None


def toggle_managed_flag(name: str, enabled: bool) -> str | None:
    """Flip a true/false export inside the bashrc managed block.

    Returns None on success, or an error string:
      'not_found'      - managed block absent (run mr setup first)
      'already'        - the export already holds the target value
      'line_missing'   - block exists but the export line is not in it
    """
    path = _bashrc_path()
    lines = _read_lines(path)
    span = _locate_managed_block(lines)
    if span is None:
        return 'not_found'

    target = f'export {name}={"true" if enabled else "false"}'
    begin_idx, end_idx = span
    for i in range(begin_idx, end_idx):
        s = lines[i].rstrip('\n')
        if s.startswith(f'export {name}='):
            if s == target:
                return 'already'
            lines[i] = target + '\n'
            path.write_text(''.join(lines), encoding='utf-8')
            return None

    return 'line_missing'


def toggle_tooling_enabled(enabled: bool) -> str | None:
    """Flip AI_TOOLING_ENABLED in the bashrc managed block."""
    return toggle_managed_flag('AI_TOOLING_ENABLED', enabled)


def toggle_hardening(enabled: bool) -> str | None:
    """Flip IS_HARDENING in the bashrc managed block.

    Set means the orchestrator runs the full stack; unset or false means POC,
    the default. A new shell picks the change up; the `mr` shell function
    exports it into the current one as well.
    """
    return toggle_managed_flag('IS_HARDENING', enabled)


def append_to_bashrc(lines_to_add: list) -> None:
    """Append a list of lines to the user's ~/.bashrc.

    Idempotent: ensures only one managed block exists.
    """
    path = _bashrc_path()
    existing = _read_lines(path)
    stripped = _strip_existing_block(existing)

    # Ensure trailing newline before our block
    if stripped and not stripped[-1].endswith('\n'):
        stripped[-1] += '\n'

    block = [_BLOCK_BEGIN + '\n']
    for line in lines_to_add:
        block.append(line if line.endswith('\n') else line + '\n')
    block.append(_BLOCK_END + '\n')

    path.write_text(''.join(stripped) + ''.join(block), encoding='utf-8')


def _extract_existing_value(existing_lines: list, span: tuple, name: str) -> str:
    """Search the managed-block interior for an existing export line.

    Returns the current value of `name` if found, or empty string if absent.
    """
    if span is None:
        return ''
    begin_idx, end_idx = span
    prefix = f'export {name}="'
    for line in existing_lines[begin_idx:end_idx]:
        stripped = line.rstrip('\n')
        if stripped.startswith(prefix) and stripped.endswith('"'):
            return stripped[len(prefix):-1]
    return ''


def write_managed_block(ai_tooling_src: str, tokens: dict) -> None:
    """Write the canonical ai_tooling managed block to ~/.bashrc.

    Args:
        ai_tooling_src: absolute path to $AI_TOOLING_SRC.
        tokens: dict of {env_var_name: value}; expected keys
                JIRA_API_TOKEN, GLAB_TOKEN, ANTHROPIC_AUTH_TOKEN.
                Keys absent from tokens are preserved from the existing block.
    """
    path = _bashrc_path()
    existing_lines = _read_lines(path)
    existing_span = _locate_managed_block(existing_lines)

    mingw_src = _to_mingw_path(ai_tooling_src)

    # Preserve the developer's current mode across a block rewrite; a setup
    # run is not a reason to drop them back into the default.
    hardening = 'false'
    if existing_span is not None:
        begin_idx, end_idx = existing_span
        for line in existing_lines[begin_idx:end_idx]:
            if line.strip().startswith('export IS_HARDENING='):
                hardening = line.strip().split('=', 1)[1].strip('"\'') or 'false'
                break

    block_lines = [
        f'export AI_TOOLING_SRC="{ai_tooling_src}"',
        f'export PATH="{mingw_src}:$PATH"',
        'export AI_TOOLING_ENABLED=true',
        f'export IS_HARDENING={hardening}',
        'export ANTHROPIC_BASE_URL="https://reponameq-service.companyname.io/anthropic"',
        'export CLAUDE_CODE_SKIP_BEDROCK_AUTH=1',
        'export CLAUDE_CODE_MAX_OUTPUT_TOKENS=64000',
        'export CLAUDE_SKILL_DIR="$HOME/.claude/skills/orchestrator"',
    ]
    for name in ('JIRA_API_TOKEN', 'GLAB_TOKEN', 'ANTHROPIC_AUTH_TOKEN'):
        value = (tokens.get(name)
                 or _extract_existing_value(existing_lines, existing_span, name)
                 or '')
        block_lines.append(f'export {name}="{value}"')

    # Tooling on/off - shell function so mr on/off also flips the current shell's env.
    # Calling "$AI_TOOLING_SRC/mr" (script path) avoids function recursion.
    block_lines += [
        'mr() {',
        '    case "$1" in',
        '        on)        export AI_TOOLING_ENABLED=true ;;',
        '        off)       export AI_TOOLING_ENABLED=false ;;',
        '        hardening) [ "$2" = on ] && export IS_HARDENING=true',
        '                   [ "$2" = off ] && export IS_HARDENING=false ;;',
        '    esac',
        '    "$AI_TOOLING_SRC/mr" "$@"',
        '}',
    ]

    append_to_bashrc(block_lines)


def cmd_install_profiles(ai_tooling_src: str, tokens: dict) -> int:
    """CLI entry-point - write the managed block, report status."""
    write_managed_block(ai_tooling_src, tokens)
    print(f'Wrote ~/.bashrc managed block ({len(tokens)} tokens)')
    return 0


if __name__ == '__main__':
    # CLI usage: setup/install_profiles.py <ai_tooling_src>
    # (tokens default to empty; tools.py drives this with real values)
    src = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('AI_TOOLING_SRC', '')
    sys.exit(cmd_install_profiles(src, {}))
