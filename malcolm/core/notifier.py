from contextlib import contextmanager

from malcolm.core.serializable import serialize_object
from malcolm.core.loggable import Loggable
from malcolm.core.request import Subscribe, Unsubscribe, Get, Request


class Notifier(Loggable):
    """Object that can service callbacks on given endpoints"""

    def __init__(self, name, process, block):
        self.set_logger_name(name)
        self._process = process
        self._tree = NotifierNode(block)
        self._lock = process.create_lock()
        self._squashed_changes = None
        # {Subscribe.generator_key(): Subscribe}
        self._subscription_keys = {}

    def handle_request(self, request):
        """Handle a request from outside

        Args:
            request (Request): Request to respond to
        """
        with self._lock:
            try:
                if isinstance(request, Subscribe):
                    self._tree.handle_subscribe(request, request.path[1:])
                    self._subscription_keys[request.generate_key()] = request
                elif isinstance(request, Unsubscribe):
                    subscribe = self._subscription_keys[request.generate_key()]
                    self._tree.handle_unsubscribe(subscribe, subscribe.path[1:])
                elif isinstance(request, Get):
                    data = self._tree.data
                    for p in request.path:
                        data = getattr(data, p)
                    serialized = serialize_object(data)
                    request.respond_with_return(serialized)
                else:
                    request.respond_with_error("Bad request %s" % request)
            except Exception as e:
                self.log_exception("Exception when handling %s", request)
                request.respond_with_error(e)

    @contextmanager
    def changes_squashed(self):
        """Context manager to allow multiple calls to notify_change() to be
        made and all changes squashed into one consistent set. E.g:

        with notifier.changes_squashed:
            attr.set_value(1)
            attr.set_alarm(MINOR)
        """
        with self._lock:
            assert self._squashed_changes is None, "Already squashing changes"
            self._squashed_changes = []
            yield
            changes = self._squashed_changes
            self._squashed_changes = None
            self._tree.notify_changes(changes)

    def notify_change(self, path, data=None):
        """Notify of a single change made

        Args:
            path (list): The path of what has changed
            data (object): The new data, None for deletion
        """
        with self._lock:
            if data is None:
                change = [path]
            else:
                change = [path, data]
            if self._squashed_changes is None:
                self._tree.notify_changes([change])
            else:
                self._squashed_changes.append(change)


class NotifierNode(object):

    # Define slots so it uses less resources to make these
    __slots__ = ["requests", "children", "parent", "data"]

    def __init__(self, data, parent=None):
        # [Subscribe]
        self.requests = []
        # {name: NotifierNode}
        self.children = {}
        # Leaf
        self.parent = parent
        # object
        self.data = data

    def notify_changes(self, changes):
        """Set our data and notify anyone listening

        Args:
            changes (list): [[path, optional data]] where path is the path to
                what has changed, and data is the unserialized object that has
                changed
        """
        child_changes = {}
        for change in changes:
            path = change[0]
            if path:
                # This is for one of our children
                name = path[0]
                if name in self.children:
                    if len(change) == 2:
                        child_change = [path[1:], change[1]]
                    else:
                        child_change = [path[1:]]
                    child_changes.setdefault(name, []).append(child_change)
            else:
                # This is for us
                if len(change) == 2:
                    child_change_dict = self._update_data(change[1])
                else:
                    child_change_dict = self._update_data(None)
                for name, child_change in child_change_dict.items():
                    child_changes.setdefault(name, []).append(child_change)
        # If we have subscribers, serialize at this level
        if self.requests:
            for request in self.requests:
                if request.delta:
                    for change in changes:
                        change[-1] = serialize_object(change[-1])
                    request.respond_with_delta(changes)
                else:
                    request.respond_with_update(serialize_object(self.data))
        # Now notify our children
        for name, child_changes in child_changes.items():
            self.children[name].notify_changes(child_changes)

    def _update_data(self, data):
        """Set our data and notify any subscribers of children what has changed

        Args:
            data (object): The new data

        Returns:
            dict: {child_name: [path_list, optional child_data]} of the change
                that needs to be passed to a child as a result of this
        """
        self.data = data
        child_change_dict = {}
        # Reflect change of data to children
        for name in self.children:
            child_data = getattr(data, name, None)
            if child_data is None:
                # Deletion
                child_change_dict[name] = [[]]
            else:
                # Change
                child_change_dict[name] = [[], child_data]
        return child_change_dict

    def handle_subscribe(self, request, path):
        """Add to the list of request to notify, and notify the initial value of
        the data held

        Args:
            request (Subscribe): The subscribe request
            path (list): The relative path from ourself
        """
        if path:
            # Recurse down
            name = path[0]
            if name not in self.children:
                self.children[name] = NotifierNode(
                    getattr(self.data, name, None), self)
            self.children[name].handle_subscribe(request, path[1:])
        else:
            # This is for us
            self.requests.append(request)
            serialized = serialize_object(self.data)
            if request.delta:
                request.respond_with_delta([[[], serialized]])
            else:
                request.respond_with_update(serialized)

    def handle_unsubscribe(self, request, path):
        """Remove from the notifier list and send a return

        Args:
            request (Subscribe): The original subscribe request

        Returns:
            bool: True if we are ampty and should be deleted from parent
        """
        if path:
            # Recurse down
            name = path[0]
            delete = self.children[name].handle_unsubscribe(request, path[1:])
            if delete:
                del self.children[name]
        else:
            # This is for us
            self.requests.remove(request)
            request.respond_with_return()
        if self.children or self.requests:
            should_delete = False
        else:
            should_delete = True
        return should_delete