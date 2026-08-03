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
from threading import Lock
from time import time
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Header, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", Path(__file__).parent / "data" / "taskflow.db"))
USERS_PATH = Path(os.getenv("USERS_PATH", DATABASE_PATH.parent / "users.json"))
TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", "43200"))
# Controles ajustables sin cambiar el código. Los valores por defecto permiten
# el uso normal de la aplicación y acotan el coste de peticiones abusivas.
MAX_REQUEST_BODY_BYTES = int(os.getenv("MAX_REQUEST_BODY_BYTES", "1048576"))
LOGIN_RATE_LIMIT_ATTEMPTS = int(os.getenv("LOGIN_RATE_LIMIT_ATTEMPTS", "5"))
LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "60"))
LOGIN_LOCKOUT_FAILURES = int(os.getenv("LOGIN_LOCKOUT_FAILURES", "5"))
LOGIN_LOCKOUT_SECONDS = int(os.getenv("LOGIN_LOCKOUT_SECONDS", "900"))
PASSWORD_ITERATIONS = 600_000
Priority = Literal["low", "medium", "high"]
TaskStatus = Literal["todo", "in_progress", "completed"]
active_tokens: dict[str, tuple[str, float]] = {}
login_requests: dict[str, list[float]] = {}
failed_logins: dict[tuple[str, str], tuple[int, float, float]] = {}
auth_state_lock = Lock()


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


class RequestBodyTooLarge(Exception):
    """Señala que el cuerpo excedió el límite durante una transferencia."""


class RequestBodyLimitMiddleware:
    """Aplica un máximo de bytes sin acumular cuerpos fragmentados completos."""

    def __init__(self, app, max_body_bytes: int):
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        content_length = headers.get(b"content-length")
        if content_length and content_length.isdigit() and int(content_length) > self.max_body_bytes:
            await self.send_too_large(scope, receive, send)
            return

        received_bytes = 0

        async def limited_receive():
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_body_bytes:
                    raise RequestBodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestBodyTooLarge:
            await self.send_too_large(scope, receive, send)

    @staticmethod
    async def send_too_large(scope, receive, send) -> None:
        response = JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={"detail": "El cuerpo de la solicitud supera el tamaño permitido."},
        )
        await response(scope, receive, send)


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


def get_client_ip(request: Request) -> str:
    """Obtiene la IP original enviada por el proxy interno de confianza."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", maxsplit=1)[0].strip()
    return request.client.host if request.client else "unknown"


def prune_auth_state(now: float) -> None:
    """Descarta estado vencido para que los límites en memoria sigan acotados."""
    for client_ip, request_times in list(login_requests.items()):
        recent_requests = [
            timestamp
            for timestamp in request_times
            if timestamp > now - LOGIN_RATE_LIMIT_WINDOW_SECONDS
        ]
        if recent_requests:
            login_requests[client_ip] = recent_requests
        else:
            del login_requests[client_ip]

    for login_key, (_, locked_until, last_failure) in list(failed_logins.items()):
        if locked_until <= now and last_failure <= now - LOGIN_LOCKOUT_SECONDS:
            del failed_logins[login_key]


def check_login_allowed(username: str, client_ip: str) -> tuple[str, str]:
    """Aplica el límite por IP y comprueba el bloqueo usuario+IP."""
    now = time()
    login_key = (username.casefold(), client_ip)
    with auth_state_lock:
        prune_auth_state(now)
        request_times = login_requests.get(client_ip, [])
        if len(request_times) >= LOGIN_RATE_LIMIT_ATTEMPTS:
            retry_after = max(1, int(request_times[0] + LOGIN_RATE_LIMIT_WINDOW_SECONDS - now))
            login_requests[client_ip] = request_times
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Demasiados intentos de inicio de sesión. Inténtalo más tarde.",
                headers={"Retry-After": str(retry_after)},
            )
        request_times.append(now)
        login_requests[client_ip] = request_times

        failure_count, locked_until, _ = failed_logins.get(login_key, (0, 0.0, 0.0))
        if locked_until > now:
            retry_after = max(1, int(locked_until - now))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Inicio de sesión bloqueado temporalmente por intentos fallidos.",
                headers={"Retry-After": str(retry_after)},
            )
        if locked_until:
            failed_logins.pop(login_key, None)
    return login_key


def register_failed_login(login_key: tuple[str, str]) -> bool:
    """Registra un fallo y devuelve si este intento acaba de bloquear el acceso."""
    with auth_state_lock:
        now = time()
        failures, _, _ = failed_logins.get(login_key, (0, 0.0, 0.0))
        failures += 1
        if failures >= LOGIN_LOCKOUT_FAILURES:
            failed_logins[login_key] = (failures, now + LOGIN_LOCKOUT_SECONDS, now)
            return True
        failed_logins[login_key] = (failures, 0.0, now)
    return False


def clear_failed_logins(login_key: tuple[str, str]) -> None:
    with auth_state_lock:
        failed_logins.pop(login_key, None)


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
app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=MAX_REQUEST_BODY_BYTES)


@app.post("/api/auth/login", response_model=LoginResponse, response_model_by_alias=True)
def login(login_input: LoginInput, request: Request) -> LoginResponse:
    login_key = check_login_allowed(login_input.username, get_client_ip(request))
    user = load_users().get(login_input.username)
    if not user or not verify_password(login_input.password, user):
        if register_failed_login(login_key):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Inicio de sesión bloqueado temporalmente por intentos fallidos.",
                headers={"Retry-After": str(LOGIN_LOCKOUT_SECONDS)},
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario o contraseña incorrectos.")

    clear_failed_logins(login_key)
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
