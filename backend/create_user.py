"""Crea o actualiza un usuario de TaskFlow en PostgreSQL."""

import argparse
import getpass
import os

from app.main import get_auth_connection, hash_password, initialize_auth_database


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

    # Permite crear el primer usuario antes de iniciar FastAPI.
    initialize_auth_database()
    password_hash, salt = hash_password(password)
    with get_auth_connection() as connection:
        connection.execute(
            """
            INSERT INTO users (username, password_hash, salt, password_algorithm)
            VALUES (%s, %s, %s, 'argon2id')
            ON CONFLICT (username) DO UPDATE SET
                password_hash = EXCLUDED.password_hash,
                salt = EXCLUDED.salt,
                password_algorithm = EXCLUDED.password_algorithm,
                is_active = TRUE,
                updated_at = NOW()
            """,
            (arguments.username, password_hash, salt),
        )
        connection.execute(
            "UPDATE auth_sessions SET revoked_at = NOW() WHERE username = %s AND revoked_at IS NULL",
            (arguments.username,),
        )
    print(f"Usuario '{arguments.username}' guardado en PostgreSQL con Argon2id.")


if __name__ == "__main__":
    main()
