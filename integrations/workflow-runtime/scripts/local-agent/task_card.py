#!/usr/bin/env python3
"""Versioned, immutable task-card contract shared by local-agent tooling."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Optional


SCHEMA_VERSION = 2
SOURCE_SCHEMA_V2 = "task-card-v2"
SOURCE_SCHEMA_LEGACY = "legacy-v1"
CARD_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}\Z")
CRITERION_ID_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9._-]{0,63}\Z")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
RRI_BANDS = frozenset(
    {"Low", "Moderate", "Med-high", "Complex", "High", "Very high", "Excessive"}
)


class TaskCardValidationError(ValueError):
    """The task card is not safe to interpret."""


class LegacyTaskCardConversionRequired(TaskCardValidationError):
    """A legacy card contains commands that require an operator conversion."""


@dataclass(frozen=True)
class AcceptanceCriterion:
    id: str
    statement: str

    def as_dict(self):
        return {"id": self.id, "statement": self.statement}


@dataclass(frozen=True)
class VerificationCommand:
    id: str
    criterion_ids: tuple[str, ...]
    argv: tuple[str, ...]

    def as_dict(self):
        return {
            "id": self.id,
            "criterion_ids": list(self.criterion_ids),
            "argv": list(self.argv),
        }


@dataclass(frozen=True)
class TaskCard:
    schema_version: int
    card_id: str
    task_id: str
    spec: str
    allowed_paths: tuple[str, ...]
    acceptance_criteria: tuple[AcceptanceCriterion, ...]
    verification_commands: tuple[VerificationCommand, ...]
    source_schema: str = SOURCE_SCHEMA_V2
    rri: Optional[int] = None
    band: Optional[str] = None
    capsule_hash: Optional[str] = None
    policy_version: Optional[str] = None
    plan: Optional[str] = None

    @property
    def verification_argvs(self):
        return tuple(command.argv for command in self.verification_commands)

    def criteria_payload(self):
        return [criterion.as_dict() for criterion in self.acceptance_criteria]

    def commands_payload(self):
        return [command.as_dict() for command in self.verification_commands]


def criteria_payload(card):
    """Render typed criteria, tolerating legacy-shaped in-memory test doubles."""
    if hasattr(card, "criteria_payload"):
        return card.criteria_payload()
    return [
        {"id": f"legacy-{index}", "statement": str(statement)}
        for index, statement in enumerate(getattr(card, "acceptance_tests", ()), start=1)
    ]


def commands_payload(card):
    """Render typed commands; legacy prose is deliberately never converted."""
    if hasattr(card, "commands_payload"):
        return card.commands_payload()
    return []


_V2_KEYS = frozenset(
    {
        "schema_version",
        "card_id",
        "task_id",
        "spec",
        "allowed_paths",
        "acceptance_criteria",
        "verification_commands",
        "rri",
        "band",
        "capsule_hash",
        "policy_version",
        "plan",
    }
)
_LEGACY_KEYS = frozenset(
    {
        "task_id",
        "spec",
        "allowed_paths",
        "acceptance_tests",
        "rri",
        "band",
        "capsule_hash",
        "policy_version",
        "plan",
    }
)


def _object(value, label):
    if not isinstance(value, dict):
        raise TaskCardValidationError(f"{label} must be an object")
    return value


def _string(value, label):
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise TaskCardValidationError(f"{label} must be a non-empty string without NUL")
    return value


def _optional_string(value, label):
    if value is None:
        return None
    return _string(value, label)


def _matching_string(value, label, pattern):
    value = _string(value, label)
    if pattern.fullmatch(value) is None:
        raise TaskCardValidationError(f"{label} has an invalid format")
    return value


def _repository_path(value, label):
    value = _string(value, label)
    path = PurePosixPath(value)
    if path.is_absolute() or value == "." or ".." in path.parts:
        raise TaskCardValidationError(f"{label} must be repository-relative")
    return value


def _list(value, label):
    if not isinstance(value, list):
        raise TaskCardValidationError(f"{label} must be a list")
    return value


def _reject_unknown(data, allowed, label):
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise TaskCardValidationError(f"unknown {label} field(s): {', '.join(unknown)}")


def _unique_strings(values, label):
    parsed = tuple(_string(value, f"{label}[{index}]") for index, value in enumerate(values))
    if len(set(parsed)) != len(parsed):
        raise TaskCardValidationError(f"{label} entries must be unique")
    return parsed


def _unique_paths(values, label):
    parsed = tuple(_repository_path(value, f"{label}[{index}]") for index, value in enumerate(values))
    if len(set(parsed)) != len(parsed):
        raise TaskCardValidationError(f"{label} entries must be unique")
    return parsed


def parse_v2(data):
    data = _object(data, "task card")
    _reject_unknown(data, _V2_KEYS, "task card")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise TaskCardValidationError(f"schema_version must be {SCHEMA_VERSION}")

    criterion_values = _list(data.get("acceptance_criteria"), "acceptance_criteria")
    criteria = []
    criterion_ids = set()
    for index, value in enumerate(criterion_values):
        value = _object(value, f"acceptance_criteria[{index}]")
        _reject_unknown(value, {"id", "statement"}, f"acceptance_criteria[{index}]")
        criterion_id = _matching_string(
            value.get("id"),
            f"acceptance_criteria[{index}].id",
            CRITERION_ID_PATTERN,
        )
        if criterion_id in criterion_ids:
            raise TaskCardValidationError(f"duplicate acceptance criterion id: {criterion_id}")
        criterion_ids.add(criterion_id)
        criteria.append(
            AcceptanceCriterion(
                id=criterion_id,
                statement=_string(
                    value.get("statement"), f"acceptance_criteria[{index}].statement"
                ),
            )
        )

    command_values = _list(data.get("verification_commands"), "verification_commands")
    commands = []
    command_ids = set()
    for index, value in enumerate(command_values):
        value = _object(value, f"verification_commands[{index}]")
        _reject_unknown(
            value, {"id", "criterion_ids", "argv"}, f"verification_commands[{index}]"
        )
        command_id = _string(value.get("id"), f"verification_commands[{index}].id")
        if command_id in command_ids:
            raise TaskCardValidationError(f"duplicate verification command id: {command_id}")
        command_ids.add(command_id)
        references = _unique_strings(
            _list(value.get("criterion_ids"), f"verification_commands[{index}].criterion_ids"),
            f"verification_commands[{index}].criterion_ids",
        )
        if not references:
            raise TaskCardValidationError(
                f"verification_commands[{index}].criterion_ids must not be empty"
            )
        missing = sorted(set(references) - criterion_ids)
        if missing:
            raise TaskCardValidationError(
                f"verification command {command_id!r} references unknown criteria: "
                + ", ".join(missing)
            )
        argv = tuple(
            _string(item, f"verification_commands[{index}].argv[{item_index}]")
            for item_index, item in enumerate(
                _list(value.get("argv"), f"verification_commands[{index}].argv")
            )
        )
        if not argv:
            raise TaskCardValidationError(
                f"verification_commands[{index}].argv must not be empty"
            )
        commands.append(VerificationCommand(command_id, references, argv))

    rri = data.get("rri")
    if rri is not None and (isinstance(rri, bool) or not isinstance(rri, int)):
        raise TaskCardValidationError("rri must be an integer or null")

    band = _optional_string(data.get("band"), "band")
    if band is not None and band not in RRI_BANDS:
        raise TaskCardValidationError("band must be a repository RRI band label or null")

    capsule_hash = _optional_string(data.get("capsule_hash"), "capsule_hash")
    if capsule_hash is not None and SHA256_PATTERN.fullmatch(capsule_hash) is None:
        raise TaskCardValidationError("capsule_hash must be a lowercase SHA-256 hex digest")

    return TaskCard(
        schema_version=SCHEMA_VERSION,
        card_id=_matching_string(data.get("card_id"), "card_id", CARD_ID_PATTERN),
        task_id=_matching_string(data.get("task_id"), "task_id", CARD_ID_PATTERN),
        spec=_string(data.get("spec"), "spec"),
        allowed_paths=_unique_paths(
            _list(data.get("allowed_paths"), "allowed_paths"), "allowed_paths"
        ),
        acceptance_criteria=tuple(criteria),
        verification_commands=tuple(commands),
        rri=rri,
        band=band,
        capsule_hash=capsule_hash,
        policy_version=_optional_string(data.get("policy_version"), "policy_version"),
        plan=_optional_string(data.get("plan"), "plan"),
    )


def adapt_legacy(data):
    """Explicitly adapt command-free v1 cards; never guess string semantics."""

    data = _object(data, "legacy task card")
    _reject_unknown(data, _LEGACY_KEYS, "legacy task card")
    acceptance_tests = data.get("acceptance_tests", [])
    if not isinstance(acceptance_tests, list):
        raise TaskCardValidationError("legacy acceptance_tests must be a list")
    if acceptance_tests:
        raise LegacyTaskCardConversionRequired(
            "legacy acceptance_tests is non-empty; convert prose and commands to task-card-v2"
        )
    converted = {
        "schema_version": SCHEMA_VERSION,
        "card_id": f"legacy/{_string(data.get('task_id'), 'task_id')}",
        "task_id": data.get("task_id"),
        "spec": data.get("spec"),
        "allowed_paths": data.get("allowed_paths", []),
        "acceptance_criteria": [],
        "verification_commands": [],
        **{key: data[key] for key in ("rri", "band", "capsule_hash", "policy_version", "plan") if key in data},
    }
    card = parse_v2(converted)
    return TaskCard(**{**card.__dict__, "source_schema": SOURCE_SCHEMA_LEGACY})


def parse_task_card(data, *, allow_legacy=False):
    if isinstance(data, dict) and data.get("schema_version") == SCHEMA_VERSION:
        return parse_v2(data)
    if allow_legacy:
        return adapt_legacy(data)
    raise TaskCardValidationError(
        "task-card-v2 required; use the explicit legacy compatibility path for v1"
    )


def load_task_card(path, *, allow_legacy=False):
    with open(path, encoding="utf-8") as handle:
        return parse_task_card(json.load(handle), allow_legacy=allow_legacy)
