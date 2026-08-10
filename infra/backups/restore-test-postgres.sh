#!/usr/bin/env bash
# Restaura el último dump en un PostgreSQL desechable y valida su esquema.
# Nunca monta el volumen postgres_data ni publica un puerto del contenedor.
set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
BACKUP_CONFIG="${TASKFLOW_BACKUP_CONFIG:-/etc/taskflow/backup/restic.env}"
RESTIC_PASSWORD_HOST_FILE="${TASKFLOW_RESTIC_PASSWORD_FILE:-/etc/taskflow/backup/restic_password}"
RESTIC_IMAGE="${TASKFLOW_RESTIC_IMAGE:-restic/restic:0.17.3}"
POSTGRES_IMAGE="${TASKFLOW_RESTORE_POSTGRES_IMAGE:-postgres:16-alpine}"
BACKUP_PATH="postgres/taskflow.dump"
TEST_CONTAINER="taskflow-postgres-restore-test-$$"

fail() {
  printf 'restore-test-postgres: %s\n' "$*" >&2
  exit 1
}

require_file() {
  [[ -r "$1" ]] || fail "No se puede leer $1"
}

require_file "$BACKUP_CONFIG"
require_file "$RESTIC_PASSWORD_HOST_FILE"

# shellcheck disable=SC1090
source "$BACKUP_CONFIG"
: "${RESTIC_REPOSITORY:?Define RESTIC_REPOSITORY en $BACKUP_CONFIG}"
: "${POSTGRES_DB:=taskflow}"
: "${POSTGRES_USER:=taskflow}"

restic() {
  docker run --rm \
    --env-file "$BACKUP_CONFIG" \
    -e RESTIC_PASSWORD_FILE=/run/secrets/restic_password \
    -v "$RESTIC_PASSWORD_HOST_FILE:/run/secrets/restic_password:ro" \
    "$RESTIC_IMAGE" "$@"
}

cleanup() {
  docker rm --force "$TEST_CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# No hay red, puertos ni volumen de producción: el entorno es aislado y se
# elimina al terminar, incluso si falla una validación.
docker run --detach --rm \
  --name "$TEST_CONTAINER" \
  --network none \
  -e POSTGRES_DB="$POSTGRES_DB" \
  -e POSTGRES_USER="$POSTGRES_USER" \
  -e POSTGRES_PASSWORD=restore-test-only \
  "$POSTGRES_IMAGE" >/dev/null

for _ in {1..30}; do
  if docker exec "$TEST_CONTAINER" pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker exec "$TEST_CONTAINER" pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null \
  || fail 'PostgreSQL aislado no inició a tiempo'

# La comprobación completa verifica todos los packs remotos antes de leer el
# dump. pg_restore --exit-on-error evita aceptar una restauración parcial.
restic check --read-data
restic dump latest "$BACKUP_PATH" \
  | docker exec -i "$TEST_CONTAINER" pg_restore \
      --exit-on-error --no-owner --no-acl \
      --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"

expected_tables=$'application_migrations\nauth_sessions\ntasks\nusers'
actual_tables="$(docker exec "$TEST_CONTAINER" psql -X -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  \"SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('application_migrations', 'auth_sessions', 'tasks', 'users') ORDER BY table_name;\")"
[[ "$actual_tables" == "$expected_tables" ]] || fail "Faltan tablas esperadas tras restaurar: $actual_tables"

docker exec "$TEST_CONTAINER" psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "SELECT 'users' AS table_name, COUNT(*) AS rows FROM users UNION ALL SELECT 'auth_sessions', COUNT(*) FROM auth_sessions UNION ALL SELECT 'tasks', COUNT(*) FROM tasks UNION ALL SELECT 'application_migrations', COUNT(*) FROM application_migrations ORDER BY table_name;"

printf 'Restauración aislada completada correctamente desde el último snapshot.\n'
