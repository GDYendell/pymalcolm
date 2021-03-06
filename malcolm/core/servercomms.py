from malcolm.core.loggable import Loggable
from malcolm.core.spawnable import Spawnable
from malcolm.core.response import Delta, Update
from malcolm.core.request import Unsubscribe


class ServerComms(Loggable, Spawnable):
    """Abstract class for dispatching requests to a process and responses to a
    client"""

    def __init__(self, process):
        self.process = process
        self.q = self.process.create_queue()
        self.add_spawn_function(self.send_loop,
                                self.make_default_stop_func(self.q))

    def send_loop(self):
        """Service self.q, sending responses to client"""
        while True:
            response = self.q.get()
            if response is Spawnable.STOP:
                break
            try:
                self.send_to_client(response)
            except Exception:  # pylint:disable=broad-except
                self.log_exception(
                    "Exception sending response %s", response.to_dict())

    def send_to_client(self, response):
        """Abstract method to dispatch response to a client

        Args:
            response (Response): The message to pass to the client
        """
        raise NotImplementedError(
            "Abstract method that must be implemented by deriving class")

    def send_to_process(self, request):
        """Send request to process"""
        self.process.q.put(request)

    def notify_closed_connection(self, response):
        """Let the process know not to send any more updates or deltas"""
        self.log_warning(
            "Response %s cannot be sent as connection closed", response)
        if isinstance(response, (Delta, Update)):
            request = Unsubscribe(response.context, self.q)
            request.set_id(response.id)
            self.send_to_process(request)
