# Provisión reproducible de un VPS de TaskFlow

Este runbook configura una instalación nueva de TaskFlow sin cambiar el
código ni guardar credenciales en Git. El procedimiento asume un VPS Linux
con Docker Engine y el plugin `docker compose` instalados, una cuenta con
`sudo`, un FQDN propio y un bucket S3-compatible dedicado para respaldos.

## 1. Preparar el VPS y el DNS

1. Instala Docker Engine, el plugin Compose y Git usando el procedimiento
   oficial de tu distribución. Comprueba que la cuenta de despliegue puede
   ejecutar `docker ps` sin `sudo` o decide usar `sudo docker` de forma
   consistente.
2. Instala las utilidades necesarias:

   ```bash
   sudo apt-get update
   sudo apt-get install -y ca-certificates git openssl
   docker --version
   docker compose version
   ```

3. Crea un registro `A` (y `AAAA` sólo si IPv6 está correctamente enroutado)
   para el dominio que usarás en `TASKFLOW_DOMAIN`. Debe apuntar a la IP del
   VPS antes de arrancar Caddy.
4. Permite en el firewall del proveedor y del VPS únicamente TCP `22`, `80`
   y `443`. Restringe `22` a tu IP o red administrativa cuando sea posible.
   No abras `8000`, `5432` ni `3333`: backend, PostgreSQL y Grafana no deben
   quedar publicados en Internet.

## 2. Obtener el código

Elige una ruta estable y mantenla igual durante la vida del servicio:

```bash
sudo mkdir -p /opt/taskflow
sudo chown "$USER":"$USER" /opt/taskflow
git clone <URL_DEL_REPOSITORIO> /opt/taskflow
cd /opt/taskflow
```

Si la máquina no puede clonar por SSH, usa el método de acceso aprobado por
tu proveedor. No copies `.env` ni archivos de `secrets/` desde el repositorio.

## 3. Crear configuración y secretos

La configuración no sensible se mantiene en `.env`; las credenciales se
mantienen como archivos locales con permisos `0600` y son consumidas por
Docker Compose como secretos. Ejecuta:

```bash
cd /opt/taskflow
cp .env.example .env
sed -i 's/^TASKFLOW_DOMAIN=.*/TASKFLOW_DOMAIN=taskflow.example.com/' .env
chmod 600 .env

install -d -m 0700 secrets
openssl rand -base64 48 > secrets/jwt_secret
openssl rand -base64 36 > secrets/postgres_password
chmod 600 secrets/jwt_secret secrets/postgres_password
```

Edita `.env` y confirma al menos `TASKFLOW_DOMAIN`. Los valores de base de
datos, TTL, límites y emisor/audiencia tienen valores explícitos en la
plantilla; cámbialos sólo con una decisión de configuración documentada.

Para habilitar observabilidad, crea además el secreto de Grafana:

```bash
openssl rand -base64 36 > secrets/grafana_admin_password
chmod 600 secrets/grafana_admin_password
```

Nunca pongas contraseñas, claves JWT, claves S3 ni la contraseña de Restic en
`.env`, en un commit o en un comando que quede guardado en el historial.

## 4. Validar antes de arrancar

Comprueba que Compose puede resolver la configuración y que no falta ningún
secreto:

```bash
test -s .env
test -s secrets/jwt_secret
test -s secrets/postgres_password
docker compose config --quiet
```

La configuración esperada tiene sólo `caddy` con puertos del host; `backend`,
`frontend` y `postgres` usan `expose` o red interna.

## 5. Arrancar y crear el primer usuario

Arranca en segundo plano, espera los health checks y revisa los logs:

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 caddy backend postgres
curl --fail --silent --show-error --head "https://${TASKFLOW_DOMAIN}"
```

Cada servicio usa `restart: unless-stopped` y rota el driver `json-file` a
tres archivos de 10 MiB. Verifica que Docker aplicó ambas políticas y que un
reinicio controlado recupera el backend:

```bash
docker inspect -f '{{.HostConfig.RestartPolicy.Name}} {{.HostConfig.LogConfig.Type}} {{json .HostConfig.LogConfig.Config}}' "$(docker compose ps -q backend)"
docker compose restart backend
docker compose ps backend
```

La salida de la primera orden debe contener `unless-stopped json-file` y
`max-size`/`max-file`; la segunda debe mostrar el backend saludable tras su
health check.

La primera ejecución crea el volumen `postgres_data` y Caddy solicita el
certificado ACME. Si HTTPS falla, verifica primero DNS, firewall y que ningún
otro proceso esté usando los puertos `80`/`443`.

Crea el usuario inicial sólo después de que el backend esté saludable:

```bash
docker compose exec backend python create_user.py --username admin
```

El comando solicita la contraseña de forma interactiva y no la escribe en el
repositorio. Para una automatización controlada se puede usar temporalmente
`TASKFLOW_CREATE_USER_PASSWORD`, eliminándola inmediatamente después.

## 6. Observabilidad opcional

Grafana queda limitado al loopback del VPS (`127.0.0.1:3333`), por lo que se
administra mediante un túnel SSH:

```bash
test -s secrets/grafana_admin_password
docker compose --profile observability up -d
docker compose --profile observability ps
ssh -L 3333:127.0.0.1:3333 <usuario>@<ip-del-vps>
```

Abre `http://127.0.0.1:3333` en tu equipo y usa `GRAFANA_ADMIN_USER` junto
con el contenido de `secrets/grafana_admin_password`.

## 7. Activar respaldos externos y pruebas de restauración

Antes de activar los timers, crea un bucket exclusivo para PostgreSQL fuera
del VPS, preferiblemente en otra cuenta o proveedor. Habilita versionado y
una credencial con permisos mínimos sobre ese bucket. La contraseña de Restic
debe guardarse aparte, en un gestor de secretos y en un mecanismo de
recuperación documentado.

En el VPS:

```bash
sudo install -d -m 0700 /etc/taskflow/backup
sudo install -m 0600 infra/backups/restic.env.example /etc/taskflow/backup/restic.env
sudoedit /etc/taskflow/backup/restic.env
sudo install -m 0600 /dev/null /etc/taskflow/backup/restic_password
sudoedit /etc/taskflow/backup/restic_password

sudo install -m 0644 infra/backups/systemd/taskflow-postgres-*.service /etc/systemd/system/
sudo install -m 0644 infra/backups/systemd/taskflow-postgres-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now taskflow-postgres-backup.timer taskflow-postgres-restore-test.timer
```

Completa `RESTIC_REPOSITORY`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
`POSTGRES_DB` y `POSTGRES_USER` en `/etc/taskflow/backup/restic.env`. Prueba
ambos servicios y conserva la evidencia:

```bash
sudo systemctl start taskflow-postgres-backup.service
sudo journalctl -u taskflow-postgres-backup.service --no-pager -n 100
sudo systemctl start taskflow-postgres-restore-test.service
sudo journalctl -u taskflow-postgres-restore-test.service --no-pager -n 100
```

El backup es un `pg_dump` cifrado en Restic. La prueba restaura en un
PostgreSQL temporal sin red, sin puertos y sin `postgres_data`; nunca la
ejecutes restaurando directamente sobre el volumen de producción.

## 8. Actualizaciones y recuperación

Para actualizar, conserva el `.env`, `secrets/`, los volúmenes y la evidencia
de backups; sólo cambia el código versionado:

```bash
cd /opt/taskflow
git fetch --tags origin
git checkout <VERSION_O_COMMIT_APROBADO>
docker compose up -d --build --remove-orphans
docker compose ps
```

Antes de una migración o cambio de contrato, ejecuta un backup manual y
confirma el health check. Para una incidencia de datos, ejecuta primero
`restore-test-postgres.service` y valida el contenido; cualquier reemplazo de
`postgres_data` requiere un runbook de incidente separado y una ventana de
mantenimiento. Un backup no recupera el código, DNS, secretos ni la
configuración del proveedor.

## Criterio de aceptación de una instalación nueva

- `.env` proviene de `.env.example` y no contiene credenciales.
- Los tres secretos de Compose existen sólo en `secrets/` con permisos `0600`.
- `docker compose config --quiet` pasa y sólo Caddy publica `80/443`.
- Cada servicio tiene reinicio `unless-stopped`, logs Docker rotados y las
  imágenes externas y bases de build están fijadas por digest.
- Un `docker compose restart backend` devuelve el backend a estado saludable.
- HTTPS responde para el FQDN configurado y el usuario inicial puede iniciar
  sesión.
- El backup y la restauración aislada terminan correctamente y sus logs quedan
  conservados.
