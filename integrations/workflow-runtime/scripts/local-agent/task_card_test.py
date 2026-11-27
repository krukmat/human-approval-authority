#!/usr/bin/env python3

import os
import sys
import unittest
import tempfile
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from task_card import (
    LegacyTaskCardConversionRequired,
    SOURCE_SCHEMA_LEGACY,
    TaskCardValidationError,
    adapt_legacy,
    parse_task_card,
)
import run_local_task as rlt


def _v2():
    return {
        "schema_version": 2,
        "card_id": "card-1",
        "task_id": "task-1",
        "spec": "Implement the bounded change.",
        "allowed_paths": ["src/lib.rs"],
        "acceptance_criteria": [{"id": "HP-1", "statement": "Validation code uses typed input."}],
        "verification_commands": [
            {"id": "verify-unit", "criterion_ids": ["HP-1"], "argv": ["env", "MODE=test", "cargo", "test"]}
        ],
    }


class TaskCardTest(unittest.TestCase):
    def test_v2_keeps_prose_separate_from_exact_argv(self):
        card = parse_task_card(_v2())
        self.assertEqual(card.acceptance_criteria[0].statement, "Validation code uses typed input.")
        self.assertEqual(card.verification_commands[0].argv, ("env", "MODE=test", "cargo", "test"))
        self.assertNotIn("Validation", card.verification_commands[0].argv)

    def test_explicit_shell_is_preserved_as_argv(self):
        data = _v2()
        data["verification_commands"][0]["argv"] = ["bash", "-lc", "cargo test && cargo fmt --check"]
        self.assertEqual(parse_task_card(data).verification_argvs[0][0], "bash")

    def test_legacy_nonempty_acceptance_tests_requires_conversion(self):
        with self.assertRaises(LegacyTaskCardConversionRequired):
            adapt_legacy({"task_id": "old", "spec": "old", "acceptance_tests": ["Validation code uses typed input."], "allowed_paths": []})

    def test_legacy_is_never_implicit(self):
        with self.assertRaises(TaskCardValidationError):
            parse_task_card({"task_id": "old", "spec": "old", "allowed_paths": []})

    def test_empty_legacy_card_has_visible_provenance(self):
        card = adapt_legacy({"task_id": "old", "spec": "old", "allowed_paths": [], "acceptance_tests": []})
        self.assertEqual(card.source_schema, SOURCE_SCHEMA_LEGACY)

    def test_unknown_criterion_reference_is_rejected(self):
        data = _v2()
        data["verification_commands"][0]["criterion_ids"] = ["missing"]
        with self.assertRaises(TaskCardValidationError):
            parse_task_card(data)

    def test_verification_command_must_identify_proven_criteria(self):
        data = _v2()
        data["verification_commands"][0]["criterion_ids"] = []
        with self.assertRaises(TaskCardValidationError):
            parse_task_card(data)

    def test_identity_formats_fail_closed(self):
        for field in ("card_id", "task_id"):
            data = _v2()
            data[field] = "bad id"
            with self.subTest(field=field), self.assertRaises(TaskCardValidationError):
                parse_task_card(data)
        data = _v2()
        data["acceptance_criteria"][0]["id"] = "1-not-a-criterion"
        with self.assertRaises(TaskCardValidationError):
            parse_task_card(data)

    def test_allowed_paths_must_be_repository_relative(self):
        for invalid_path in ("/tmp/file", "../outside", "."):
            data = _v2()
            data["allowed_paths"] = [invalid_path]
            with self.subTest(path=invalid_path), self.assertRaises(TaskCardValidationError):
                parse_task_card(data)

    def test_optional_governance_fields_are_validated(self):
        for field, value in (("band", "Medium"), ("capsule_hash", "not-a-hash")):
            data = _v2()
            data[field] = value
            with self.subTest(field=field), self.assertRaises(TaskCardValidationError):
                parse_task_card(data)

    def test_runner_executes_only_structured_argv_and_preserves_ids(self):
        card = parse_task_card(_v2())
        boundary = Mock()
        observed = {}

        def execute(argv, worktree_dir, active_boundary):
            observed["argv"] = argv
            return {"tool": "run_command", "argv": argv, "ok": True, "returncode": 0, "stdout": "", "stderr": ""}

        with patch.object(rlt.session_loop, "_run_command_with_timeout", side_effect=execute):
            result = rlt.build_default_test_runner(card, boundary)("/tmp/worktree")

        self.assertTrue(result["passed"])
        self.assertEqual(observed["argv"], ["env", "MODE=test", "cargo", "test"])
        self.assertEqual(result["commands"][0]["command_id"], "verify-unit")
        self.assertEqual(result["commands"][0]["criterion_ids"], ["HP-1"])

    def test_invalid_legacy_prose_fails_before_context_or_model(self):
        data = {"task_id": "old", "spec": "old", "allowed_paths": [], "acceptance_tests": ["Validation code uses typed input."]}
        chat = Mock()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "card.json")
            out = os.path.join(tmp, "out.json")
            with open(path, "w", encoding="utf-8") as handle:
                import json
                json.dump(data, handle)
            with self.assertRaises(LegacyTaskCardConversionRequired):
                rlt.main(["--card", path, "--legacy-card", "--worktree", tmp, "--out", out], chat_fn=chat)
        chat.assert_not_called()


if __name__ == "__main__":
    unittest.main()
