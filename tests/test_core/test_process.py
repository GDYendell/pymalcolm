import unittest
import sys
import os
# import logging
# logging.basicConfig(level=logging.DEBUG)
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

# mock
from pkg_resources import require
require("mock")
from mock import MagicMock

# module imports
from malcolm.core.process import \
        Process, BlockChanged, BlockNotify, PROCESS_STOP
from malcolm.core.syncfactory import SyncFactory
from malcolm.core.request import Request
from malcolm.core.response import Response


class TestProcess(unittest.TestCase):

    def test_init(self):
        s = MagicMock()
        p = Process("proc", s)
        s.create_queue.assert_called_once_with()
        self.assertEqual(p.q, s.create_queue.return_value)

    def test_starting_process(self):
        s = SyncFactory("sched")
        p = Process("proc", s)
        b = MagicMock()
        b.name = "myblock"
        p.add_block(b)
        self.assertEqual(p._blocks, dict(myblock=b))
        p.start()
        request = MagicMock()
        request.type_ = Request.POST
        request.endpoint = ["myblock", "foo"]
        p.q.put(request)
        # wait for spawns to have done their job
        p.stop()
        b.handle_request.assert_called_once_with(request)

    def test_error(self):
        s = SyncFactory("sched")
        p = Process("proc", s)
        p.log_exception = MagicMock()
        p.start()
        request = MagicMock()
        request.endpoint = ["anything"]
        request.to_dict.return_value = "<to_dict>"
        p.q.put(request)
        p.stop()
        p.log_exception.assert_called_once_with("Exception while handling %s",
                                                "<to_dict>")

    def test_spawned_adds_to_other_spawned(self):
        s = MagicMock()
        p = Process("proc", s)
        spawned = p.spawn(callable, "fred", a=4)
        self.assertEqual(spawned, s.spawn.return_value)
        self.assertEqual(p._other_spawned, [spawned])
        s.spawn.assert_called_once_with(callable, "fred", a=4)

    def test_get(self):
        p = Process("proc", MagicMock())
        block = MagicMock()
        block.name = "myblock"
        block.to_dict = MagicMock(
            return_value={"path_1":{"path_2":{"attr":"value"}}})
        request = MagicMock()
        request.type_ = Request.GET
        request.endpoint = ["myblock", "path_1", "path_2"]
        p.add_block(block)
        p.q.get = MagicMock(side_effect=[request, PROCESS_STOP])

        p.recv_loop()

        response = request.response_queue.put.call_args[0][0]
        self.assertEquals(Response.RETURN, response.type_)
        self.assertEquals({"attr":"value"}, response.value)

class TestSubscriptions(unittest.TestCase):

    def test_on_changed(self):
        changes = [[["path"], "value"]]
        s = MagicMock()
        p = Process("proc", s)
        p.on_changed(changes)
        p.q.put.assert_called_once_with(BlockChanged(changes=changes))

    def test_notify(self):
        s = MagicMock()
        p = Process("proc", s)
        p.notify_subscribers("block")
        p.q.put.assert_called_once_with(BlockNotify(name="block"))

    def test_subscribe(self):
        block = MagicMock(
            to_dict=MagicMock(
                return_value={"attr":"value", "inner":{"attr2":"other"}}))
        block.name = "block"
        p = Process("proc", MagicMock())
        sub_1 = Request.Subscribe(
            MagicMock(), MagicMock(), ["block"], False)
        sub_2 = Request.Subscribe(
            MagicMock(), MagicMock(), ["block", "inner"], True)
        p.q.get = MagicMock(side_effect = [sub_1, sub_2, PROCESS_STOP])

        p.add_block(block)
        p.recv_loop()

        self.assertEquals([sub_1, sub_2], p._subscriptions)
        sub_1.response_queue.put.assert_called_once_with(
                {"attr":"value", "inner":{"attr2":"other"}})
        sub_2.response_queue.put.assert_called_once_with(
                {"attr2":"other"})

    def test_overlapped_changes(self):
        block = MagicMock(
            to_dict=MagicMock(return_value={"attr":"value", "attr2":"other"}))
        block.name = "block"
        sub_1 = MagicMock()
        sub_1.endpoint = ["block"]
        sub_1.delta = False
        sub_2 = MagicMock()
        sub_2.endpoint = ["block"]
        sub_2.delta = True
        changes_1 = [[["block", "attr"], "changing_value"]]
        changes_2 = [[["block", "attr"], "final_value"]]
        request_1 = BlockChanged(changes_1)
        request_2 = BlockChanged(changes_2)
        request_3 = BlockNotify(block.name)
        s = MagicMock()
        p = Process("proc", s)
        p._subscriptions.append(sub_1)
        p._subscriptions.append(sub_2)
        p.q.get = MagicMock(
            side_effect = [request_1, request_2, request_3, PROCESS_STOP])

        p.add_block(block)
        p.recv_loop()

        sub_1.response_queue.put.assert_called_once_with(
            {"attr":"final_value", "attr2":"other"})
        sub_2.response_queue.put.assert_called_once_with(
            [[["attr"], "final_value"]])

    def test_partial_structure_subscriptions(self):
        block_1 = MagicMock(
            to_dict=MagicMock(
                return_value={"attr":"value", "inner":{"attr2":"value"}}))
        block_1.name = "block_1"
        block_2 = MagicMock(
            to_dict=MagicMock(return_value={"attr":"value"}))
        block_2.name = "block_2"

        sub_1 = MagicMock()
        sub_1.endpoint = ["block_1", "inner"]
        sub_1.delta = False
        sub_2 = MagicMock()
        sub_2.endpoint = ["block_1", "inner"]
        sub_2.delta = True

        changes_1 = [[["block_1", "inner", "attr2"], "new_value"],
            [["block_1", "attr"], "new_value"]]
        changes_2 = [[["block_2", "attr"], "block_2_value"]]
        request_1 = BlockChanged(changes_1)
        request_2 = BlockChanged(changes_2)
        request_3 = BlockNotify(block_1.name)
        request_4 = BlockNotify(block_2.name)
        p = Process("proc", MagicMock())
        p.q.get = MagicMock(side_effect = [request_1, request_2, request_3,
                                           request_4, PROCESS_STOP])
        p._subscriptions = [sub_1, sub_2]

        p.add_block(block_1)
        p.add_block(block_2)
        p.recv_loop()

        sub_1.response_queue.put.assert_called_once_with(
            {"attr2":"new_value"})
        sub_2.response_queue.put.assert_called_once_with(
            [[["attr2"], "new_value"]])

if __name__ == "__main__":
    unittest.main(verbosity=2)
