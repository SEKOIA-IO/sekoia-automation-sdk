from threading import Event, Timer


class RepeatedTimer:
    """
    Execute the given function every `interval` seconds.
    """

    def __init__(self, interval, function):
        self._timer = None
        self.interval = interval
        self.function = function
        self.is_running = False
        self._stop = Event()

    def _run(self):
        self.function()
        self.is_running = False
        self.start()

    def start(self):
        if not self._stop.is_set() and not self.is_running:
            self._timer = Timer(self.interval, self._run)
            self._timer.start()
            self.is_running = True

    def stop(self):
        self._stop.set()
        if self._timer:
            self._timer.cancel()
        self.is_running = False
