from time import sleep

from sekoia_automation.timer import RepeatedTimer


def test_timer():
    a = 0

    def timed():
        nonlocal a
        a += 1

    timer = RepeatedTimer(0.1, timed)
    timer.start()

    assert timer.is_running is True
    sleep(0.15)
    assert a == 1

    # Check stop
    timer.stop()
    assert timer.is_running is False
