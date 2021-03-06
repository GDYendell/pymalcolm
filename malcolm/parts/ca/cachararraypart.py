from malcolm.core.vmetas import StringMeta
from malcolm.parts.ca.capart import CAPart


class CACharArrayPart(CAPart):
    """Defines a part which connects to a pv via channel access DBR_CHAR_STR"""

    def create_meta(self, description, tags):
        return StringMeta(description=description, tags=tags)

    def get_datatype(self):
        return self.catools.DBR_CHAR_STR

    def format_caput_value(self, value):
        self.log_info("caput -c -w 1000 -S %s %r", self.params.pv, value)
        return value
