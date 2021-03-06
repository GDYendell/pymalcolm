import time

from malcolm.core import REQUIRED, method_takes
from malcolm.core.vmetas import PointGeneratorMeta, StringArrayMeta, NumberMeta
from malcolm.parts.builtin.childpart import ChildPart
from malcolm.controllers.runnablecontroller import RunnableController


class ScanTickerPart(ChildPart):
    # Generator instance
    generator = None
    # Where to start
    completed_steps = None
    # How many steps to do
    steps_to_do = None
    # When to blow up
    exception_step = None

    @RunnableController.Configure
    @RunnableController.PostRunReady
    @RunnableController.Seek
    @method_takes(
        "generator", PointGeneratorMeta("Generator instance"), REQUIRED,
        "axesToMove", StringArrayMeta(
            "List of axes in inner dimension of generator that should be moved"
        ), REQUIRED,
        "exceptionStep", NumberMeta(
            "int32", "If >0, raise an exception at the end of this step"), 0)
    def configure(self, task, completed_steps, steps_to_do, part_info, params):
        # If we are being asked to move
        if self.name in params.axesToMove:
            # Just store the generator and place we need to start
            self.generator = params.generator
            self.completed_steps = completed_steps
            self.steps_to_do = steps_to_do
            self.exception_step = params.exceptionStep
        else:
            # Flag nothing to do
            self.generator = None

    @RunnableController.Run
    @RunnableController.Resume
    def run(self, task, update_completed_steps):
        # Start time so everything is relative
        point_time = time.time()
        if self.generator:
            for i in range(self.completed_steps,
                           self.completed_steps + self.steps_to_do):
                # Get the point we are meant to be scanning
                point = self.generator.get_point(i)
                # Update the child counter to be the demand position
                position = point.positions[self.name]
                task.put(self.child["counter"], position)
                # Wait until the next point is due
                point_time += point.duration
                wait_time = point_time - time.time()
                task.sleep(wait_time)
                # Update the point as being complete
                update_completed_steps(i + 1, self)
                # If this is the exception step then blow up
                assert i +1 != self.exception_step, \
                    "Raising exception at step %s" % self.exception_step
