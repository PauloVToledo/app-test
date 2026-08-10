"""Pruebas de integración del contrato HTTP contra PostgreSQL efímero."""

import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from app import main


class ApiContractTests(unittest.TestCase):
    """Verifica autenticación, rotación y aislamiento de datos por usuario."""

    password = "correct-horse-battery-staple"

    @classmethod
    def setUpClass(cls) -> None:
        cls.user_prefix = f"ci-{uuid4().hex[:12]}"
        cls.client_context = TestClient(main.app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.remove_test_data()
        finally:
            cls.client_context.__exit__(None, None, None)

    @classmethod
    def remove_test_data(cls) -> None:
        with main.get_postgres_connection() as connection:
            connection.execute("DELETE FROM tasks WHERE owner LIKE %s", (f"{cls.user_prefix}%",))
            connection.execute("DELETE FROM auth_sessions WHERE username LIKE %s", (f"{cls.user_prefix}%",))
            connection.execute("DELETE FROM users WHERE username LIKE %s", (f"{cls.user_prefix}%",))

    def setUp(self) -> None:
        self.remove_test_data()
        with main.auth_state_lock:
            main.login_requests.clear()
            main.failed_logins.clear()

    def create_user(self, suffix: str) -> str:
        username = f"{self.user_prefix}-{suffix}"
        password_hash, salt = main.hash_password(self.password)
        with main.get_postgres_connection() as connection:
            connection.execute(
                """
                INSERT INTO users (username, password_hash, salt, password_algorithm)
                VALUES (%s, %s, %s, 'argon2id')
                """,
                (username, password_hash, salt),
            )
        return username

    def login(self, username: str) -> dict[str, object]:
        response = self.client.post(
            "/api/auth/login",
            json={"username": username, "password": self.password},
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(set(payload), {"accessToken", "refreshToken", "tokenType", "expiresIn"})
        self.assertEqual(payload["tokenType"], "bearer")
        self.assertIsInstance(payload["expiresIn"], int)
        return payload

    @staticmethod
    def bearer(tokens: dict[str, object]) -> dict[str, str]:
        return {"Authorization": f"Bearer {tokens['accessToken']}"}

    def test_health_check_reports_database_readiness(self) -> None:
        response = self.client.get("/api/healthz")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_login_refresh_and_refresh_token_reuse_revokes_the_family(self) -> None:
        user = self.create_user("refresh")
        initial_tokens = self.login(user)

        refreshed = self.client.post(
            "/api/auth/refresh",
            json={"refreshToken": initial_tokens["refreshToken"]},
        )
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        rotated_tokens = refreshed.json()
        self.assertNotEqual(rotated_tokens["accessToken"], initial_tokens["accessToken"])
        self.assertNotEqual(rotated_tokens["refreshToken"], initial_tokens["refreshToken"])

        reused = self.client.post(
            "/api/auth/refresh",
            json={"refreshToken": initial_tokens["refreshToken"]},
        )
        self.assertEqual(reused.status_code, 401, reused.text)

        family_after_reuse = self.client.post(
            "/api/auth/refresh",
            json={"refreshToken": rotated_tokens["refreshToken"]},
        )
        self.assertEqual(family_after_reuse.status_code, 401, family_after_reuse.text)

    def test_tasks_are_private_to_the_authenticated_user(self) -> None:
        alice_tokens = self.login(self.create_user("alice"))
        bob_tokens = self.login(self.create_user("bob"))
        task_input = {
            "title": "Contrato aislado",
            "description": "Sólo Alice puede modificarla.",
            "priority": "high",
            "status": "todo",
            "dueDate": "2026-08-10",
        }

        created = self.client.post("/api/tasks", json=task_input, headers=self.bearer(alice_tokens))
        self.assertEqual(created.status_code, 201, created.text)
        task = created.json()
        self.assertEqual(task["title"], task_input["title"])
        self.assertEqual(task["dueDate"], task_input["dueDate"])
        self.assertNotIn("due_date", task)

        self.assertEqual(self.client.get("/api/tasks", headers=self.bearer(bob_tokens)).json(), [])
        forbidden_update = self.client.put("/api/tasks/" + task["id"], json=task_input, headers=self.bearer(bob_tokens))
        forbidden_delete = self.client.delete("/api/tasks/" + task["id"], headers=self.bearer(bob_tokens))
        self.assertEqual(forbidden_update.status_code, 404, forbidden_update.text)
        self.assertEqual(forbidden_delete.status_code, 404, forbidden_delete.text)

        updated_input = {**task_input, "status": "completed"}
        updated = self.client.put("/api/tasks/" + task["id"], json=updated_input, headers=self.bearer(alice_tokens))
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["status"], "completed")
        self.assertEqual(self.client.get("/api/tasks", headers=self.bearer(alice_tokens)).json()[0]["id"], task["id"])

        deleted = self.client.delete("/api/tasks/" + task["id"], headers=self.bearer(alice_tokens))
        self.assertEqual(deleted.status_code, 204, deleted.text)
        self.assertEqual(self.client.get("/api/tasks", headers=self.bearer(alice_tokens)).json(), [])
