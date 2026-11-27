"""Real child-process crash/restart with synthetic authority only.

Run the same test under the protected executor UID for host evidence.
No HAA calls, credentials, activation, or privileges are requested.
"""
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

# Isolated child imports only from the selected installed/test code root.
ROOT=Path(__file__).resolve().parents[2]
CHILD=r"""
import sys
sys.path.insert(0,sys.argv[1])
from pathlib import Path
from datetime import datetime,UTC,timedelta
import json,os
from scripts.haa.authority_lease import AuthorityLease,LeaseError
from scripts.haa.contracts import digest_json
from scripts.haa.volatile_authority import AdmissionJournal,VolatileLeaseStore
root=Path(sys.argv[2])
mode=sys.argv[3]
record=root/"legacy-active.json"
if mode in ("crash","revoke"):
    AdmissionJournal.initialize(root)
    now=datetime.now(UTC)
    lease=AuthorityLease(lease_id="a"*32,request_id="r",execution_id="e",
        action_digest="action",repository="example/workflow-fixture",plan_id="p",
        task_id="t",session_id="s",branch="test",base_commit_sha="b"*40,
        scope_digest="scope",allowed_paths=("README.md",),capabilities=("edit","test"),
        rri=55,issued_at=now.isoformat(),expires_at=(now+timedelta(seconds=300)).isoformat(),
        grant_digest=digest_json({"grant":"synthetic-process-probe"}))
    store=VolatileLeaseStore(AdmissionJournal(root))
    store.create(lease)
    assert store.load(lease.lease_id)==lease
    # Deliberately save legacy ACTIVE bytes as a synthetic replay input.
    # The volatile store never reads this file.
    record.write_text(json.dumps(lease.record()))
    if mode=="revoke":
        store.revoke(lease.lease_id)
        try:
            store.load(lease.lease_id)
        except LeaseError as exc:
            assert str(exc)=="NO_LIVE_AUTHORITY"
        else:
            raise AssertionError("revocation failed")
        store.close()
        sys.exit(0)
    os._exit(23)
lease=AuthorityLease.parse(json.loads(record.read_text()))
store=VolatileLeaseStore(AdmissionJournal(root))
try:
    store.load(lease.lease_id)
except LeaseError as exc:
    assert str(exc)=="NO_LIVE_AUTHORITY"
else:
    raise AssertionError("restart restored authority")
try:
    store.create(lease)
except LeaseError as exc:
    assert str(exc)=="AUTHORIZATION_ALREADY_ADMITTED"
else:
    raise AssertionError("replay admitted")
store.close()
"""


class LeaseProcessRestartTest(unittest.TestCase):
    def exercise(self,mode,expected_exit):
        with TemporaryDirectory(prefix="haa-restart-") as tmp:
            directory=Path(tmp).resolve()
            def run(action):
                return subprocess.run([sys.executable,"-I","-B","-c",CHILD,
                                       str(ROOT),str(directory),action],
                                      capture_output=True,text=True,timeout=20)
            first=run(mode)
            self.assertEqual(first.returncode,expected_exit,first.stderr)
            second=run("restart")
            self.assertEqual(second.returncode,0,second.stderr)

    def test_crash_then_fresh_process_denies_replay(self):
        self.exercise("crash",23)

    def test_revoke_then_fresh_process_denies_replay(self):
        self.exercise("revoke",0)
