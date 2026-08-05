"""API de TaskFlow con tareas SQLite y sesiones JWT persistidas en PostgreSQL."""

from contextlib import asynccontextmanager
from datetime import date
import base64
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

import psycopg
from argon2.exceptions import VerificationError
from argon2.low_level import Type, hash_secret, verify_secret
from fastapi import Depends, FastAPI, HTTPException, Header, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", Path(__file__).parent / "data" / "taskflow.db"))
USERS_PATH = Path(os.getenv("USERS_PATH", DATABASE_PATH.parent / "users.json"))
JWT_SECRET_FILE = Path(os.getenv("JWT_SECRET_FILE", "/run/secrets/taskflow_jwt_secret"))
POSTGRES_PASSWORD_FILE = Path(
    os.getenv("POSTGRES_PASSWORD_FILE", "/run/secrets/taskflow_postgres_password")
)
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "taskflow")
POSTGRES_USER = os.getenv("POSTGRES_USER", "taskflow")
ACCESS_TOKEN_TTL_SECONDS = int(os.getenv("ACCESS_TOKEN_TTL_SECONDS", "900"))
REFRESH_TOKEN_TTL_SECONDS = int(os.getenv("REFRESH_TOKEN_TTL_SECONDS", "2592000"))
JWT_ISSUER = os.getenv("JWT_ISSUER", "taskflow")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "taskflow-web")
# Controles ajustables sin cambiar el código. Los valores por defecto permiten
# el uso normal de la aplicación y acotan el coste de peticiones abusivas.
MAX_REQUEST_BODY_BYTES = int(os.getenv("MAX_REQUEST_BODY_BYTES", "1048576"))
LOGIN_RATE_LIMIT_ATTEMPTS = int(os.getenv("LOGIN_RATE_LIMIT_ATTEMPTS", "5"))
LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "60"))
LOGIN_LOCKOUT_FAILURES = int(os.getenv("LOGIN_LOCKOUT_FAILURES", "5"))
LOGIN_LOCKOUT_SECONDS = int(os.getenv("LOGIN_LOCKOUT_SECONDS", "900"))
PASSWORD_ITERATIONS = 600_000
# Perfil Argon2id compatible con servidores pequeños: 19 MiB, dos pasadas y
# un hilo. Mantiene un coste de memoria relevante sin bloquear Docker Desktop.
ARGON2_TIME_COST = 2
ARGON2_MEMORY_COST = 19_456
ARGON2_PARALLELISM = 1
ARGON2_HASH_LENGTH = 32
ARGON2_SALT_LENGTH = 16
Priority = Literal["low", "medium", "high"]
TaskStatus = Literal["todo", "in_progress", "completed"]
login_requests: dict[str, list[float]] = {}
failed_logins: dict[tuple[str, str], tuple[int, float, float]] = {}
auth_state_lock = Lock()
_jwt_secret: bytes | None = None
_postgres_password: str | None = None


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


class RefreshInput(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=512, validation_alias="refreshToken")

    model_config = ConfigDict(populate_by_name=True)


class LogoutInput(BaseModel):
    refresh_token: str | None = Field(default=None, min_length=32, max_length=512, validation_alias="refreshToken")

    model_config = ConfigDict(populate_by_name=True)


class TokenResponse(BaseModel):
    access_token: str = Field(serialization_alias="accessToken")
    refresh_token: str = Field(serialization_alias="refreshToken")
    token_type: Literal["bearer"] = Field(serialization_alias="tokenType")
    expires_in: int = Field(serialization_alias="expiresIn")

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


def read_required_secret(path: Path, label: str) -> str:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise RuntimeError(f"No se pudo leer el secreto {label} desde {path}.") from error
    if len(value) < 32:
        raise RuntimeError(f"El secreto {label} debe tener al menos 32 caracteres.")
    return value


def get_jwt_secret() -> bytes:
    global _jwt_secret
    if _jwt_secret is None:
        _jwt_secret = read_required_secret(JWT_SECRET_FILE, "JWT").encode("utf-8")
    return _jwt_secret


def get_postgres_password() -> str:
    global _postgres_password
    if _postgres_password is None:
        _postgres_password = read_required_secret(POSTGRES_PASSWORD_FILE, "de PostgreSQL")
    return _postgres_password


def get_connection() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def get_auth_connection() -> psycopg.Connection:
    return psycopg.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=get_postgres_password(),
    )


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


def initialize_auth_database() -> None:
    with get_auth_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                password_algorithm TEXT NOT NULL DEFAULT 'argon2id',
                role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user', 'admin')),
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_sessions (
                id TEXT PRIMARY KEY,
                family_id TEXT NOT NULL,
                username TEXT NOT NULL,
                refresh_token_hash TEXT NOT NULL UNIQUE,
                expires_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                revoked_at TIMESTAMPTZ
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS auth_sessions_family_id_idx ON auth_sessions (family_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS auth_sessions_active_idx ON auth_sessions (id, username) WHERE revoked_at IS NULL"
        )
        migrate_legacy_users(connection)


def load_legacy_users() -> dict[str, dict[str, str]]:
    """Lee el almacén previo sólo para migrarlo, nunca para autenticar."""
    if not USERS_PATH.exists():
        return {}
    try:
        users = json.loads(USERS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RuntimeError("El archivo de usuarios no contiene JSON válido.") from error

    if not isinstance(users, dict):
        raise RuntimeError("El archivo de usuarios debe contener un objeto JSON.")
    return users


def migrate_legacy_users(connection: psycopg.Connection) -> None:
    """Importa los hashes PBKDF2 existentes sin sobrescribir usuarios de PostgreSQL."""
    for username, user in load_legacy_users().items():
        if not isinstance(username, str) or not isinstance(user, dict):
            continue
        password_hash = user.get("password_hash")
        salt = user.get("salt")
        if not isinstance(password_hash, str) or not isinstance(salt, str):
            continue
        connection.execute(
            """
            INSERT INTO users (username, password_hash, salt, password_algorithm)
            VALUES (%s, %s, %s, 'pbkdf2_sha256')
            ON CONFLICT (username) DO NOTHING
            """,
            (username, password_hash, salt),
        )


def hash_password(password: str) -> tuple[str, str]:
    salt = secrets.token_bytes(ARGON2_SALT_LENGTH)
    password_hash = hash_secret(
        password.encode("utf-8"),
        salt,
        time_cost=ARGON2_TIME_COST,
        memory_cost=ARGON2_MEMORY_COST,
        parallelism=ARGON2_PARALLELISM,
        hash_len=ARGON2_HASH_LENGTH,
        type=Type.ID,
    ).decode("utf-8")
    return password_hash, salt.hex()


def verify_legacy_password(password: str, password_hash: str, salt: str) -> bool:
    try:
        salt_bytes = bytes.fromhex(salt)
    except ValueError:
        return False

    candidate_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt_bytes, PASSWORD_ITERATIONS
    ).hex()
    return hmac.compare_digest(candidate_hash, password_hash)


def verify_password(password: str, password_hash: str, salt: str, algorithm: str) -> bool:
    if algorithm == "argon2id":
        try:
            return verify_secret(password_hash.encode("utf-8"), password.encode("utf-8"), Type.ID)
        except (VerificationError, ValueError):
            return False
    if algorithm == "pbkdf2_sha256":
        return verify_legacy_password(password, password_hash, salt)
    return False


def get_user(username: str) -> tuple[str, str, str, bool] | None:
    with get_auth_connection() as connection:
        return connection.execute(
            """
            SELECT password_hash, salt, password_algorithm, is_active
            FROM users WHERE username = %s
            """,
            (username,),
        ).fetchone()


def upgrade_password_hash(username: str, password: str) -> None:
    password_hash, salt = hash_password(password)
    with get_auth_connection() as connection:
        connection.execute(
            """
            UPDATE users
            SET password_hash = %s, salt = %s, password_algorithm = 'argon2id', updated_at = NOW()
            WHERE username = %s
            """,
            (password_hash, salt, username),
        )


def base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def base64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_access_token(username: str, session_id: str) -> str:
    now = int(time())
    header = base64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = base64url_encode(
        json.dumps(
            {
                "sub": username,
                "sid": session_id,
                "typ": "access",
                "iss": JWT_ISSUER,
                "aud": JWT_AUDIENCE,
                "iat": now,
                "exp": now + ACCESS_TOKEN_TTL_SECONDS,
            },
            separators=(",", ":"),
        ).encode()
    )
    signature = base64url_encode(hmac.new(get_jwt_secret(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


def decode_access_token(token: str) -> dict[str, str | int]:
    try:
        header, payload, encoded_signature = token.split(".")
        expected_signature = base64url_encode(
            hmac.new(get_jwt_secret(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
        )
        decoded_header = json.loads(base64url_decode(header))
        claims = json.loads(base64url_decode(payload))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida o expirada.")

    if not hmac.compare_digest(encoded_signature, expected_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida o expirada.")
    if (
        decoded_header != {"alg": "HS256", "typ": "JWT"}
        or claims.get("typ") != "access"
        or claims.get("iss") != JWT_ISSUER
        or claims.get("aud") != JWT_AUDIENCE
        or not isinstance(claims.get("sub"), str)
        or not isinstance(claims.get("sid"), str)
        or not isinstance(claims.get("exp"), int)
        or claims["exp"] <= int(time())
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida o expirada.")
    return claims


def hash_refresh_token(refresh_token: str) -> str:
    return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()


def create_session(username: str, family_id: str | None = None) -> TokenResponse:
    session_id = str(uuid4())
    refresh_token = secrets.token_urlsafe(48)
    with get_auth_connection() as connection:
        connection.execute(
            """
            INSERT INTO auth_sessions (id, family_id, username, refresh_token_hash, expires_at)
            VALUES (%s, %s, %s, %s, NOW() + (%s * INTERVAL '1 second'))
            """,
            (session_id, family_id or str(uuid4()), username, hash_refresh_token(refresh_token), REFRESH_TOKEN_TTL_SECONDS),
        )
    return TokenResponse(
        access_token=create_access_token(username, session_id),
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_TTL_SECONDS,
    )


def refresh_session(refresh_token: str) -> TokenResponse:
    refresh_hash = hash_refresh_token(refresh_token)
    invalid_session = False
    with get_auth_connection() as connection:
        session = connection.execute(
            """
            SELECT id, family_id, username, expires_at, revoked_at
            FROM auth_sessions WHERE refresh_token_hash = %s FOR UPDATE
            """,
            (refresh_hash,),
        ).fetchone()
        if not session:
            invalid_session = True
        else:
            session_id, family_id, username, expires_at, revoked_at = session
            if revoked_at is not None or expires_at.timestamp() <= time():
                # La excepción se lanza fuera del bloque para confirmar primero
                # la revocación de toda la familia ante una reutilización.
                connection.execute(
                    "UPDATE auth_sessions SET revoked_at = NOW() WHERE family_id = %s AND revoked_at IS NULL",
                    (family_id,),
                )
                invalid_session = True
            else:
                connection.execute("UPDATE auth_sessions SET revoked_at = NOW() WHERE id = %s", (session_id,))
                new_session_id = str(uuid4())
                new_refresh_token = secrets.token_urlsafe(48)
                connection.execute(
                    """
                    INSERT INTO auth_sessions (id, family_id, username, refresh_token_hash, expires_at)
                    VALUES (%s, %s, %s, %s, NOW() + (%s * INTERVAL '1 second'))
                    """,
                    (new_session_id, family_id, username, hash_refresh_token(new_refresh_token), REFRESH_TOKEN_TTL_SECONDS),
                )
    if invalid_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión de actualización inválida.")
    return TokenResponse(
        access_token=create_access_token(username, new_session_id),
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_TTL_SECONDS,
    )


def revoke_session(session_id: str | None = None, refresh_token: str | None = None) -> None:
    if not session_id and not refresh_token:
        return
    with get_auth_connection() as connection:
        if session_id:
            connection.execute("UPDATE auth_sessions SET revoked_at = NOW() WHERE id = %s", (session_id,))
        elif refresh_token:
            connection.execute(
                "UPDATE auth_sessions SET revoked_at = NOW() WHERE refresh_token_hash = %s",
                (hash_refresh_token(refresh_token),),
            )


def get_client_ip(request: Request) -> str:
    """Obtiene la IP original enviada por el proxy interno de confianza."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", maxsplit=1)[0].strip()
    return request.client.host if request.client else "unknown"


def prune_auth_state(now: float) -> None:
    """Descarta estado vencido para que los límites en memoria sigan acotados."""
    for client_ip, request_times in list(login_requests.items()):
        recent_requests = [timestamp for timestamp in request_times if timestamp > now - LOGIN_RATE_LIMIT_WINDOW_SECONDS]
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


def require_auth(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticación requerida.")
    claims = decode_access_token(authorization.removeprefix("Bearer "))
    with get_auth_connection() as connection:
        session = connection.execute(
            """
            SELECT 1
            FROM auth_sessions
            JOIN users ON users.username = auth_sessions.username
            WHERE auth_sessions.id = %s AND auth_sessions.username = %s
              AND auth_sessions.revoked_at IS NULL AND auth_sessions.expires_at > NOW()
              AND users.is_active = TRUE
            """,
            (claims["sid"], claims["sub"]),
        ).fetchone()
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida o expirada.")
    return str(claims["sub"])


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
    # Falla al inicio si los secretos no fueron montados por la plataforma.
    get_jwt_secret()
    get_postgres_password()
    initialize_database()
    initialize_auth_database()
    yield


app = FastAPI(title="TaskFlow API", version="1.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=MAX_REQUEST_BODY_BYTES)


@app.post("/api/auth/login", response_model=TokenResponse, response_model_by_alias=True)
def login(login_input: LoginInput, request: Request) -> TokenResponse:
    login_key = check_login_allowed(login_input.username, get_client_ip(request))
    user = get_user(login_input.username)
    if not user:
        password_valid = False
    else:
        password_hash, salt, algorithm, is_active = user
        password_valid = is_active and verify_password(login_input.password, password_hash, salt, algorithm)
    if not password_valid:
        if register_failed_login(login_key):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Inicio de sesión bloqueado temporalmente por intentos fallidos.",
                headers={"Retry-After": str(LOGIN_LOCKOUT_SECONDS)},
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario o contraseña incorrectos.")

    clear_failed_logins(login_key)
    if algorithm == "pbkdf2_sha256":
        upgrade_password_hash(login_input.username, login_input.password)
    return create_session(login_input.username)


@app.post("/api/auth/refresh", response_model=TokenResponse, response_model_by_alias=True)
def refresh(refresh_input: RefreshInput) -> TokenResponse:
    return refresh_session(refresh_input.refresh_token)


@app.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    logout_input: LogoutInput | None = None,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    session_id: str | None = None
    if authorization and authorization.startswith("Bearer "):
        try:
            session_id = str(decode_access_token(authorization.removeprefix("Bearer "))["sid"])
        except HTTPException:
            # Un access token vencido no impide revocar el refresh token recibido.
            pass
    revoke_session(session_id, logout_input.refresh_token if logout_input else None)
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
                task_data["id"], task_data["title"], task_data["description"], task_data["priority"],
                task_data["status"], task_data["due_date"], owner,
            ),
        )
    return task


@app.put("/api/tasks/{task_id}", response_model=Task, response_model_by_alias=True)
def update_task(task_id: str, task_input: TaskInput, owner: str = Depends(require_auth)) -> Task:
    task = Task(id=task_id, **task_input.model_dump())
    task_data = task.model_dump(mode="json")
    with get_connection() as connection:
        result = connection.execute(
            """UPDATE tasks SET title = ?, description = ?, priority = ?, status = ?, due_date = ?
            WHERE id = ? AND owner = ?""",
            (
                task_data["title"], task_data["description"], task_data["priority"], task_data["status"],
                task_data["due_date"], task_data["id"], owner,
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
