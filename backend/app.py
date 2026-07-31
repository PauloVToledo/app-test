"""API de TaskFlow implementada con FastAPI y SQLite."""

from contextlib import asynccontextmanager
from datetime import date
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
from time import time
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Header, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", Path(__file__).parent / "data" / "taskflow.db"))
USERS_PATH = Path(os.getenv("USERS_PATH", DATABASE_PATH.parent / "users.json"))
TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", "43200"))
PASSWORD_ITERATIONS = 600_000
Priority = Literal["low", "medium", "high"]
TaskStatus = Literal["todo", "in_progress", "completed"]
active_tokens: dict[str, tuple[str, float]] = {}


class TaskInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    priority: Priority = "medium"
    status: TaskStatus = "todo"
    due_date: date = Field(default_factory=date.today, validation_alias="dueDate", serialization_alias="dueDate")

    model_config = ConfigDict(populate_by_name=True)


class Task(TaskInput):
    id: str


class LoginInput(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=256)


class LoginResponse(BaseModel):
    access_token: str = Field(serialization_alias="accessToken")
    token_type: Literal["bearer"] = Field(serialization_alias="tokenType")

    model_config = ConfigDict(populate_by_name=True)


def get_connection() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                priority TEXT NOT NULL CHECK(priority IN ('low', 'medium', 'high')),
                status TEXT NOT NULL CHECK(status IN ('todo', 'in_progress', 'completed')),
                due_date TEXT NOT NULL
            )
            """
        )
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(tasks)")}
        if "owner" not in columns:
            connection.execute("ALTER TABLE tasks ADD COLUMN owner TEXT NOT NULL DEFAULT 'admin'")


def load_users() -> dict[str, dict[str, str]]:
    if not USERS_PATH.exists():
        raise RuntimeError(
            f"No se encontró el archivo de usuarios en {USERS_PATH}. "
            "Crea un usuario con backend/create_user.py."
        )

    try:
        users = json.loads(USERS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RuntimeError("El archivo de usuarios no contiene JSON válido.") from error

    if not isinstance(users, dict):
        raise RuntimeError("El archivo de usuarios debe contener un objeto JSON.")
    return users


def verify_password(password: str, user: dict[str, str]) -> bool:
    try:
        expected_hash = user["password_hash"]
        salt = bytes.fromhex(user["salt"])
    except (KeyError, TypeError, ValueError):
        return False

    password_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    ).hex()
    return hmac.compare_digest(password_hash, expected_hash)


def require_auth(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticación requerida.")

    token = authorization.removeprefix("Bearer ")
    token_data = active_tokens.get(token)
    if not token_data or token_data[1] <= time():
        active_tokens.pop(token, None)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida o expirada.")
    return token_data[0]


def row_to_task(row: sqlite3.Row) -> Task:
    return Task(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        priority=row["priority"],
        status=row["status"],
        dueDate=row["due_date"],
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="TaskFlow API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/auth/login", response_model=LoginResponse, response_model_by_alias=True)
def login(login_input: LoginInput) -> LoginResponse:
    user = load_users().get(login_input.username)
    if not user or not verify_password(login_input.password, user):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario o contraseña incorrectos.")

    token = secrets.token_urlsafe(32)
    active_tokens[token] = (login_input.username, time() + TOKEN_TTL_SECONDS)
    return LoginResponse(access_token=token, token_type="bearer")


@app.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(authorization: Annotated[str | None, Header()] = None) -> Response:
    if authorization and authorization.startswith("Bearer "):
        active_tokens.pop(authorization.removeprefix("Bearer "), None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/tasks", response_model=list[Task], response_model_by_alias=True)
def list_tasks(owner: str = Depends(require_auth)) -> list[Task]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM tasks WHERE owner = ? ORDER BY rowid DESC", (owner,)
        ).fetchall()
    return [row_to_task(row) for row in rows]


@app.post("/api/tasks", response_model=Task, response_model_by_alias=True, status_code=status.HTTP_201_CREATED)
def create_task(task_input: TaskInput, owner: str = Depends(require_auth)) -> Task:
    task = Task(id=str(uuid4()), **task_input.model_dump())
    task_data = task.model_dump(mode="json")
    with get_connection() as connection:
        connection.execute(
            """INSERT INTO tasks (id, title, description, priority, status, due_date, owner)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                task_data["id"],
                task_data["title"],
                task_data["description"],
                task_data["priority"],
                task_data["status"],
                task_data["due_date"],
                owner,
            ),
        )
    return task


@app.put("/api/tasks/{task_id}", response_model=Task, response_model_by_alias=True)
def update_task(
    task_id: str, task_input: TaskInput, owner: str = Depends(require_auth)
) -> Task:
    task = Task(id=task_id, **task_input.model_dump())
    task_data = task.model_dump(mode="json")
    with get_connection() as connection:
        result = connection.execute(
            """UPDATE tasks SET title = ?, description = ?, priority = ?, status = ?, due_date = ?
            WHERE id = ? AND owner = ?""",
            (
                task_data["title"],
                task_data["description"],
                task_data["priority"],
                task_data["status"],
                task_data["due_date"],
                task_data["id"],
                owner,
            ),
        )
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tarea no encontrada.")
    return task


@app.delete("/api/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: str, owner: str = Depends(require_auth)) -> Response:
    with get_connection() as connection:
        result = connection.execute("DELETE FROM tasks WHERE id = ? AND owner = ?", (task_id, owner))
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tarea no encontrada.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
