import sqlite3
import pytest
from backend.audit_chain import migrate, append, verify


def database():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute(
        "CREATE TABLE audit(id INTEGER PRIMARY KEY,time TEXT,action TEXT,detail TEXT)"
    )
    c.execute("INSERT INTO audit VALUES(1,'UTC','legacy','{}')")
    c.commit()
    migrate(c)
    c.commit()
    return c


def test_legacy_migration_append_and_trigger_protection():
    c = database()
    assert verify(c)["valid"] and verify(c)["legacy_records_through"] == 1
    append(c, "UTC", "new", '{"source":"EV-1"}')
    c.commit()
    assert verify(c)["events_checked"] == 2 and verify(c)["valid"]
    for table in ("audit", "audit_chain", "audit_chain_migration"):
        with pytest.raises(sqlite3.IntegrityError):
            c.execute(f"DELETE FROM {table}")
        c.rollback()
    old = verify(c)["head_sha256"]
    migrate(c)
    c.commit()
    assert verify(c)["head_sha256"] == old


def test_tamper_detected_and_restart_never_rehashes_changed_history():
    c = database()
    append(c, "UTC", "next", "{}")
    c.commit()
    c.execute("DROP TRIGGER audit_deny_update")
    c.execute("UPDATE audit SET detail='altered' WHERE id=1")
    c.commit()
    assert not verify(c)["valid"]
    migrate(c)
    c.commit()
    assert not verify(c)["valid"] and len(verify(c)["issues"]) == 2


def test_deleted_tail_detected_and_append_refused_without_repair():
    c = database()
    append(c, "UTC", "next", "{}")
    c.commit()
    c.execute("DROP TRIGGER audit_deny_delete")
    c.execute("DELETE FROM audit WHERE id=2")
    c.commit()
    assert not verify(c)["valid"]
    with pytest.raises(RuntimeError):
        append(c, "UTC", "bad", "{}")
    c.rollback()
