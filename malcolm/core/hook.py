import inspect

from malcolm.core.task import Task


class Hook(object):

    def __call__(self, func):
        """
        Decorator function to add a Hook to a Part's function

        Args:
            func: Function to decorate with Hook

        Returns:
            Decorated function
        """

        func.Hook = self
        return func

    def run(self, controller):
        """
        Run all relevant functions for this Hook

        Args:
            controller(Controller): Controller who's parts' functions will be run
        """

        names = [n for n in dir(controller) if getattr(controller, n) is self]
        assert len(names) > 0, \
            "Hook is not in controller"
        assert len(names) == 1, \
            "Hook appears in controller multiple times as %s" % names

        task_queue = controller.process.create_queue()

        spawned_list = []
        active_tasks = []
        for pname, part in controller.parts.items():
            members = [value[1] for value in
                       inspect.getmembers(part, predicate=inspect.ismethod)]

            for function in members:
                if hasattr(function, "Hook") and function.Hook == self:
                    task = Task("%s.%s" % (names[0], pname), controller.process)
                    spawned_list.append(controller.process.spawn(
                        self._run_func, task_queue, function, task))
                    active_tasks.append(task)

        while active_tasks:
            task, response = task_queue.get()
            active_tasks.remove(task)

            if isinstance(response, Exception):
                for task in active_tasks:
                    task.stop()
                for spawned in spawned_list:
                    spawned.wait()

                raise response

    @staticmethod
    def _run_func(q, func, task):
        """
        Run a function and place the response or exception back on the queue

        Args:
            q(Queue): Queue to place response/exception raised on
            func: Function to run
            task(Task): Task to run function with
        """

        try:
            result = func(task)
        except Exception as e:  # pylint:disable=broad-except
            q.put((task, e))
        else:
            q.put((task, result))