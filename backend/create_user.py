"""Crea o actualiza un usuario local para TaskFlow."""

import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import secrets

PASSWORD_ITERATIONS = 600_000
USERS_PATH = Path(
    os.getenv("USERS_PATH", Path(__file__).parent / "data" / "users.json")
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crea o actualiza un usuario de TaskFlow.")
    parser.add_argument("--username", required=True, help="Nombre de usuario (3 a 64 caracteres).")
    return parser.parse_args()


def validate_username(username: str) -> None:
    allowed_characters = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-")
    if not 3 <= len(username) <= 64 or not set(username) <= allowed_characters:
        raise ValueError("El usuario debe tener entre 3 y 64 caracteres alfanuméricos, punto, guion o guion bajo.")


def main() -> None:
    arguments = parse_arguments()
    validate_username(arguments.username)
    password = os.getenv("TASKFLOW_CREATE_USER_PASSWORD") or getpass.getpass(
        "Contraseña (mínimo 12 caracteres): "
    )
    if len(password) < 12:
        raise ValueError("La contraseña debe tener al menos 12 caracteres.")

    USERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    users = {}
    if USERS_PATH.exists():
        users = json.loads(USERS_PATH.read_text(encoding="utf-8"))

    salt = secrets.token_bytes(16)
    users[arguments.username] = {
        "salt": salt.hex(),
        "password_hash": hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
        ).hex(),
    }
    USERS_PATH.write_text(json.dumps(users, indent=2) + "\n", encoding="utf-8")
    print(f"Usuario '{arguments.username}' guardado en {USERS_PATH}.")


if __name__ == "__main__":
    main()
