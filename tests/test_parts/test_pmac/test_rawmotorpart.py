import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
import setup_malcolm_paths

import unittest
from mock import Mock, MagicMock

from malcolm.parts.pmac.rawmotorpart import RawMotorPart


class TestRawMotorPart(unittest.TestCase):

    def setUp(self):
        self.process = MagicMock()
        self.child = MagicMock()
        self.child.maxVelocity = 5.0
        self.child.accelerationTime = 0.5
        self.params = MagicMock()
        self.process.get_block.return_value = self.child
        self.c = RawMotorPart(self.process, self.params)

    def test_report(self):
        returns = self.c.report_cs_info(MagicMock())[0]
        self.assertEqual(returns.cs_axis, self.child.csAxis)
        self.assertEqual(returns.cs_port, self.child.csPort)
        self.assertEqual(returns.acceleration, 10.0)
        self.assertEqual(returns.resolution, self.child.resolution)
        self.assertEqual(returns.offset, self.child.offset)
        self.assertEqual(returns.max_velocity, self.child.maxVelocity)
        self.assertEqual(returns.current_position, self.child.position)
        self.assertEqual(returns.scannable, self.child.scannable)


if __name__ == "__main__":
    unittest.main(verbosity=2)
