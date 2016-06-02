import unittest
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

# mock
from pkg_resources import require
require("mock")
from mock import patch

# module imports
from malcolm.core.scheduler import Scheduler


class TestBlock(unittest.TestCase):

    @patch("malcolm.core.scheduler.ThreadPool")
    def setUp(self, mock_pool):
        self.s = Scheduler("sched")
        mock_pool.assert_called_once_with()
        self.assertEqual(self.s.pool, mock_pool.return_value)

    @patch("malcolm.core.scheduler.Queue")
    def test_queue_creation(self, mock_queue):
        q = self.s.create_queue()
        mock_queue.assert_called_once_with()
        self.assertEqual(q, mock_queue.return_value)

    @patch("malcolm.core.scheduler.Lock")
    def test_lock_creation(self, mock_lock):
        l = self.s.create_lock()
        mock_lock.assert_called_once_with()
        self.assertEqual(l, mock_lock.return_value)

    def test_spawned_calls_pool_apply(self):
        r = self.s.spawn(callable, "fred", b=43)
        self.s.pool.apply_async.assert_called_once_with(
            callable, ("fred",), dict(b=43))
        self.assertEqual(r, self.s.pool.apply_async.return_value)

if __name__ == "__main__":
    unittest.main(verbosity=2)