"""Tests for autonomous database tooling (find_databases / query_database)."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from nexus.infrastructure.adapters.execution.extended_tools import (
    EXTENDED_HANDLERS,
    extended_builtin_tools,
)


def _make_sqlite(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE users (id INTEGER, name TEXT, role TEXT)")
    conn.executemany(
        "INSERT INTO users VALUES (?,?,?)",
        [(1, "alice", "admin"), (2, "bob", "dev")],
    )
    conn.commit()
    conn.close()


@pytest.mark.anyio
async def test_database_tools_registered():
    names = {t.id for t in extended_builtin_tools()}
    assert "find_databases" in names
    assert "query_database" in names
    assert "find_databases" in EXTENDED_HANDLERS
    assert "query_database" in EXTENDED_HANDLERS


@pytest.mark.anyio
async def test_find_databases_discovers_sqlite_files():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "store.db"
        _make_sqlite(db)
        result = await EXTENDED_HANDLERS["find_databases"]({"path": tmp})
        dbs = result["databases"]
        assert any(d["kind"] == "file" and d["engine"] == "sqlite" for d in dbs)
        assert any(Path(d["path"]).name == "store.db" for d in dbs)


@pytest.mark.anyio
async def test_find_databases_detects_configs():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / ".env").write_text("DATABASE_URL=sqlite:///x.db\n")
        (Path(tmp) / "docker-compose.yml").write_text("services:\n  postgres:\n    image: postgres\n")
        result = await EXTENDED_HANDLERS["find_databases"]({"path": tmp})
        kinds = {(d["kind"], d["engine"]) for d in result["databases"]}
        assert ("config", "env") in kinds
        assert ("config", "compose") in kinds


@pytest.mark.anyio
async def test_query_database_sqlite_list_tables_and_query():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "store.db"
        _make_sqlite(db)
        tables = await EXTENDED_HANDLERS["query_database"](
            {
                "type": "sqlite",
                "database": str(db),
                "mode": "list_tables",
            }
        )
        assert [t["name"] for t in tables["tables"]] == ["users"]

        rows = await EXTENDED_HANDLERS["query_database"](
            {
                "type": "sqlite",
                "database": str(db),
                "sql": "SELECT name, role FROM users",
            }
        )
        assert rows["row_count"] == 2
        assert rows["rows"][0]["name"] == "alice"
        assert rows["rows"][1]["role"] == "dev"


@pytest.mark.anyio
async def test_query_database_sqlite_read_only_by_default():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "store.db"
        _make_sqlite(db)
        result = await EXTENDED_HANDLERS["query_database"](
            {
                "type": "sqlite",
                "database": str(db),
                "sql": "DELETE FROM users",
            }
        )
        assert "read-only" in result.get("error", result.get("rows", ""))


@pytest.mark.anyio
async def test_query_database_missing_sqlite_file():
    result = await EXTENDED_HANDLERS["query_database"](
        {
            "type": "sqlite",
            "database": "C:/definitely/missing.db",
        }
    )
    assert "error" in result and "not found" in result["error"]


@pytest.mark.anyio
async def test_query_database_unsupported_engine():
    result = await EXTENDED_HANDLERS["query_database"]({"type": "mongo"})
    assert "unsupported" in result["error"]
