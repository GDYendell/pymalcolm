import functools
from collections import OrderedDict

from malcolm.core.loggable import Loggable
from malcolm.core.attribute import Attribute
from malcolm.core.hook import Hook
from malcolm.core.methodmeta import takes, only_in, MethodMeta, \
    get_method_decorated
from malcolm.core.blockmeta import BlockMeta
from malcolm.core.vmetas import BooleanMeta, ChoiceMeta, StringMeta
from malcolm.core.statemachine import DefaultStateMachine
from malcolm.core.block import Block


sm = DefaultStateMachine


@sm.insert
class Controller(Loggable):
    """Implement the logic that takes a Block through its state machine"""

    Resetting = Hook()

    def __init__(self, block_name, process, parts=None, params=None):
        """
        Args:
            process (Process): The process this should run under
        """
        self.block = Block()
        self.params = params
        self.process = process
        self.lock = process.create_lock()
        # dictionary of dictionaries
        # {state (str): {MethodMeta: writeable (bool)}
        self.methods_writeable = {}
        if parts is None:
            parts = []
        self.parts = parts

        self.set_logger_name("%s(%s)" % (type(self).__name__, block_name))
        self._set_block_children()
        self.block.set_parent(process, block_name)
        process.add_block(self.block)

    def add_change(self, changes, item, attr, value):
        path = [attr]
        while item is not self.block:
            path.insert(0, item.name)
            item = item.parent
        changes.append([path, value])

    def _set_block_children(self):
        # reconfigure block with new children
        child_list = [self.create_meta()]
        child_list += list(self._create_default_attributes())
        child_list += list(self.create_attributes())
        child_list += list(self.create_methods())
        for part in self.parts:
            child_list += list(part.create_attributes())
            child_list += list(part.create_methods())

        self.methods_writeable = {}
        writeable_functions = {}
        children = OrderedDict()

        for name, child, writeable_func in child_list:
            if isinstance(child, MethodMeta):
                # Set if the method is writeable
                if child.only_in is None:
                    states = [
                        state for state in self.stateMachine.possible_states
                        if state != sm.DISABLED]
                else:
                    states = child.only_in
                    for state in states:
                        assert state in self.stateMachine.possible_states, \
                            "State %s is not one of the valid states %s" % \
                            (state, self.stateMachine.possible_states)
                self.register_method_writeable(child, states)
            children[name] = child
            if writeable_func:
                writeable_functions[name] = functools.partial(
                    self.call_writeable_function, writeable_func)

        self.block.set_children(children, writeable_functions)

    def call_writeable_function(self, function, child, *args):
        with self.lock:
            assert child.writeable, \
                "Child %r is not writeable" % (child,)
        result = function(*args)
        return result

    def _create_default_attributes(self):
        # Add the state, status and busy attributes
        self.state = Attribute(
            ChoiceMeta("State of Block", self.stateMachine.possible_states),
            self.stateMachine.DISABLED)
        yield ("state", self.state, None)
        self.status = Attribute(StringMeta("Status of Block"), "Disabled")
        yield ("status", self.status, None)
        self.busy = Attribute(BooleanMeta("Whether Block busy or not"), False)
        yield ("busy", self.busy, None)

    def create_meta(self):
        self.meta = BlockMeta()
        return "meta", self.meta, None

    def create_attributes(self):
        """Method that should provide Attribute instances for Block

        Yields:
            tuple: (string name, Attribute, callable put_function).
        """
        return iter(())

    def create_methods(self):
        """Method that should provide MethodMeta instances for Block

        Yields:
            tuple: (string name, MethodMeta, callable post_function).
        """
        return get_method_decorated(self)

    def transition(self, state, message):
        """
        Change to a new state if the transition is allowed

        Args:
            state(str): State to transition to
            message(str): Status message
        """
        with self.lock:
            if self.stateMachine.is_allowed(
                    initial_state=self.state.value, target_state=state):

                # transition is allowed, so set attributes
                changes = []
                self.add_change(changes, self.state, "value", state)
                self.add_change(changes, self.status, "value", message)
                self.add_change(changes, self.busy, "value",
                                state in self.stateMachine.busy_states)

                # say which methods can now be called
                for child in self.block.children.values():
                    if isinstance(child, MethodMeta):
                        writeable = self.methods_writeable[state][child]
                        self.set_method_writeable(changes, child, writeable)

                self.block.apply_changes(*changes)
            else:
                raise TypeError("Cannot transition from %s to %s" %
                                (self.state.value, state))

    def set_method_writeable(self, changes, method, writeable):
        self.add_change(changes, method, "writeable", writeable)
        for meta in method.takes.elements.values():
            self.add_change(changes, meta, "writeable", writeable)

    def register_method_writeable(self, method, states):
        """
        Set the states that the given method can be called in

        Args:
            method(MethodMeta): Method that will be set writeable or not
            states(list[str]): List of states where method is writeable
        """
        for state in self.stateMachine.possible_states:
            writeable_dict = self.methods_writeable.setdefault(state, {})
            is_writeable = state in states
            writeable_dict[method] = is_writeable

    @takes()
    def disable(self):
        self.transition(sm.DISABLED, "Disabled")

    @takes()
    @only_in(sm.DISABLED, sm.FAULT)
    def reset(self):
        try:
            self.transition(sm.RESETTING, "Resetting")
            self.Resetting.run(self)
            self.transition(sm.AFTER_RESETTING, "Done resetting")
        except Exception as e:
            self.log_exception("Fault occurred while Resetting")
            self.transition(sm.FAULT, str(e))
