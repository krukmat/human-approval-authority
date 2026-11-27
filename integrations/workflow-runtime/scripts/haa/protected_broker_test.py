from hashlib import sha256
from pathlib import Path
import os
import socket
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts.haa.protected_broker import (
    BrokerError, WorkerBroker, _replace_existing, read_message, write_message,
)
from scripts.haa.volatile_authority import VolatileLeaseStore


class BrokerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / "README.md"
        self.path.write_text("before")
        self.before = sha256(b"before").hexdigest()

    def test_exact_preimage_and_no_stale_replay(self):
        after = _replace_existing(self.root, "README.md", self.before, "after")
        self.assertEqual(after, sha256(b"after").hexdigest())
        with self.assertRaisesRegex(BrokerError, "STALE_PREIMAGE"):
            _replace_existing(self.root, "README.md", self.before, "again")

    def test_hardlink_and_symlink_denied(self):
        (self.root / "link").symlink_to(self.path)
        with self.assertRaises(BrokerError):
            _replace_existing(self.root, "link", self.before, "bad")
        os.link(self.path, self.root / "hardlink")
        with self.assertRaises(BrokerError):
            _replace_existing(self.root, "README.md", self.before, "bad")

    def test_framed_json_roundtrip(self):
        a,b = socket.socketpair()
        with a,b:
            write_message(a, {"op":"status"})
            self.assertEqual(read_message(b), {"op":"status"})

    def test_wrong_uid_and_arbitrary_command_denied(self):
        authority = Mock()
        authority.leases = Mock(spec=VolatileLeaseStore)
        uid = 502 if os.geteuid() != 502 else 503
        broker = WorkerBroker(authority, worker_uid=uid)
        with self.assertRaisesRegex(BrokerError,"PEER_NOT_AUTHORIZED"):
            broker.dispatch(uid+1, {"op":"status"})
        with self.assertRaisesRegex(BrokerError,"UNSUPPORTED_PROPOSAL"):
            broker.dispatch(uid, {"op":"run","argv":["true"]})
        authority.edit.assert_not_called()

    def test_stale_worker_window_denied(self):
        authority=Mock()
        authority.leases=Mock(spec=VolatileLeaseStore)
        uid=os.geteuid()+1
        old=WorkerBroker(authority,worker_uid=uid)
        new=WorkerBroker(authority,worker_uid=uid)
        status=old.dispatch(uid,{"op":"status"})
        with self.assertRaisesRegex(BrokerError,"STALE_WORKER_WINDOW"):
            new.dispatch(uid,{"op":"replace","window":status["window"],
                              "path":"README.md","before_sha256":self.before,"content":"bad"})
        authority.edit.assert_not_called()

    def test_one_proposal_and_sealed_evidence(self):
        authority=Mock()
        authority.leases=Mock(spec=VolatileLeaseStore)
        authority.scope.task.repo_root=self.root
        authority.edit.side_effect=lambda path,effect:effect()
        uid=os.geteuid()+1
        broker=WorkerBroker(authority,worker_uid=uid)
        window=broker.dispatch(uid,{"op":"status"})["window"]
        msg={"op":"replace","window":window,"path":"README.md",
             "before_sha256":self.before,"content":"after"}
        self.assertEqual(broker.dispatch(uid,msg)["status"],"REPLACED")
        with self.assertRaisesRegex(BrokerError,"WINDOW_CLOSED"):
            broker.dispatch(uid,msg)
        self.assertEqual(broker.seal(),("README.md",sha256(b"after").hexdigest()))
        with self.assertRaisesRegex(BrokerError,"WINDOW_CLOSED"):
            broker.dispatch(uid,{"op":"status"})
        authority.edit.assert_called_once()

    def test_no_disk_lease_store(self):
        authority=Mock()
        with self.assertRaisesRegex(BrokerError,"VOLATILE_AUTHORITY_REQUIRED"):
            WorkerBroker(authority, worker_uid=os.geteuid()+1)
