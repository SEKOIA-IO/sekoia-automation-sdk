from threading import Event, Thread


class Worker(Thread):
    """
    Represent a task to execute in a connector
    """

    KIND = "worker"

    def __init__(self):
        super().__init__()
        # Flag to indicate if the worker is still running
        self._stop_event = Event()

    def stop(self):
        """
        Stop the worker
        """
        self._stop_event.set()

    @property
    def is_running(self):
        """
        Indicate if the worker is still running
        """
        return not self._stop_event.is_set()


class Workers(list[Worker]):
    """
    Represents a group of tasks.
    """

    def __init__(self, worker_class: type[Worker], *positional_args, **keyword_args):
        self.worker_class = worker_class
        self.positional_args = positional_args
        self.keyword_args = keyword_args

    @classmethod
    def create(cls, nb_workers: int, worker_class: type[Worker], *args, **kwargs):
        """
        Create a new group of workers

        :param int nb_workers: The number of workers to create
        :param type worker_class: The class of the worker to create
        """
        # initialize the list
        workers = cls(worker_class, *args, **kwargs)

        # create the workers
        for _ in range(nb_workers):
            workers.append(worker_class(*args, **kwargs))

        return workers

    def supervise(self):
        """
        Supervise the workers. Detect dead ones and relaunch them
        """
        for index in range(len(self)):
            if not self[index].is_alive() and self[index].is_running:
                self[index] = self.worker_class(
                    *self.positional_args, **self.keyword_args
                )
                self[index].start()

    def start(self):
        """
        Start all workers
        """
        for worker in self:
            worker.start()

    def stop(self, timeout_per_worker: int | None = None):
        """
        Stop all workers

        :param int or None timeout_per_worker: The delay, per worker,
                                               before raising a timeout
        """

        for worker in self:
            if worker.is_alive():
                worker.stop()

        for worker in self:
            worker.join(timeout=timeout_per_worker)
