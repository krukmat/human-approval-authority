from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from scripts.haa.policy import PolicyPin
from scripts.haa.protected_session import ProtectedSession, SessionError
from scripts.haa.volatile_authority import VolatileLeaseStore


class ProtectedSessionTest(unittest.TestCase):
    def test_legacy_store_is_rejected(self):
        with patch("scripts.haa.protected_session.validate_layout"):
            with self.assertRaisesRegex(SessionError,"VOLATILE_AUTHORITY_REQUIRED"):
                ProtectedSession(layout=Mock(), task=Mock(), card_sha256="a"*64,
                                 authoritative_rri=55, checkpoints=Mock(), leases=Mock(),
                                 requester=Mock(), executor=Mock(), pin=Mock(), existing_boundary=Mock(),
                                 policy_pin=Mock(spec=PolicyPin,requires_haa=True))

    def test_fresh_attempt_only_and_no_premature_activation(self):
        layout=Mock()
        layout.target=Path("/target")
        layout.state=Path("/state")
        task=Mock()
        task.repo_root=layout.target
        checkpoints=Mock()
        checkpoints.authenticated=True
        checkpoints.directory=Path("/state/checkpoints")
        leases=Mock(spec=VolatileLeaseStore)
        leases.journal=Mock()
        leases.journal.directory=Path("/state/journal")
        pending=Mock()
        pending.status="WAITING_FOR_HUMAN"
        with patch("scripts.haa.protected_session.validate_layout"), \
             patch("scripts.haa.protected_session.bind_trusted_task",return_value=task), \
             patch("scripts.haa.protected_session.request_bound_task",return_value=pending) as req:
            session=ProtectedSession(layout=layout, task=task, card_sha256="a"*64,
                                     authoritative_rri=55, checkpoints=checkpoints, leases=leases,
                                     requester=Mock(), executor=Mock(), pin=Mock(), existing_boundary=Mock(),
                                 policy_pin=Mock(spec=PolicyPin,requires_haa=True))
            self.assertEqual(session.request(),"WAITING_FOR_HUMAN")
            with self.assertRaisesRegex(SessionError,"ALREADY_ATTEMPTED"):
                session.request()
            with self.assertRaisesRegex(SessionError,"NOT_APPROVED"):
                session.activate()
            req.assert_called_once()
            session.close()
            leases.close.assert_called_once()
