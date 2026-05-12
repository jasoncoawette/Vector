from __future__ import annotations

from pathlib import Path

import pytest

from vector.store import connect
from vector.store import tasks as tasks_repo


@pytest.fixture()
def conn(tmp_path: Path):
    c = connect(tmp_path / "vector.db")
    yield c
    c.close()


def test_upsert_inserts_new(conn):
    tid = tasks_repo.upsert(
        conn,
        external_id="LIN-1",
        title="Ship CLI",
        source="linear",
        tag="outcome",
        priority=1,
    )
    assert tid > 0
    out = tasks_repo.get(conn, tid)
    assert out is not None
    assert out.title == "Ship CLI"


def test_upsert_updates_existing(conn):
    a = tasks_repo.upsert(
        conn, external_id="LIN-1", title="Ship CLI", source="linear"
    )
    b = tasks_repo.upsert(
        conn, external_id="LIN-1", title="Ship CLI v2", source="linear", priority=1
    )
    assert a == b
    out = tasks_repo.get(conn, a)
    assert out.title == "Ship CLI v2"
    assert out.priority == 1


def test_list_open_excludes_shipped(conn):
    a = tasks_repo.upsert(conn, external_id="A", title="A", source="linear")
    b = tasks_repo.upsert(conn, external_id="B", title="B", source="linear")
    tasks_repo.mark_shipped(conn, a)
    open_ids = {t.id for t in tasks_repo.list_open(conn)}
    assert open_ids == {b}


def test_list_open_sorted_by_priority(conn):
    a = tasks_repo.upsert(conn, external_id="A", title="A", source="linear", priority=3)
    b = tasks_repo.upsert(conn, external_id="B", title="B", source="linear", priority=1)
    ids = [t.id for t in tasks_repo.list_open(conn)]
    assert ids == [b, a]
