#!/usr/bin/env python3
"""Fail-closed capability boundary for the Moderate local implementer.

The task card is the complete authority surface. Model file operations are
limited to its ``allowed_paths``. Commands are operator-controlled and the
runner may execute only argv that exactly match one parsed
``verification_commands[].argv`` entry. Rejections raise the runner's
``BoundaryViolation`` and therefore terminate the attempt.
"""

import os
class BoundaryViolation(RuntimeError):
    pass


def _inside(candidate, root):
    try:
        return os.path.commonpath([candidate, root]) == root
    except ValueError:
        return False


class LocalAgentBoundary:
    def __init__(self, worktree_root, allowed_paths, allowed_commands):
        self._worktree_root = os.path.realpath(worktree_root)
        self._allowed_paths = tuple(
            self._build_allowed_path(path) for path in allowed_paths
        )
        self._allowed_commands = frozenset(tuple(argv) for argv in allowed_commands)

    def _build_allowed_path(self, path):
        if not isinstance(path, str) or not path:
            raise BoundaryViolation(f"invalid allowed path: {path!r}")
        if os.path.isabs(path):
            raise BoundaryViolation(f"absolute allowed path rejected: {path!r}")

        normalized = os.path.normpath(path)
        if normalized in (".", "..") or normalized.startswith(".." + os.sep):
            raise BoundaryViolation(f"allowed path escapes worktree: {path!r}")

        lexical = os.path.abspath(os.path.join(self._worktree_root, normalized))
        resolved = os.path.realpath(lexical)
        if not _inside(lexical, self._worktree_root) or not _inside(
            resolved, self._worktree_root
        ):
            raise BoundaryViolation(f"allowed path escapes worktree: {path!r}")

        return {
            "path": normalized,
            "lexical": lexical,
            "resolved": resolved,
            "directory": os.path.isdir(resolved),
        }

    def check_path(self, path):
        if not isinstance(path, str) or not path:
            raise BoundaryViolation(f"invalid path rejected: {path!r}")
        if os.path.isabs(path):
            raise BoundaryViolation(f"absolute path rejected: {path!r}")

        normalized = os.path.normpath(path)
        if normalized in (".", "..") or normalized.startswith(".." + os.sep):
            raise BoundaryViolation(f"path escapes worktree: {path!r}")

        lexical = os.path.abspath(os.path.join(self._worktree_root, normalized))
        resolved = os.path.realpath(lexical)
        if not _inside(lexical, self._worktree_root) or not _inside(
            resolved, self._worktree_root
        ):
            raise BoundaryViolation(f"path escapes worktree: {path!r}")

        for allowed in self._allowed_paths:
            if allowed["directory"]:
                if _inside(lexical, allowed["lexical"]) and _inside(
                    resolved, allowed["resolved"]
                ):
                    return
            elif lexical == allowed["lexical"] and resolved == allowed["resolved"]:
                return

        raise BoundaryViolation(f"path outside allowed_paths: {path!r}")

    # Keep the established interface used by RunnerFileTools. Reads, writes,
    # and patches all pass through the same capability check.
    def check_write(self, path):
        self.check_path(path)

    def check_command(self, argv):
        if not isinstance(argv, list) or not argv or not all(
            isinstance(item, str) and item for item in argv
        ):
            raise BoundaryViolation(f"invalid command rejected: {argv!r}")
        if tuple(argv) not in self._allowed_commands:
            raise BoundaryViolation(f"command outside verification_commands: {argv!r}")

    def env_for_subprocess(self):
        return stripped_agent_env()


ALLOWED_ENV_VAR_NAMES = {"OLLAMA_HOST"}


def stripped_agent_env(source_env=None):
    """Return the minimal environment used by model and acceptance commands."""
    source_env = source_env if source_env is not None else os.environ
    stripped = {}
    if "PATH" in source_env:
        stripped["PATH"] = source_env["PATH"]
    for key, value in source_env.items():
        if key in ALLOWED_ENV_VAR_NAMES:
            stripped[key] = value
    return stripped
