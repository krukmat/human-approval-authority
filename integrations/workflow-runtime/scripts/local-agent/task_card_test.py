#!/usr/bin/env python3

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from task_card import (
    LegacyTaskCardConversionRequired,
    SOURCE_SCHEMA_LEGACY,
    TaskCardValidationError,
    adapt_legacy,
    parse_task_card,
)


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


    def test_strict_parser_rejects_unknown_fields_and_duplicate_criteria(self):
        data = _v2()
        data["unexpected"] = True
        with self.assertRaises(TaskCardValidationError):
            parse_task_card(data)
        data = _v2()
        data["acceptance_criteria"].append(dict(data["acceptance_criteria"][0]))
        with self.assertRaises(TaskCardValidationError):
            parse_task_card(data)

    def test_v2_preserves_command_and_criterion_identifiers(self):
        card = parse_task_card(_v2())
        self.assertEqual(card.verification_commands[0].id, "verify-unit")
        self.assertEqual(card.verification_commands[0].criterion_ids, ("HP-1",))


if __name__ == "__main__":
    unittest.main()
