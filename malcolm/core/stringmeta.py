from malcolm.core.attributemeta import AttributeMeta


class StringMeta(AttributeMeta):
    """Meta object containing information for a string"""

    def __init__(self, name):
        super(StringMeta, self).__init__(name=name)

    def validate(self, value):
        """
        Check if the value is None and returns None, else casts value to a
        string and returns it

        Args:
            value: Value to validate

        Returns:
            str: Value as a string [If value is not None]
        """

        if value is None:
            return None
        else:
            return str(value)

    def to_dict(self):
        """Convert object attributes into a dictionary"""

        d = super(StringMeta, self).to_dict()

        return d
