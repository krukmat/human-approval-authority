from dataclasses import replace
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

from scripts.haa.handoff import live_handoff_pin, validate_handoff, HandoffError
from scripts.haa.protected_session import ProtectedSession, SessionError


class HandoffTest(unittest.TestCase):
    def setUp(self):
        self.authority=Mock()
        self.authority._lock=RLock()
        self.task=SimpleNamespace(repo_root=Path("/fixture"),repository="example/project",
            session_id="s",card_sha256="a"*64,policy_pin=Mock())
        self.task.policy_pin.digest.return_value="b"*64
        self.authority.scope=SimpleNamespace(task=self.task,lease_id="l")
        self.authority.leases.load.return_value=SimpleNamespace(
            repository=self.task.repository,session_id="s",branch="candidate",
            base_commit_sha="c"*40,grant_digest="sha256:fixture")
        self.git=patch("scripts.haa.handoff._git",side_effect=lambda root,*argv:
                       "candidate" if argv[0]=="symbolic-ref" else "c"*40)
        self.git.start();self.addCleanup(self.git.stop)
        self.pin=live_handoff_pin(self.authority,worker_uid=502)

    def test_same_worker_and_scope_reuse_live_authority(self):
        self.assertEqual(validate_handoff(self.authority,self.pin,worker_uid=502),
                         "SAME_LIVE_AUTHORITY")
        self.authority._check.assert_called_with("test")

    def test_scope_and_worker_drift_denied(self):
        with self.assertRaisesRegex(HandoffError,"NEW_WORKER"):
            validate_handoff(self.authority,self.pin,worker_uid=503)
        for key,value in (("card_sha256","x"),("session_id","other"),
                          ("policy_digest","other"),("base_commit_sha","d"*40)):
            with self.subTest(key=key),self.assertRaisesRegex(HandoffError,"SCOPE_CHANGED"):
                validate_handoff(self.authority,replace(self.pin,**{key:value}),worker_uid=502)

    def test_expired_or_revoked_lease_propagates_denial(self):
        self.authority._check.side_effect=RuntimeError("NO_LIVE_AUTHORITY")
        with self.assertRaisesRegex(RuntimeError,"NO_LIVE_AUTHORITY"):
            validate_handoff(self.authority,self.pin,worker_uid=502)

    def test_owner_session_invalidates_on_identity_mismatch(self):
        session=ProtectedSession.__new__(ProtectedSession)
        session._lock=RLock();session._closed=False;session._authority=self.authority
        session._worker_window_used=False;session.layout=SimpleNamespace(worker_uid=502)
        session.leases=Mock()
        with self.assertRaisesRegex(HandoffError,"NEW_WORKER"):
            session.authorize_handoff(replace(self.pin,worker_uid=503))
        self.assertTrue(session._closed)
        self.authority.close.assert_called_once()
        session.leases.close.assert_called_once()

    def test_no_handoff_after_proposal_window_opened(self):
        session=ProtectedSession.__new__(ProtectedSession)
        session._lock=RLock();session._closed=False;session._authority=self.authority
        session._worker_window_used=True
        with self.assertRaisesRegex(SessionError,"WINDOW_UNAVAILABLE"):
            session.authorize_handoff(self.pin)
