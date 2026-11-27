"""Shared symlink helpers used by setup/link.py and setup/skills.py.

Files are deployed as symlinks (os.symlink) — symlinks only, never hard-links.
On Windows this requires Developer Mode or Administrator privileges; mr setup
fails hard if the privilege is absent.
"""

import os

# Skill subtrees ai_tooling fully owns inside ~/.claude/skills/. Files inside
# these subtrees that have no source counterpart are stale ai_tooling artifacts,
# never user-created content. The recursive prune logic uses this set to skip
# the user-file guard inside these namespaces and to surface file-level orphans
# that the subtree-level walk misses.
AI_TOOLING_MANAGED_SKILLS = ('orchestrator',)


class PruneStatError(Exception):
    """A stat() failure during a prune pass leaves the inode set incomplete.

    Raised instead of silently swallowing OSError at sites where missing
    information could misclassify a live file as an orphan. The caller must
    catch this, report it, and skip that run's cleanup rather than proceed.
    """


def _is_linked(source_file, target_file):
    """Return True if target_file is a symlink resolving to source_file."""
    try:
        return (
            os.path.islink(target_file)
            and os.path.realpath(target_file) == os.path.realpath(source_file)
        )
    except OSError:
        return False


def _resolves_to_source(source_file, target_file):
    """Return True if target_file's real path is source_file's real path.

    Unlike _is_linked, this does not require target_file itself to be a
    symlink — it also recognizes a file reached through a symlinked
    ancestor directory (e.g. a whole skill symlinked as one unit), which
    _is_linked reports as not-linked since the leaf isn't a symlink.
    """
    try:
        return (
            os.path.exists(target_file)
            and os.path.realpath(target_file) == os.path.realpath(source_file)
        )
    except OSError:
        return False


def _link_unconditional(source_file, target_file):
    """Symlink unconditionally — replace if not linked or diverged. Returns True if linked.

    Existing hard-links (st_nlink > 1, not a symlink) are treated as
    diverged and replaced with a symlink (auto-migration path).
    """
    if _is_linked(source_file, target_file):
        return False
    if os.path.exists(target_file) or os.path.islink(target_file):
        os.remove(target_file)
    os.symlink(source_file, target_file)
    return True


def _link_directory_recursive(source_dir, target_dir):
    """Walk source_dir, symlink every file into target_dir. Returns (linked, up_to_date)."""
    linked_count = 0
    up_to_date_count = 0
    for dirpath, dirnames, filenames in os.walk(source_dir):
        rel_dir = os.path.relpath(dirpath, source_dir)
        target_subdir = os.path.join(target_dir, rel_dir) if rel_dir != '.' else target_dir

        # target_subdir may already be a directory-level symlink resolving
        # into this same source subtree (e.g. a whole skill symlinked as one
        # unit). Walking into it would compute per-file target paths that
        # physically resolve back into source_dir: os.remove() would delete
        # the real source file and os.symlink() would recreate it pointing
        # at itself. Skip the whole subtree — it's already linked.
        if (os.path.islink(target_subdir)
                and os.path.realpath(target_subdir) == os.path.realpath(dirpath)):
            dirnames[:] = []
            continue

        os.makedirs(target_subdir, exist_ok=True)
        for filename in filenames:
            source_file = os.path.join(dirpath, filename)
            target_file = os.path.join(target_subdir, filename)
            if _link_unconditional(source_file, target_file):
                linked_count += 1
            else:
                up_to_date_count += 1
    return linked_count, up_to_date_count


def _link_flat_directory(source_dir, target_dir):
    """Symlink files in source_dir (non-recursive) into target_dir. Returns (linked, up_to_date)."""
    os.makedirs(target_dir, exist_ok=True)
    linked_count = 0
    up_to_date_count = 0
    for filename in os.listdir(source_dir):
        source_file = os.path.join(source_dir, filename)
        if not os.path.isfile(source_file):
            continue
        target_file = os.path.join(target_dir, filename)
        if _link_unconditional(source_file, target_file):
            linked_count += 1
        else:
            up_to_date_count += 1
    return linked_count, up_to_date_count


def _prune_flat_directory(source_dir, target_dir, prefix):
    """Collect orphaned files in target_dir — prefix-matched but inode-unverified.

    A file in target_dir is an orphan when:
    - Its name starts with prefix (ai_tooling-owned namespace), AND
    - Its inode does not appear in any file currently in source_dir
      (inode comparison across the whole source set, not just same filename).

    Returns list of orphan absolute paths. Does not delete anything.
    """
    if not os.path.isdir(source_dir) or not os.path.isdir(target_dir):
        return []

    # Build set of (inode, device) for every file in source_dir.
    source_inodes = set()
    for filename in os.listdir(source_dir):
        src = os.path.join(source_dir, filename)
        if os.path.isfile(src):
            try:
                st = os.stat(src)
                source_inodes.add((st.st_ino, st.st_dev))
            except OSError as error:
                raise PruneStatError(f'cannot stat source file {src!r}: {error}') from error

    orphans = []
    for filename in os.listdir(target_dir):
        if not filename.startswith(prefix):
            continue
        target_file = os.path.join(target_dir, filename)
        if not os.path.isfile(target_file):
            continue
        try:
            st = os.stat(target_file)
            if (st.st_ino, st.st_dev) not in source_inodes:
                orphans.append(target_file)
        # Fails safe: skips flagging this one target file as an orphan — it survives, nothing deleted.
        except OSError:
            pass

    return orphans


def _prune_recursive_directory(source_dir, target_dir,
                               managed_skills=AI_TOOLING_MANAGED_SKILLS):
    """Collect orphaned subdirectories in target_dir.

    A subdirectory in target_dir is an orphan when:
    - The corresponding relative path does not exist in source_dir, AND
    - One of:
      a) The subtree root is INSIDE an ai_tooling-managed skill namespace
         (first path segment in `managed_skills`). Every file under a managed
         namespace is ai_tooling-managed (stale or live); user content does not
         live there, so the user-file guard is skipped.
      b) The subtree root is OUTSIDE managed namespaces AND every file inside
         the target subtree has an inode that matches a file in source_dir
         (no user-owned files inside — safe to delete whole tree).

    Walk is top-down; once a directory is flagged as an orphan, its children are
    not walked further (they're part of the same subtree to delete).

    Returns list of orphan subtree-root absolute paths. Does not delete anything.
    """
    if not os.path.isdir(source_dir) or not os.path.isdir(target_dir):
        return []

    # Build set of (inode, device) for every file in source_dir (recursive).
    # Used only outside managed namespaces — managed namespaces skip the guard.
    source_inodes = set()
    for dirpath, _dirnames, filenames in os.walk(source_dir):
        for filename in filenames:
            src = os.path.join(dirpath, filename)
            try:
                st = os.stat(src)
                source_inodes.add((st.st_ino, st.st_dev))
            # Fails safe: a missing inode here can only push has_user_file toward True downstream, which preserves the subtree instead of deleting it.
            except OSError:
                pass

    orphans = []
    flagged_roots = set()

    for dirpath, dirnames, _filenames in os.walk(target_dir, topdown=True):
        # Skip subtrees already flagged as orphan roots.
        if any(dirpath == r or dirpath.startswith(r + os.sep) for r in flagged_roots):
            dirnames[:] = []
            continue

        rel = os.path.relpath(dirpath, target_dir)
        if rel == '.':
            continue

        source_counterpart = os.path.join(source_dir, rel)
        if os.path.isdir(source_counterpart):
            continue

        # Candidate orphan. Check the managed-namespace fast-path first.
        first_segment = rel.split(os.sep)[0]
        in_managed_namespace = first_segment in managed_skills

        if in_managed_namespace:
            # Managed namespace: every file is ai_tooling-owned. Prune safely.
            orphans.append(dirpath)
            flagged_roots.add(dirpath)
            dirnames[:] = []
            continue

        # Non-managed namespace: enforce user-file guard.
        has_user_file = False
        for sub_dirpath, _sub_dirs, sub_files in os.walk(dirpath):
            for fname in sub_files:
                fpath = os.path.join(sub_dirpath, fname)
                try:
                    st = os.stat(fpath)
                    if (st.st_ino, st.st_dev) not in source_inodes:
                        has_user_file = True
                        break
                except OSError as error:
                    raise PruneStatError(f'cannot stat target file {fpath!r}: {error}') from error
            if has_user_file:
                break
        if not has_user_file:
            orphans.append(dirpath)
            flagged_roots.add(dirpath)
            dirnames[:] = []  # don't recurse into flagged subtree

    return orphans


def _prune_managed_skill_orphan_files(source_skills_dir, target_skills_dir,
                                      managed_skills=AI_TOOLING_MANAGED_SKILLS):
    """Collect orphan FILES inside ai_tooling-managed skill subtrees.

    Companion to `_prune_recursive_directory`, which only flags orphan
    SUBDIRECTORIES. This function catches orphan FILES living inside a
    directory that DOES have a source counterpart — the source-present-dir
    case the recursive walk skips.

    For each managed skill name, walk every file under
    `target_skills_dir/<name>/`. A file is an orphan when:
    - Its relative path under `<name>/` has NO source counterpart under
      `source_skills_dir/<name>/`, AND
    - Its (inode, device) is NOT in the source-side inode set for that skill
      subtree (defensive — catches a stale regular file that happens to share
      a name with a deleted source file but a different inode).

    Returns list of orphan absolute file paths. Does not delete anything.
    """
    orphans = []
    for skill_name in managed_skills:
        source_skill = os.path.join(source_skills_dir, skill_name)
        target_skill = os.path.join(target_skills_dir, skill_name)
        if not os.path.isdir(source_skill) or not os.path.isdir(target_skill):
            continue

        # Build source inode set scoped to THIS skill subtree.
        source_inodes = set()
        for dirpath, _dirnames, filenames in os.walk(source_skill):
            for filename in filenames:
                src = os.path.join(dirpath, filename)
                try:
                    st = os.stat(src)
                    source_inodes.add((st.st_ino, st.st_dev))
                except OSError as error:
                    raise PruneStatError(f'cannot stat source file {src!r}: {error}') from error

        # Walk target subtree, flag orphan files (source-counterpart-missing).
        for dirpath, _dirnames, filenames in os.walk(target_skill):
            rel_dir = os.path.relpath(dirpath, target_skill)
            for filename in filenames:
                target_file = os.path.join(dirpath, filename)
                rel_file = (os.path.join(rel_dir, filename)
                            if rel_dir != '.' else filename)
                source_counterpart = os.path.join(source_skill, rel_file)
                if os.path.exists(source_counterpart):
                    continue
                try:
                    st = os.stat(target_file)
                    if (st.st_ino, st.st_dev) not in source_inodes:
                        orphans.append(target_file)
                # Fails safe: skips flagging this one target file as an orphan — it survives, nothing deleted.
                except OSError:
                    pass

    return orphans
