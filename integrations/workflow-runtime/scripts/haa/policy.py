"""Trusted policy snapshot, independent of any global RRI threshold.

Only the protected supervisor may construct pins. A pin is not approval,
a grant, a reviewer verdict or permission to run a side effect.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat


class PolicyError(ValueError):
    pass


CAPABILITIES = frozenset({"edit", "test", "review", "commit"})


def _hash_file(root, relative):
    if (not isinstance(relative, str) or not relative or "\\" in relative
            or any(p in {"", ".", "..", ".git", ".agent"} for p in relative.split("/"))
            or PurePosixPath(relative).is_absolute()):
        raise PolicyError("INVALID_POLICY_SOURCE")
    root = Path(root).resolve()
    target = root / relative
    if target.resolve() != target:
        raise PolicyError("UNSAFE_POLICY_SOURCE")
    try:
        fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise PolicyError("UNSAFE_POLICY_SOURCE")
            data = stream.read(1024 * 1024 + 1)
    except OSError as exc:
        raise PolicyError("POLICY_SOURCE_UNAVAILABLE") from exc
    if len(data) > 1024 * 1024:
        raise PolicyError("POLICY_SOURCE_TOO_LARGE")
    return sha256(data).hexdigest()


@dataclass(frozen=True)
class PolicyPin:
    repository: str
    card_sha256: str
    rri: int
    requires_haa: bool
    capabilities: tuple[str, ...]
    sources: tuple[tuple[str, str], ...]
    plan_close_requires_haa: bool

    def validate(self, *, root, repository, card_sha256, rri, capabilities):
        if (not isinstance(self.repository, str) or not self.repository
                or self.repository != repository
                or not isinstance(self.card_sha256, str)
                or not re.fullmatch(r"[0-9a-f]{64}", self.card_sha256)
                or self.card_sha256 != card_sha256
                or type(self.rri) is not int or self.rri < 0 or self.rri != rri
                or type(self.requires_haa) is not bool
                or type(self.plan_close_requires_haa) is not bool
                or not self.capabilities or set(self.capabilities) - CAPABILITIES
                or self.capabilities != tuple(sorted(set(capabilities)))
                or not self.sources or len({p for p, _ in self.sources}) != len(self.sources)
                or self.sources != tuple(sorted(self.sources))):
            raise PolicyError("INVALID_POLICY_PIN")
        for path, digest in self.sources:
            if _hash_file(root, path) != digest:
                raise PolicyError("POLICY_SOURCE_CHANGED")
        return self

    def digest(self):
        value = [self.repository, self.card_sha256, self.rri, self.requires_haa,
                 self.capabilities, self.sources, self.plan_close_requires_haa]
        return sha256(json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


def pin_policy(*, root, repository, card_sha256, rri, requires_haa,
               capabilities, source_paths, plan_close_requires_haa):
    """The caller must be the trusted policy resolver, never the worker."""
    caps = tuple(capabilities)
    paths = tuple(source_paths)
    if len(set(caps)) != len(caps) or len(set(paths)) != len(paths):
        raise PolicyError("DUPLICATE_POLICY_INPUT")
    pin = PolicyPin(repository, card_sha256, rri, requires_haa,
                    tuple(sorted(caps)), tuple(sorted((p, _hash_file(root, p)) for p in paths)),
                    plan_close_requires_haa)
    return pin.validate(root=root, repository=repository, card_sha256=card_sha256,
                        rri=rri, capabilities=caps)


PROJECT_SOURCES = {
    "krukmat/fenix": ("README_AGENT_ORDER.md", "AGENTS.md", "CLAUDE.md",
        "docs/playbooks/AGENT_WORKFLOW_GUIDE.md", "docs/policies/HITL_AUTONOMY_POLICY.md",
        "docs/policies/RRI_POLICY.md", "docs/policies/LOCAL_MODEL_POLICY.md"),
    "krukmat/dubbridge": ("README_AGENT_ORDER.md", "AGENTS.md", "CLAUDE.md",
        "docs/playbooks/AGENT_WORKFLOW_GUIDE.md", "docs/policies/HITL_AUTONOMY_POLICY.md",
        "docs/policies/RRI_POLICY.md"),
}


def pin_project_policy(*, root, repository, card_sha256, rri, requires_haa,
                       capabilities, plan_close_requires_haa):
    """Adapters bind governing sources; the existing workflow resolves its policy.

    This is not an RRI calculator or a replacement for existing HITL/QA gates.
    """
    if repository not in PROJECT_SOURCES:
        raise PolicyError("UNKNOWN_PROJECT_POLICY")
    return pin_policy(root=root, repository=repository, card_sha256=card_sha256,
                      rri=rri, requires_haa=requires_haa, capabilities=capabilities,
                      source_paths=PROJECT_SOURCES[repository],
                      plan_close_requires_haa=plan_close_requires_haa)
