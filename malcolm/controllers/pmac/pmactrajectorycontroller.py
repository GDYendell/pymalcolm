from collections import Counter, OrderedDict

from malcolm.controllers.builtin.managercontroller import ManagerController
from malcolm.core import Hook, Table
from malcolm.core.vmetas import NumberArrayMeta, TableMeta

# velocity modes
PREV_TO_NEXT = 0
PREV_TO_CURRENT = 1
CURRENT_TO_NEXT = 2
ZERO_VELOCITY = 3

# user programs
NO_PROGRAM = 0       # Do nothing
TRIG_CAPTURE = 4     # Capture 1, Frame 0, Detector 0
TRIG_DEAD_FRAME = 2  # Capture 0, Frame 1, Detector 0
TRIG_LIVE_FRAME = 3  # Capture 0, Frame 1, Detector 1
TRIG_ZERO = 8        # Capture 0, Frame 0, Detector 0

cs_axis_names = list("ABCUVWXYZ")

columns = OrderedDict(
    time=NumberArrayMeta("float64", "Time in ms to spend getting to point"))
columns["velocity_mode"] = NumberArrayMeta("uint8", "Velocity mode for point")
columns["user_programs"] = NumberArrayMeta("uint8", "User program for point")

for axis in cs_axis_names:
    columns[axis] = NumberArrayMeta(
        "float64", "Position of %s at this point" % axis)
profile_table = TableMeta("Profile time and velocity arrays", columns=columns)

sm = ManagerController.stateMachine


class PMACTrajectoryController(ManagerController):
    ReportCSInfo = Hook()
    BuildProfile = Hook()
    RunProfile = Hook()
    axis_mapping = None
    cs_port = None
    points_built = 0
    completed_steps = None

    def do_validate(self, params):
        self.get_cs_port(params.axes_to_move)
        return params

    def get_cs_port(self, axes_to_move):
        # Get the cs number of these axes
        cs_info_d = self.run_hook(self.ReportCSInfo, self.create_part_tasks())
        cs_ports = set()
        # dict {name: cs_type}
        axis_mapping = {}
        for part_name, report_d in list(cs_info_d.items()):
            if part_name in axes_to_move:
                assert report_d.cs_axis in cs_axis_names, \
                    "Can only scan 1-1 mappings, %r is %r" % \
                    (part_name, report_d.cs_axis)
                cs_ports.add(report_d.cs_port)
                axis_mapping[part_name] = report_d.cs_axis
        missing = set(axes_to_move) - set(axis_mapping)
        assert not missing, \
            "Some scannables %s are not children of this controller" % missing
        assert len(cs_ports) == 1, \
            "Requested axes %s are in multiple CS numbers %s" % (
                axes_to_move, list(cs_ports))
        cs_axis_counts = Counter(axis_mapping.values())
        # Any cs_axis defs that are used for more that one raw motor
        overlap = [k for k, v in cs_axis_counts.items() if v > 1]
        assert not overlap, \
            "CS axis defs %s have more that one raw motor attached" % overlap
        return cs_ports.pop(), axis_mapping

    def do_configure(self, part_tasks, params, start_index=0):
        self.cs_port, self.axis_mapping = self.get_cs_port(params.axes_to_move)
        self.build_start_profile(part_tasks, start_index)
        self.run_hook(self.RunProfile, part_tasks)
        self.points_built, self.completed_steps = self.build_generator_profile(
            part_tasks, start_index)

    def do_run(self, part_tasks):
        self.transition(sm.RUNNING, "Waiting for scan to complete")
        self.run_hook(self.RunProfile, part_tasks,
                      completed_steps=self.completed_steps)
        more_to_do = self.points_built < self.totalSteps.value - 1
        if more_to_do:
            self.transition(sm.POSTRUN, "Building next stage")
            self.points_built, self.completed_steps = \
                self.build_generator_profile(part_tasks, self.points_built)
            return self.stateMachine.READY
        else:
            self.transition(sm.POSTRUN, "Finishing run")
            return self.stateMachine.IDLE

    def run_up_positions(self, point, fraction):
        """Generate a dict of axis positions at start of run up

        Args:
            point (Point): The first point of the scan
            fraction (float): The fraction of the Point exposure time that the
                run up move should take
        """
        positions = {}

        for axis_name in self.axis_mapping:
            full_distance = point.upper[axis_name] - point.lower[axis_name]
            run_up = full_distance * fraction
            positions[axis_name] = run_up

        return positions

    def calculate_acceleration_time(self):
        acceleration_time = 0
        for axis_name in self.axis_mapping:
            part = self.parts[axis_name]
            acceleration_time = max(
                acceleration_time, part.get_acceleration_time())
        return acceleration_time

    def build_start_profile(self, part_tasks, start_index):
        """Move to the run up position ready to start the scan"""
        acceleration_time = self.calculate_acceleration_time()
        fraction = acceleration_time / self.configure_params.exposure
        first_point = self.get_point(start_index)
        trajectory = {}
        move_time = 0

        for axis_name, run_up in \
                self.run_up_positions(first_point, fraction).items():
            start_pos = first_point.lower[axis_name] - run_up
            trajectory[axis_name] = [start_pos]
            part = self.parts[axis_name]
            move_time = max(move_time, part.get_move_time(start_pos))

        # if we are spending any time at max_velocity, put in points at
        # the acceleration times
        if move_time > 2 * acceleration_time:
            time_array = [acceleration_time, move_time - acceleration_time,
                          move_time]
            velocity_mode = [CURRENT_TO_NEXT, PREV_TO_CURRENT, ZERO_VELOCITY]
            user_programs = [NO_PROGRAM, NO_PROGRAM, NO_PROGRAM]
            for axis_name, positions in trajectory.items():
                part = self.parts[axis_name]
                # TODO: move this to the trajectory when current pos is reported
                current = part.child.position
                accl_dist = acceleration_time * part.child.max_velocity / 2
                start_pos = positions[0]
                if current > start_pos:
                    # backwards
                    accl_dist = - accl_dist
                positions.insert(0, current + accl_dist)
                positions.insert(1, start_pos - accl_dist)
        else:
            time_array = [move_time]
            velocity_mode = [ZERO_VELOCITY]
            user_programs = [NO_PROGRAM]

        self.build_profile(part_tasks, time_array, velocity_mode, trajectory,
                           user_programs)

    def build_profile(self, part_tasks, time_array, velocity_mode, trajectory,
                      user_programs):
        """Build profile using part_tasks

        Args:
            time_array (list): List of times in ms
            velocity_mode (list): List of velocity modes like PREV_TO_NEXT
            trajectory (dict): {axis_name: [positions in EGUs]}
            part_tasks (dict): {part: task}
            user_programs (list): List of user programs like TRIG_LIVE_FRAME
        """
        profile = Table(profile_table)
        profile.time = time_array
        profile.velocity_mode = velocity_mode
        profile.user_programs = user_programs
        use = []
        resolutions = []
        offsets = []

        for axis_name in trajectory:
            cs_axis = self.axis_mapping[axis_name]
            profile[cs_axis] = trajectory[axis_name]
            use.append(cs_axis)
            resolutions.append(self.parts[axis_name].get_resolution())
            offsets.append(self.parts[axis_name].get_offset())

        for cs_axis in cs_axis_names:
            if cs_axis not in use:
                profile[cs_axis] = [0] * len(time_array)

        self.run_hook(self.BuildProfile, part_tasks, profile=profile,
                      use=use, resolutions=resolutions, offsets=offsets)

    def build_generator_profile(self, part_tasks, start_index=0):
        acceleration_time = self.calculate_acceleration_time()
        fraction = acceleration_time / self.configure_params.exposure
        trajectory = {}
        time_array = []
        velocity_mode = []
        user_programs = []
        completed_steps = []
        last_point = None

        for i in range(start_index, self.totalSteps.value):
            point = self.get_point(i)

            # Check that none of the external motors need moving
            if last_point and self.external_axis_has_moved(last_point, point):
                break

            # Check if we need to insert the lower bound point
            if last_point is None:
                lower_move_time = acceleration_time
            else:
                lower_move_time = self.need_lower_move_time(last_point, point)

            if lower_move_time:
                if velocity_mode:
                    # set the previous point to not take this point into account
                    velocity_mode[-1] = PREV_TO_CURRENT
                    # and tell it that this was an empty frame
                    user_programs[-1] = TRIG_DEAD_FRAME

                # Add lower bound
                time_array.append(lower_move_time)
                velocity_mode.append(CURRENT_TO_NEXT)
                user_programs.append(TRIG_LIVE_FRAME)
                completed_steps.append(i)

            # Add position
            time_array.append(self.configure_params.exposure / 2.0)
            velocity_mode.append(PREV_TO_NEXT)
            user_programs.append(TRIG_CAPTURE)
            completed_steps.append(i)

            # Add upper bound
            time_array.append(self.configure_params.exposure / 2.0)
            velocity_mode.append(PREV_TO_NEXT)
            user_programs.append(TRIG_LIVE_FRAME)
            completed_steps.append(i + 1)

            # Add the axis positions
            for axis_name, cs_def in self.axis_mapping.items():
                positions = trajectory.setdefault(axis_name, [])
                # Add lower bound axis positions
                if lower_move_time:
                    positions.append(point.lower[axis_name])
                positions.append(point.positions[axis_name])
                positions.append(point.upper[axis_name])
            last_point = point

        # Add the last point
        time_array.append(acceleration_time)
        velocity_mode.append(ZERO_VELOCITY)
        user_programs.append(TRIG_ZERO)
        if i + 1 < self.totalSteps.value:
            # We broke, so don't add i + 1 to current step
            completed_steps.append(i)
        else:
            completed_steps.append(i + 1)

        # Add a tail off position
        for axis_name, tail_off in \
                self.run_up_positions(last_point, fraction).items():
            positions = trajectory[axis_name]
            positions.append(positions[-1] + tail_off)

        self.build_profile(part_tasks, time_array, velocity_mode, trajectory,
                           user_programs)
        return i, completed_steps

    def need_lower_move_time(self, last_point, point):
        # First point needs to insert lower bound point
        lower_move_time = 0
        for axis_name, cs_def in self.axis_mapping.items():
            if last_point.upper[axis_name] != point.lower[axis_name]:
                # axis needs to move during turnaround, so insert lower bound
                move_time = self.parts[axis_name].get_move_time(
                    last_point.upper[axis_name], point.lower[axis_name])
                lower_move_time = max(lower_move_time, move_time)
            else:
                # axis has been moving
                direction = last_point.upper[axis_name] - \
                            last_point.lower[axis_name]
                new_direction = point.upper[axis_name] - point.lower[axis_name]
                if (direction > 0 and new_direction < 0) or \
                        (direction < 0 and new_direction > 0):
                    move_time = self.parts[axis_name].get_acceleration_time() * 2
                    lower_move_time = max(lower_move_time, move_time)
        return lower_move_time

    def external_axis_has_moved(self, last_point, point):
        for axis_name in self.configure_params.generator.position_units:
            if axis_name not in self.axis_mapping:
                # Check it hasn't needed to move
                if point.positions[axis_name] != \
                        last_point.positions[axis_name]:
                    return True
        return False
