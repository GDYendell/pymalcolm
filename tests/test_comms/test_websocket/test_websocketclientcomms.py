import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
import setup_malcolm_paths

import unittest
from mock import MagicMock, patch, call

from malcolm.compat import OrderedDict
from malcolm.comms.websocket import WebsocketClientComms
from malcolm.core.response import Response

params = dict(hostname="test", port=1)


class TestWSClientComms(unittest.TestCase):

    def setUp(self):
        self.p = MagicMock()

    @patch('malcolm.comms.websocket.websocketclientcomms.IOLoop')
    def test_init(self, ioloop_mock):
        self.WS = WebsocketClientComms(self.p, params)
        self.assertEqual(self.p, self.WS.process)
        self.assertEqual("ws://test:1/ws", self.WS.url)
        self.assertEqual(ioloop_mock.current(), self.WS.loop)
        self.WS.loop.add_callback.assert_called_once_with(
            self.WS.recv_loop)

    @patch('malcolm.comms.websocket.websocketclientcomms.IOLoop')
    def test_subscribe_initial(self, _):
        self.WS = WebsocketClientComms(self.p, params)
        self.WS.send_to_server = MagicMock()
        self.WS.subscribe_server_blocks()
        self.assertEqual(self.WS.send_to_server.call_count, 1)
        request = self.WS.send_to_server.call_args[0][0]
        self.assertEqual(request.id, 0)
        self.assertEqual(request.typeid, "malcolm:core/Subscribe:1.0")
        self.assertEqual(request.endpoint, [".", "blocks", "value"])
        self.assertEqual(request.delta, False)

    @patch('malcolm.comms.websocket.websocketclientcomms.deserialize_object')
    @patch('malcolm.comms.websocket.websocketclientcomms.json')
    @patch('malcolm.comms.websocket.websocketclientcomms.IOLoop')
    def test_on_message(self, _, json_mock, deserialize_mock):
        self.WS = WebsocketClientComms(self.p, params)

        message_dict = dict(name="TestMessage")
        json_mock.loads.return_value = message_dict

        response = MagicMock()
        response.id = 1
        deserialize_mock.return_value = response
        request_mock = MagicMock()
        self.WS.requests[1] = request_mock

        self.WS.on_message("TestMessage")

        json_mock.loads.assert_called_once_with("TestMessage",
                                                object_pairs_hook=OrderedDict)
        deserialize_mock.assert_called_once_with(message_dict, Response)
        request_mock.response_queue.put.assert_called_once_with(response)

    @patch('malcolm.comms.websocket.websocketclientcomms.json')
    @patch('malcolm.comms.websocket.websocketclientcomms.IOLoop')
    def test_on_message_logs_exception(self, _, json_mock):
        self.WS = WebsocketClientComms(self.p, params)
        self.WS.log_exception = MagicMock()
        exception = Exception()
        json_mock.loads.side_effect = exception

        self.WS.on_message("test")

        self.WS.log_exception.assert_called_once_with(exception)

    @patch('malcolm.comms.websocket.websocketclientcomms.json')
    @patch('malcolm.comms.websocket.websocketclientcomms.IOLoop')
    def test_send_to_server(self, _, json_mock):
        self.WS = WebsocketClientComms(self.p, params)
        json_mock.reset_mock()
        result_mock = MagicMock()
        self.WS.conn = MagicMock()
        dumps_mock = MagicMock()
        json_mock.dumps.return_value = dumps_mock

        request_mock = MagicMock()
        self.WS.send_to_server(request_mock)

        json_mock.dumps.assert_called_once_with(request_mock.to_dict())
        self.WS.conn.write_message.assert_called_once_with(dumps_mock)

    @patch('malcolm.comms.websocket.websocketclientcomms.IOLoop')
    def test_start(self, ioloop_mock):
        loop_mock = MagicMock()
        ioloop_mock.current.return_value = loop_mock
        self.WS = WebsocketClientComms(self.p, params)
        self.WS.process.spawn = MagicMock()
        self.WS.start()

        self.assertEqual([call(self.WS.send_loop), call(self.WS.loop.start)],
                         self.WS.process.spawn.call_args_list)

    @patch('malcolm.comms.websocket.websocketclientcomms.IOLoop')
    def test_stop(self, ioloop_mock):
        loop_mock = MagicMock()
        ioloop_mock.current.return_value = loop_mock

        self.WS = WebsocketClientComms(self.p, params)
        self.WS.start()
        loop_mock.reset_mock()
        self.WS.stop()

        loop_mock.add_callback.assert_called_once_with(
            ioloop_mock.current().stop)
        self.WS.process.spawn.return_value.assert_not_called()

    @patch('malcolm.comms.websocket.websocketclientcomms.IOLoop')
    def test_wait(self, _):
        spawnable_mocks = [MagicMock(), MagicMock()]
        timeout = MagicMock()

        self.WS = WebsocketClientComms(self.p, params)
        self.WS.process.spawn = MagicMock(side_effect=spawnable_mocks)
        self.WS.start()
        self.WS.wait(timeout)

        spawnable_mocks[0].wait.assert_called_once_with(timeout=timeout)
        spawnable_mocks[1].wait.assert_called_once_with(timeout=timeout)

if __name__ == "__main__":
    unittest.main(verbosity=2)
