#!/usr/bin/env bash
# Crea un dump PostgreSQL recuperable y lo guarda cifrado en un repositorio
# Restic externo. Este script se ejecuta en el VPS, no dentro del contenedor.
set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$PROJECT_DIR/compose.yaml"
BACKUP_CONFIG="${TASKFLOW_BACKUP_CONFIG:-/etc/taskflow/backup/restic.env}"
RESTIC_PASSWORD_HOST_FILE="${TASKFLOW_RESTIC_PASSWORD_FILE:-/etc/taskflow/backup/restic_password}"
RESTIC_IMAGE="${TASKFLOW_RESTIC_IMAGE:-restic/restic:0.17.3}"
BACKUP_PATH="postgres/taskflow.dump"

fail() {
  printf 'backup-postgres: %s\n' "$*" >&2
  exit 1
}

require_file() {
  [[ -r "$1" ]] || fail "No se puede leer $1"
}

require_file "$COMPOSE_FILE"
require_file "$BACKUP_CONFIG"
require_file "$RESTIC_PASSWORD_HOST_FILE"

# El archivo de configuración puede contener las credenciales del bucket.
# Debe pertenecer a root y no ser legible por otros usuarios del VPS.
if command -v stat >/dev/null 2>&1; then
  permissions="$(stat -c '%a' "$BACKUP_CONFIG" 2>/dev/null || true)"
  [[ -z "$permissions" || "$permissions" -le 600 ]] || fail "$BACKUP_CONFIG debe tener permisos 0600 o más restrictivos"
fi

# shellcheck disable=SC1090
source "$BACKUP_CONFIG"
: "${RESTIC_REPOSITORY:?Define RESTIC_REPOSITORY en $BACKUP_CONFIG}"
: "${POSTGRES_DB:=taskflow}"
: "${POSTGRES_USER:=taskflow}"

compose() {
  docker compose --project-directory "$PROJECT_DIR" -f "$COMPOSE_FILE" "$@"
}

restic() {
  docker run --rm \
    --env-file "$BACKUP_CONFIG" \
    -e RESTIC_PASSWORD_FILE=/run/secrets/restic_password \
    -v "$RESTIC_PASSWORD_HOST_FILE:/run/secrets/restic_password:ro" \
    "$RESTIC_IMAGE" "$@"
}

# Un repositorio recién creado no tiene config. En los siguientes ciclos esta
# comprobación no modifica nada.
if ! restic cat config >/dev/null 2>&1; then
  restic init
fi

printf 'Iniciando dump PostgreSQL para el repositorio remoto.\n'
compose exec -T postgres pg_dump \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --format=custom \
  --compress=9 \
  --no-owner \
  --no-acl \
  | restic backup --stdin --stdin-filename "$BACKUP_PATH" --tag taskflow --tag postgres

# Política: 35 diarios, 12 mensuales y 7 anuales. El repositorio se dedica a
# PostgreSQL, por lo que no se mezclan aquí otros tipos de respaldo.
restic forget --tag postgres --keep-daily 35 --keep-monthly 12 --keep-yearly 7 --prune

# Detecta corrupción de metadatos y toma una muestra de datos en cada respaldo.
restic check --read-data-subset=5%
restic snapshots --tag postgres --latest 1
