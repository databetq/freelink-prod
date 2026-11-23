import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import escrow_worker
from app.escrow_chain import EscrowChain


class ConfirmedBlockTest(unittest.TestCase):
    def confirmed_number(self, confirmations, latest=100):
        requested = []

        def fake_block(_, number="finalized"):
            requested.append(number)
            return {"number": hex({"finalized": 80, "latest": latest}.get(number) or int(number, 16))}

        chain = EscrowChain.__new__(EscrowChain)
        with (patch("app.escrow_chain.get_settings", return_value=SimpleNamespace(escrow_confirmations=confirmations)),
              patch.object(EscrowChain, "block", fake_block)):
            return int(chain.confirmed_block()["number"], 16), requested

    def test_waits_for_finality_by_default(self):
        self.assertEqual(self.confirmed_number(None), (80, ["finalized"]))

    def test_demo_setting_counts_confirmations_from_the_latest_block(self):
        self.assertEqual(self.confirmed_number(3), (97, ["latest", hex(97)]))

    def test_a_new_chain_never_asks_for_a_negative_block(self):
        _, requested = self.confirmed_number(3, latest=1)
        self.assertEqual(requested[-1], hex(0))


class WorkerLoopTest(unittest.TestCase):
    def test_an_unexpected_reply_does_not_stop_the_worker(self):
        replies = iter([TypeError("unexpected RPC reply"), None])

        def sync():
            reply = next(replies)
            if reply:
                raise reply

        pauses = []

        def pause(seconds):
            pauses.append(seconds)
            if len(pauses) == 2:
                raise KeyboardInterrupt

        with (patch.object(escrow_worker, "sync_once", sync), patch.object(escrow_worker, "sleep", pause),
              self.assertLogs(escrow_worker.logger, "ERROR") as logs, self.assertRaises(KeyboardInterrupt)):
            escrow_worker.main()
        self.assertEqual(len(pauses), 2)
        self.assertIn("error_type=TypeError", logs.output[0])
        self.assertNotIn("unexpected RPC reply", logs.output[0])


if __name__ == "__main__":
    unittest.main()
