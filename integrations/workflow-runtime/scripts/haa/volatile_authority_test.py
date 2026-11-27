from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor
import unittest

from scripts.haa.authority_lease import AuthorityLease, LeaseError
from scripts.haa.contracts import digest_json
from scripts.haa.volatile_authority import AdmissionJournal, VolatileLeaseStore


class VolatileAuthorityTest(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        AdmissionJournal.initialize(self.root)
        self.wall=datetime.now(UTC)
        self.mono=100.0
        self.store=self.open_store()
        self.lease=AuthorityLease(
            lease_id="a"*32, request_id="r", execution_id="e", action_digest="action",
            repository="example/workflow-fixture", plan_id="p", task_id="t", session_id="s",
            branch="test", base_commit_sha="b"*40, scope_digest="scope",
            allowed_paths=("README.md",), capabilities=("edit","test"), rri=55,
            issued_at=self.wall.isoformat(), expires_at=(self.wall+timedelta(seconds=300)).isoformat(),
            grant_digest=digest_json({"grant":"fixture"}))

    def open_store(self):
        store=VolatileLeaseStore(AdmissionJournal(self.root), clock=lambda:self.mono, wall=lambda:self.wall)
        self.addCleanup(store.close)
        return store

    def test_no_restore_after_revoke_or_restart(self):
        self.store.create(self.lease)
        self.assertEqual(self.store.load(self.lease.lease_id), self.lease)
        self.store.revoke(self.lease.lease_id)
        with self.assertRaisesRegex(LeaseError,"NO_LIVE_AUTHORITY"):
            self.store.load(self.lease.lease_id)
        generation=self.store.generation
        self.store.close()
        restored=self.open_store()
        self.assertNotEqual(generation, restored.generation)
        with self.assertRaisesRegex(LeaseError,"NO_LIVE_AUTHORITY"):
            restored.load(self.lease.lease_id)
        with self.assertRaisesRegex(LeaseError,"AUTHORIZATION_ALREADY_ADMITTED"):
            restored.create(replace(self.lease,lease_id="c"*32))

    def test_crash_equivalent_restart_denies_old_admission(self):
        self.store.create(self.lease)
        self.store.close()
        restored=self.open_store()
        with self.assertRaises(LeaseError):
            restored.load(self.lease.lease_id)
        with self.assertRaisesRegex(LeaseError,"ALREADY_ADMITTED"):
            restored.create(self.lease)

    def test_monotonic_expiry_despite_frozen_wall(self):
        self.store.create(self.lease)
        self.mono+=301
        with self.assertRaisesRegex(LeaseError,"CLOCK_ROLLBACK"):
            self.store.load(self.lease.lease_id)

    def test_wall_rollback_revokes(self):
        self.store.create(self.lease)
        self.wall-=timedelta(seconds=1)
        with self.assertRaisesRegex(LeaseError,"CLOCK_ROLLBACK"):
            self.store.load(self.lease.lease_id)
        with self.assertRaisesRegex(LeaseError,"NO_LIVE_AUTHORITY"):
            self.store.load(self.lease.lease_id)

    def test_duplicate_grant_concurrent(self):
        def create(value):
            try:
                self.store.create(value)
                return "OK"
            except LeaseError as exc:
                return str(exc)
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(create,[self.lease,replace(self.lease,lease_id="c"*32)]))
        self.assertEqual(outcomes.count("OK"),1)

    def test_second_service_denied(self):
        with self.assertRaises(OSError):
            AdmissionJournal(self.root)

    def test_missing_journal_not_recreated(self):
        self.store.close()
        (self.root/"admissions.sqlite3").unlink()
        with self.assertRaises(OSError):
            AdmissionJournal(self.root)
        self.assertFalse((self.root/"admissions.sqlite3").exists())
