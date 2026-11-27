from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import os
import unittest

from scripts.haa.native_batch_worker import run_native


class NativeBatchWorkerTest(unittest.TestCase):
    def setUp(self):
        self.args=dict(worker_uid=502,repository="krukmat/dubbridge",rri=35,
            task_id="t",paths=("a.txt",),python=Path("/python"),scratch=Path("/scratch"),
            runner=Path("/staged/run_local_task.py"),input_file=Path("/card"),
            output_file=Path("/out"),socket_path=Path("/socket"))
        self.env=patch("scripts.haa.native_batch_worker.os.geteuid",return_value=502)
        self.env.start();self.addCleanup(self.env.stop)
        self.invocation=patch("scripts.haa.native_batch_worker.local_invocation",
            return_value=SimpleNamespace(argv=("/python","runner"),cwd=Path("/scratch")))
        self.invocation.start();self.addCleanup(self.invocation.stop)

    def test_existing_runner_once_and_no_haa_credentials(self):
        with patch.dict(os.environ,{"HAA_EXECUTOR_API_KEY":"fixture-secret","OLLAMA_HOST":"fixture"}), \
             patch("scripts.haa.native_batch_worker.send_proposal",
                side_effect=[{"status":"BROKER_REACHABLE","window":"w"},
                             {"status":"BATCH_ACCEPTED","paths":["a.txt"]}]) as broker, \
             patch("scripts.haa.native_batch_worker.subprocess.run",
                   return_value=SimpleNamespace(returncode=0)) as run, \
             patch("scripts.haa.native_batch_worker.collect",
                   return_value=[{"path":"a.txt","content":"after","before_sha256":"a"*64}]):
            self.assertEqual(run_native(**self.args)["status"],"BATCH_ACCEPTED")
            run.assert_called_once()
            self.assertNotIn("HAA_EXECUTOR_API_KEY",run.call_args.kwargs["env"])
            self.assertEqual(broker.call_count,2)

    def test_wrong_identity_no_runner_or_broker(self):
        with patch("scripts.haa.native_batch_worker.subprocess.run") as run, \
             patch("scripts.haa.native_batch_worker.send_proposal") as broker:
            with self.assertRaisesRegex(RuntimeError,"SEPARATE_WORKER"):
                run_native(**{**self.args,"worker_uid":503})
            run.assert_not_called();broker.assert_not_called()

    def test_runner_failure_never_submits(self):
        with patch("scripts.haa.native_batch_worker.send_proposal",
                   return_value={"status":"BROKER_REACHABLE","window":"w"}) as broker, \
             patch("scripts.haa.native_batch_worker.subprocess.run",
                   return_value=SimpleNamespace(returncode=1)) as run, \
             patch("scripts.haa.native_batch_worker.collect") as collect:
            with self.assertRaisesRegex(RuntimeError,"NATIVE_RUNNER_FAILED"):
                run_native(**self.args)
            run.assert_called_once();broker.assert_called_once();collect.assert_not_called()
