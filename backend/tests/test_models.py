"""Pruebas unitarias sin dependencias de infraestructura."""

from datetime import date
import unittest

from app.main import TaskInput


class TaskModelTests(unittest.TestCase):
    def test_due_date_accepts_and_serializes_the_public_alias(self) -> None:
        task = TaskInput(title="Probar estructura", dueDate="2026-08-10")

        self.assertEqual(task.due_date, date(2026, 8, 10))
        self.assertEqual(task.model_dump(by_alias=True)["dueDate"], date(2026, 8, 10))
