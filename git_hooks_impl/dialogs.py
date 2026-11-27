#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Shared tkinter dialogs for MR automation hooks.

- plan_check_dialog()  — pre-push "Is BRANCH_PLAN.md up to date?" with timeout
- conflict_dialog()    — conflict resolution (no timeout)
"""

import difflib

try:
    import winreg
except ImportError:
    winreg = None

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    tk = None
    ttk = None

# Dark-mode palette (Windows 10/11 dark theme approximation)
_DARK = {
    'bg':      '#1e1e1e',
    'fg':      '#e0e0e0',
    'btn_bg':  '#333333',
    'btn_fg':  '#e0e0e0',
    'select':  '#264f78',
    'gray':    '#888888',
}


def _is_dark_mode():
    """Check Windows dark mode via registry. Returns False on non-Windows."""
    if winreg is None:
        return False
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r'SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize')
        val, _ = winreg.QueryValueEx(key, 'AppsUseLightTheme')
        winreg.CloseKey(key)
        return val == 0
    except Exception:
        return False


def _create_modal(title, *, resizable=True, minsize=None):
    """Create a themed, topmost tkinter window.

    Returns (root, tk, ttk).  Caller adds widgets, then calls
    _show_modal(root) to center + run the event loop.
    Detects Windows dark mode and applies dark colors automatically.

    Raises ImportError if tkinter is unavailable.
    """
    if tk is None:
        raise ImportError('tkinter is not available')

    root = tk.Tk()
    root.title(title)
    root.attributes('-topmost', True)
    if not resizable:
        root.resizable(False, False)
    if minsize:
        root.minsize(*minsize)

    style = ttk.Style(root)
    dark = _is_dark_mode()

    if dark:
        # 'clam' is the only built-in theme that respects custom colors
        # on buttons, scrollbars, etc.  vista/winnative ignore them.
        style.theme_use('clam')
        d = _DARK
        root.configure(bg=d['bg'])
        style.configure('.', background=d['bg'], foreground=d['fg'],
                        troughcolor=d['bg'], bordercolor=d['btn_bg'],
                        darkcolor=d['btn_bg'], lightcolor=d['btn_bg'])
        style.configure('TLabel', background=d['bg'], foreground=d['fg'])
        style.configure('TFrame', background=d['bg'])
        style.configure('TButton', background=d['btn_bg'],
                        foreground=d['btn_fg'], padding=(8, 4))
        style.map('TButton',
                  background=[('active', d['select']),
                              ('pressed', d['select'])],
                  foreground=[('active', d['btn_fg'])])
        style.configure('TScrollbar', background=d['btn_bg'],
                        troughcolor='#2a2a2a', arrowcolor=d['fg'])
        style.map('TScrollbar',
                  background=[('active', d['select'])])
    else:
        # Light mode: native Windows theme
        for theme in ('vista', 'winnative', 'clam', 'default'):
            if theme in style.theme_names():
                style.theme_use(theme)
                break

    return root, tk, ttk


def _show_modal(root):
    """Center and run the event loop for a modal created by _create_modal."""
    # Force the window to render so wm_frame() and winfo_width() work
    root.update_idletasks()

    # Center on screen
    x = (root.winfo_screenwidth() - root.winfo_width()) // 2
    y = (root.winfo_screenheight() - root.winfo_height()) // 2
    root.geometry(f'+{x}+{y}')

    root.mainloop()


def plan_check_dialog(timeout=5):
    """Show a GUI dialog asking if BRANCH_PLAN.md is up to date.

    Auto-continues after *timeout* seconds.  Returns True to proceed,
    False to abort the push.  Falls back to True (continue) if tkinter
    is unavailable or the dialog errors out.
    """
    try:
        root, tk, ttk = _create_modal('MR Sync — pre-push', resizable=False)
    except ImportError:
        return True

    result = [True]
    remaining = [timeout]

    try:
        root.protocol('WM_DELETE_WINDOW', lambda: on_continue())

        ttk.Label(root, text='Is .ai/BRANCH_PLAN.md up to date?',
                  font=('Segoe UI', 12)).pack(pady=(12, 4))

        timer_lbl = ttk.Label(root, text=f'Continuing in {timeout}s...',
                              font=('Segoe UI', 9), foreground='gray')
        timer_lbl.pack()

        def on_continue():
            result[0] = True
            root.destroy()

        def on_abort():
            result[0] = False
            root.destroy()

        def countdown():
            remaining[0] -= 1
            if remaining[0] <= 0:
                on_continue()
            else:
                timer_lbl.config(text=f'Continuing in {remaining[0]}s...')
                root.after(1000, countdown)

        btn = ttk.Frame(root)
        btn.pack(pady=(8, 12))
        ttk.Button(btn, text='  Continue Push (Enter)  ',
                   command=on_continue).pack(side='left', padx=6)
        abort_btn = ttk.Button(btn, text='  Abort — Update BRANCH_PLAN.md (Esc)  ',
                               command=on_abort)
        abort_btn.pack(side='left', padx=6)

        root.bind('<Return>', lambda e: on_continue())
        root.bind('<Escape>', lambda e: on_abort())

        root.after(1000, countdown)
        _show_modal(root)
    except Exception:
        return True

    return result[0]




def _build_diff_lines(local_content, remote_content):
    """Compute +/- diff lines with line numbers between local and remote.

    Returns list of (tag, text) tuples where tag is 'add' or 'del'.
    '-L42: old line' for removed, '+R42: new line' for added.
    """
    local_lines = local_content.splitlines()
    remote_lines = remote_content.splitlines()
    sm = difflib.SequenceMatcher(None, local_lines, remote_lines)
    lines = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        if tag in ('replace', 'delete'):
            for idx, line in enumerate(local_lines[i1:i2], start=i1 + 1):
                lines.append(('del', f'-L{idx}: {line}'))
        if tag in ('replace', 'insert'):
            for idx, line in enumerate(remote_lines[j1:j2], start=j1 + 1):
                lines.append(('add', f'+R{idx}: {line}'))
    return lines


def _build_conflict_lines(base_content, local_content, remote_content):
    """3-way diff: return only lines where BOTH sides changed the same region.

    Compares base→local and base→remote.  A region is a "true conflict" when
    it was modified on both sides (replace/delete/insert overlapping ranges).
    Returns list of (tag, text) tuples, same format as _build_diff_lines.
    """
    base = base_content.splitlines()
    local = local_content.splitlines()
    remote = remote_content.splitlines()

    # Build sets of base line ranges changed by each side
    def _changed_ranges(base_lines, other_lines):
        """Return set of base line indices that were changed."""
        sm = difflib.SequenceMatcher(None, base_lines, other_lines)
        changed = set()
        for tag, i1, i2, _j1, _j2 in sm.get_opcodes():
            if tag != 'equal':
                changed.update(range(i1, max(i2, i1 + 1)))
        return changed

    local_changed = _changed_ranges(base, local)
    remote_changed = _changed_ranges(base, remote)
    conflict_base_lines = local_changed & remote_changed

    if not conflict_base_lines:
        return []

    # Now build diff lines but only for regions touching conflict_base_lines.
    # Use the local-vs-remote diff, filtered to overlapping base regions.
    sm_lr = difflib.SequenceMatcher(None, local, remote)
    # Map local line indices back to base to check if they're in conflict zone.
    sm_bl = difflib.SequenceMatcher(None, base, local)
    base_to_local = {}  # base_idx -> local_idx
    for tag, i1, i2, j1, _j2 in sm_bl.get_opcodes():
        if tag == 'equal':
            for off in range(i2 - i1):
                base_to_local[i1 + off] = j1 + off
    # local lines that correspond to conflicting base lines
    conflict_local = set()
    for bi in conflict_base_lines:
        if bi in base_to_local:
            conflict_local.add(base_to_local[bi])
        else:
            # base line was deleted/replaced in local — include surrounding
            # local lines from the replace opcode
            for tag, i1, i2, j1, j2 in sm_bl.get_opcodes():
                if tag != 'equal' and i1 <= bi < i2:
                    conflict_local.update(range(j1, j2))

    lines = []
    for tag, i1, i2, j1, j2 in sm_lr.get_opcodes():
        if tag == 'equal':
            continue
        # Check if this hunk overlaps with conflict local lines
        local_range = set(range(i1, max(i2, i1 + 1)))
        if not local_range & conflict_local:
            continue
        if tag in ('replace', 'delete'):
            for idx, line in enumerate(local[i1:i2], start=i1 + 1):
                lines.append(('del', f'-L{idx}: {line}'))
        if tag in ('replace', 'insert'):
            for idx, line in enumerate(remote[j1:j2], start=j1 + 1):
                lines.append(('add', f'+R{idx}: {line}'))
    return lines


def conflict_dialog(local_content, remote_content, base_content=None):
    """Show a GUI dialog for BRANCH_PLAN.md conflict resolution.

    If base_content is provided, shows only true 3-way conflicts (both sides
    changed the same region).  Non-overlapping changes are auto-merged before
    this dialog is reached.

    Returns one of: 'remote', 'local', 'merge', 'manual', 'abort'.

    - tkinter unavailable      -> 'local' (safe default).
    - Window closed / Escape   -> 'abort' (safe default).

    No isatty() gate — during pre-push git pipes stdin so isatty() is
    False even though a display is available.  The tkinter try/except
    handles truly headless environments (CI).
    """
    try:
        root, tk, ttk = _create_modal('MR Sync \u2014 plan conflict',
                                      minsize=(600, 300))
    except ImportError:
        return 'local'

    result = ['abort']

    try:
        root.protocol('WM_DELETE_WINDOW', lambda: _close())

        ttk.Label(root, text='BRANCH_PLAN.md was edited on the MR since last push.',
                  font=('Segoe UI', 11)).pack(pady=(12, 4))

        # Diff view — scrollable monospace text with colored +/- lines
        diff_frame = ttk.Frame(root)
        diff_frame.pack(fill='both', expand=True, padx=12, pady=(4, 8))

        dark = _is_dark_mode()
        text_kw = {'wrap': 'none', 'font': ('Consolas', 9), 'state': 'disabled'}
        if dark:
            text_kw.update(bg=_DARK['bg'], fg=_DARK['fg'],
                           insertbackground=_DARK['fg'])
        text = tk.Text(diff_frame, **text_kw)
        scroll_y = ttk.Scrollbar(diff_frame, orient='vertical',
                                 command=text.yview)
        scroll_x = ttk.Scrollbar(diff_frame, orient='horizontal',
                                 command=text.xview)
        text.configure(yscrollcommand=scroll_y.set,
                       xscrollcommand=scroll_x.set)

        text.grid(row=0, column=0, sticky='nsew')
        scroll_y.grid(row=0, column=1, sticky='ns')
        scroll_x.grid(row=1, column=0, sticky='ew')
        diff_frame.grid_rowconfigure(0, weight=1)
        diff_frame.grid_columnconfigure(0, weight=1)

        # Brighter diff colors on dark background for readability
        del_color = '#ff6b6b' if dark else '#cc0000'
        add_color = '#66cc66' if dark else '#008800'
        text.tag_configure('del', foreground=del_color)
        text.tag_configure('add', foreground=add_color)

        # Show only true conflicts when base available, all diffs otherwise
        if base_content is not None:
            diff_lines = _build_conflict_lines(
                base_content, local_content, remote_content)
        else:
            diff_lines = _build_diff_lines(local_content, remote_content)

        text.configure(state='normal')
        if diff_lines:
            for tag, line in diff_lines:
                text.insert('end', line + '\n', tag)
        else:
            text.insert('end', '(no visible diff)\n')
        text.configure(state='disabled')

        def _close():
            root.destroy()

        def _choose(action):
            result[0] = action
            root.destroy()

        btn_frame = ttk.Frame(root)
        btn_frame.pack(pady=(4, 12))
        for label, action in [('Keep Remote',      'remote'),
                               ('Keep Local',       'local'),
                               ('Merge via Claude', 'merge'),
                               ('Edited Manually',  'manual'),
                               ('Abort',            'abort')]:
            ttk.Button(btn_frame, text=f'  {label}  ',
                       command=lambda a=action: _choose(a)).pack(side='left',
                                                                 padx=4)

        # Escape = abort (safe default), no Enter binding
        root.bind('<Escape>', lambda e: _close())

        _show_modal(root)
    except Exception:
        return 'local'

    return result[0]


