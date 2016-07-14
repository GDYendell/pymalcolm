from collections import OrderedDict

from malcolm.core.notifier import Notifier
from malcolm.core.serializable import Serializable


@Serializable.register_subclass("epics:nt/NTAttribute:1.0")
class Attribute(Notifier):
    """Represents a value with type information that may be backed elsewhere"""

    endpoints = ["value", "meta"]

    def __init__(self, name, meta):
        super(Attribute, self).__init__(name)
        if meta.name != "meta":
            raise ValueError(
                "Meta name must be 'meta' to be added to an Attribute")
        self.meta = meta
        self.value = None
        self.put_func = None

    def set_put_function(self, func):
        self.put_func = func

    def put(self, value):
        """Call the put function with the given value"""
        self.put_func(value)

    def set_value(self, value, notify=True):
        self.value = self.meta.validate(value)
        self.on_changed([["value"], self.value], notify)

    def to_dict(self):
        """Create ordered dictionary representing class instance"""
        return super(Attribute, self).to_dict(meta=self.meta.to_dict())

    @classmethod
    def from_dict(cls, name, d):
        """Create an Attribute instance from a serialized version of itself

        Args:
            name (str): Attribute instance name
            d (dict): Output of self.to_dict()
        """
        meta = Serializable.deserialize("meta", d["meta"])
        attribute = cls(name, meta)
        attribute.value = d["value"]
        return attribute
