from unittest.mock import Mock, patch

from sekoia_automation.connector.workers import Worker, Workers


def test_stop_worker():
    worker = Worker()
    assert worker.is_running is True

    worker.stop()
    assert worker.is_running is False


def test_create_workers():
    nb_workers = 6
    workers = Workers.create(nb_workers, Worker)
    assert len(workers) == nb_workers


def test_start_workers():
    worker1 = Mock()
    worker2 = Mock()
    worker3 = Mock()
    workers = Workers(Worker)
    workers.extend([worker1, worker2, worker3])

    workers.start()
    assert worker1.start.called
    assert worker2.start.called
    assert worker3.start.called


def test_stop_workers():
    worker1 = Mock()
    worker1.is_alive.return_value = True
    worker2 = Mock()
    worker2.is_alive.return_value = False
    worker3 = Mock()
    worker3.is_alive.return_value = True
    workers = Workers(Worker)
    workers.extend([worker1, worker2, worker3])

    workers.stop()
    assert worker1.stop.called
    assert not worker2.stop.called
    assert worker3.stop.called


def test_supervise_workers():
    with patch.object(Worker, "start") as mock_start:
        worker1 = Mock()
        worker1.is_alive.return_value = False
        worker2 = Mock()
        worker2.is_alive.return_value = True
        worker3 = Mock()
        worker3.is_alive.return_value = False
        workers = Workers(Worker)
        workers.extend([worker1, worker2, worker3])

        workers.supervise()
        assert mock_start.call_count == 2
