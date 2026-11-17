import os
import threading
import time

import pytest

from app.jobs import JobForm, JobStore, Queue

FORM = JobForm(dev=53, test=54, title="Contoh Fitur")


def wait(cond, t=5):
    end = time.time() + t
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_create_and_status(tmp_path):
    s = JobStore(tmp_path)
    jid = s.create(FORM)
    assert len(jid) == 12 and int(jid, 16) >= 0
    assert s.dir(jid).is_dir()
    st = s.status(jid)
    assert st["state"] == "queued" and st["error"] is None and st["queue_pos"] == 0
    s.set_status(jid, state="running", stage="Analisa")
    assert JobStore(tmp_path).status(jid)["stage"] == "Analisa"


@pytest.mark.parametrize("bad", ["../x", "abc", "G" * 12, "A" * 12, "a" * 13, ""])
def test_invalid_id(tmp_path, bad):
    s = JobStore(tmp_path)
    with pytest.raises(ValueError):
        s.dir(bad)
    with pytest.raises(ValueError):
        s.status(bad)


def test_purge(tmp_path):
    s = JobStore(tmp_path)
    old, new = s.create(FORM), s.create(FORM)
    past = time.time() - 1000
    os.utime(s.dir(old), (past, past))
    s.purge(older_than_seconds=500)
    assert not s.dir(old).exists() and s.dir(new).exists()


def test_queue_sequential(tmp_path):
    s = JobStore(tmp_path)
    q = Queue(s)
    a, b = s.create(FORM), s.create(FORM)
    go, started, order = threading.Event(), threading.Event(), []

    def fa():
        order.append("a")
        started.set()
        go.wait(5)

    q.submit(a, fa)
    assert started.wait(5)
    q.submit(b, lambda: order.append("b"))
    assert s.status(b)["queue_pos"] == 1
    assert order == ["a"]
    go.set()
    assert wait(lambda: order == ["a", "b"])
    assert wait(lambda: s.status(b)["queue_pos"] == 0)


def test_queue_marks_failed_on_exception(tmp_path):
    s = JobStore(tmp_path)
    q = Queue(s)
    a, b = s.create(FORM), s.create(FORM)

    def boom():
        raise RuntimeError("meledak")

    q.submit(a, boom)
    q.submit(b, lambda: s.set_status(b, state="done"))
    assert wait(lambda: s.status(a)["state"] == "failed")
    assert "meledak" not in s.status(a)["error"]  # teks exception tidak bocor ke UI
    assert "RuntimeError" in s.status(a)["error"]
    assert wait(lambda: s.status(b)["state"] == "done")  # worker tetap hidup
