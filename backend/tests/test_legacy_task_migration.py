"""Pruebas de seguridad para la importación única de SQLite a PostgreSQL."""

import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app import main


class FakeResult:
    def __init__(self, *, one=None, rows=None) -> None:
        self.one = one
        self.rows = rows or []

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.rows


class FakePostgresConnection:
    def __init__(self, known_owners: set[str]) -> None:
        self.known_owners = known_owners
        self.statements: list[tuple[str, tuple[object, ...] | None]] = []

    def execute(self, statement: str, parameters=None) -> FakeResult:
        self.statements.append((statement, parameters))
        if "SELECT 1 FROM application_migrations" in statement:
            return FakeResult()
        if "SELECT username FROM users" in statement:
            return FakeResult(rows=[(owner,) for owner in self.known_owners])
        return FakeResult()


class LegacyTaskMigrationTests(unittest.TestCase):
    def create_legacy_database(self, path: Path, owner: str = "admin") -> None:
        with closing(sqlite3.connect(path)) as connection:
            connection.execute(
                """
                CREATE TABLE tasks (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
                    priority TEXT NOT NULL, status TEXT NOT NULL, due_date TEXT NOT NULL,
                    owner TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO tasks (id, title, description, priority, status, due_date, owner)
                VALUES ('legacy-task', 'Tarea heredada', '', 'medium', 'todo', '2026-08-10', ?)
                """,
                (owner,),
            )
            connection.commit()

    def test_imports_task_and_records_migration(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "taskflow.db"
            self.create_legacy_database(database_path)
            connection = FakePostgresConnection({"admin"})

            with patch.object(main, "LEGACY_SQLITE_PATH", database_path):
                main.migrate_legacy_tasks(connection)

        statements = [statement for statement, _ in connection.statements]
        self.assertTrue(any("INSERT INTO tasks" in statement for statement in statements))
        self.assertTrue(any("INSERT INTO application_migrations" in statement for statement in statements))

    def test_rejects_tasks_with_an_unknown_owner_before_importing(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "taskflow.db"
            self.create_legacy_database(database_path, owner="missing-user")
            connection = FakePostgresConnection(set())

            with patch.object(main, "LEGACY_SQLITE_PATH", database_path):
                with self.assertRaisesRegex(RuntimeError, "missing-user"):
                    main.migrate_legacy_tasks(connection)

        statements = [statement for statement, _ in connection.statements]
        self.assertFalse(any("INSERT INTO tasks" in statement for statement in statements))
