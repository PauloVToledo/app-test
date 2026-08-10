# TaskFlow

TaskFlow se organiza como un monorepo: `frontend/` contiene React/Vite,
`backend/` contiene FastAPI y `infra/` concentra proxy y observabilidad.
`compose.yaml` orquesta todos los servicios. Consulta los `AGENTS.md` de cada
área antes de modificarla.

## Getting Started

### Prerequisites

- [Node.js](https://nodejs.org/) (v18 or higher recommended)
- npm (included with Node.js)

### Installation

Clone the repository and install the dependencies:

```bash
cd frontend
npm install
```

### Available Scripts

| Command           | Description                                                       |
| ----------------- | ----------------------------------------------------------------- |
| `npm run dev`     | Starts the development server with HMR at `http://localhost:5173` |
| `npm run build`   | Builds the app for production into the `dist/` folder             |
| `npm run preview` | Serves the production build locally for previewing                |
| `npm run lint`    | Runs Oxlint to check for code issues                              |

### Running in Development

TaskFlow incluye una API FastAPI, SQLite para tareas, PostgreSQL para usuarios
y sesiones de autenticación, y acceso mediante JWT. Para el entorno local se requiere
Python 3.10 o superior y una instancia PostgreSQL accesible.

Antes de iniciar la API, crea el primer usuario directamente en PostgreSQL:

```bash
cd backend
python create_user.py --username admin
```

El script pide la contraseña de forma interactiva y la almacena como hash
Argon2id con salt aleatorio. Para automatizaciones, usa
la variable de entorno temporal `TASKFLOW_CREATE_USER_PASSWORD`; no la
incluyas en archivos versionados.

Para ejecución local (sin Docker), crea los dos archivos de secretos con al
menos 32 caracteres aleatorios y exporta sus rutas junto a la conexión de
PostgreSQL. Los secretos no se aceptan como variables de entorno con valor:
FastAPI los lee desde archivos para que el mecanismo sea equivalente al del
despliegue Docker.

```powershell
$env:JWT_SECRET_FILE = "$PWD/secrets/jwt_secret"
$env:POSTGRES_PASSWORD_FILE = "$PWD/secrets/postgres_password"
$env:POSTGRES_HOST = "127.0.0.1"
```

Inicia el backend en una terminal:

```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Después, en otra terminal, inicia el frontend:

```bash
cd frontend
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser to see the app running.
Vite redirige las llamadas a `/api` hacia el backend local. Las tareas se
guardan en `backend/data/taskflow.db` y cada usuario solo puede acceder a sus
propias tareas.

### Ejecutar con Docker

El despliegue Docker usa Caddy como proxy TLS. Caddy solicita y renueva el
certificado HTTPS automáticamente mediante ACME; el backend y Nginx no se
publican directamente. PostgreSQL se inicia desde la imagen
`postgres:16-alpine` y conserva las sesiones en el volumen Docker
`postgres_data`. Antes de iniciar, crea `.env` a partir de la plantilla y
configura un nombre DNS público que ya apunte a la IP del servidor:

```bash
cp .env.example .env
# Edita .env: TASKFLOW_DOMAIN=tasks.tu-dominio.com

# Crea secretos de producción fuera de Git (un valor por archivo).
mkdir secrets
openssl rand -base64 48 > secrets/jwt_secret
openssl rand -base64 36 > secrets/postgres_password
```

En Windows sin OpenSSL puedes usar PowerShell:

```powershell
New-Item -ItemType Directory -Force secrets
[Convert]::ToBase64String((1..48 | ForEach-Object { Get-Random -Maximum 256 })) | Set-Content -NoNewline secrets/jwt_secret
[Convert]::ToBase64String((1..36 | ForEach-Object { Get-Random -Maximum 256 })) | Set-Content -NoNewline secrets/postgres_password
```

`secrets/jwt_secret` y `secrets/postgres_password` son secretos de Docker
Compose: se montan sólo en los contenedores que los necesitan, en
`/run/secrets`, y están ignorados por Git. En una plataforma gestionada,
sustituye estas fuentes `file:` por su integración nativa de secretos sin
cambiar el código, que ya consume rutas de archivos.

Los puertos TCP 80 y 443 deben estar abiertos hacia el servidor y no pueden
estar ocupados por otro proxy. Después inicia el stack:

```bash
docker compose -f compose.yaml up --build
```

Abre `https://<TASKFLOW_DOMAIN>`. Las peticiones HTTP se redirigen a HTTPS y
las respuestas HTTPS incluyen HSTS (`max-age=31536000; includeSubDomains`). No
actives este despliegue con un dominio temporal ni habilites subdominios que no
puedan usar HTTPS: los navegadores recordarán esa política durante un año.

El backend no publica un puerto hacia el host y el frontend solo es accesible
para Caddy dentro de Docker. Para crear un usuario en Docker:

```bash
docker compose -f compose.yaml exec backend python create_user.py --username admin
```

### Logs, alertas y health checks

El perfil opcional `observability` añade Grafana, Loki y Grafana Alloy. Alloy
lee los logs de Docker y los envía a Loki; Grafana centraliza la consulta y
provisiona alertas para errores del backend, errores JavaScript reportados por
el frontend y ausencia de health checks. Grafana sólo se publica en el
loopback del host (`http://localhost:3333`), nunca a través de Caddy.

Antes de activarlo, crea la contraseña local de Grafana a partir de la plantilla:

```powershell
Copy-Item secrets/grafana_admin_password.example secrets/grafana_admin_password
# Reemplaza el contenido por una contraseña larga y única.
docker compose -f compose.yaml --profile observability up -d --build
```

Usa `admin` o `GRAFANA_ADMIN_USER` como usuario y la contraseña de ese archivo.
Los endpoints internos son `GET /api/healthz` para el backend (comprueba SQLite
y PostgreSQL) y `GET /healthz` para el frontend. Docker los ejecuta cada 30
segundos; Alloy conserva sus líneas de acceso para que las alertas detecten una
sonda ausente. Las alertas quedan visibles en Grafana; para recibir mensajes
externos configura un contact point en Grafana (webhook, correo, Slack, etc.)
según el canal que uses.

### Sesiones JWT y refresh tokens

El login devuelve un JWT de acceso con duración de 15 minutos y un refresh
token opaco. El frontend conserva ambos sólo en memoria; cuando el JWT expira,
rota el refresh token mediante `POST /api/auth/refresh` y reintenta la llamada.
Cada refresh token se almacena únicamente como hash en PostgreSQL, se invalida
al rotarse y la reutilización de uno rotado revoca toda su familia de sesión.
El cierre de sesión revoca la sesión persistida de inmediato.

### Usuarios y contraseñas

Los usuarios se guardan en la tabla PostgreSQL `users`, con `username`,
`password_hash`, `salt`, `password_algorithm`, estado, rol y fechas de
creación/actualización. Las contraseñas no se guardan en un gestor de secretos:
se derivan con Argon2id y sólo se persisten su hash y salt. El gestor de
secretos se reserva para credenciales de infraestructura, como el secreto JWT
y la contraseña de PostgreSQL.

Al iniciar, los usuarios existentes en el antiguo `backend/data/users.json`
se copian una sola vez a PostgreSQL conservando sus hashes PBKDF2. Tras su
primer inicio de sesión correcto, cada uno se actualiza automáticamente a
Argon2id; el JSON deja de usarse para autenticar y puede archivarse cuando
todos los usuarios hayan iniciado sesión.

Las rutas protegidas verifican la firma HS256, vencimiento, emisor, audiencia y
que la sesión aún no esté revocada en PostgreSQL. Por eso reiniciar FastAPI no
invalida sesiones ni JWT válidos. Rotar `secrets/jwt_secret` sí invalida todos
los JWT y debe hacerse de forma planificada. La contraseña de PostgreSQL se
lee sólo durante la inicialización del volumen: para rotarla, primero cambia
la contraseña del rol dentro de PostgreSQL, actualiza el secreto y después
reinicia los servicios.

### Límites de abuso

FastAPI rechaza cuerpos de solicitud de más de 1 MiB (`413`). El login admite
como máximo cinco intentos por IP cada 60 segundos y bloquea durante 15 minutos
la combinación usuario+IP después de cinco credenciales inválidas. Las
respuestas bloqueadas usan `429` e incluyen `Retry-After`.

Puedes ajustar estos valores en `.env` mediante `MAX_REQUEST_BODY_BYTES`,
`LOGIN_RATE_LIMIT_ATTEMPTS`, `LOGIN_RATE_LIMIT_WINDOW_SECONDS`,
`LOGIN_LOCKOUT_FAILURES` y `LOGIN_LOCKOUT_SECONDS`. En varias réplicas del
backend estos límites en memoria no se comparten: para ese escenario usa un
almacenamiento común como Redis y aplica además límites en el proxy perimetral.

### Building for Production

```bash
cd frontend
npm run build
```

To preview the production build locally:

```bash
cd frontend
npm run preview
```

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and Oxlint's TypeScript related rules in your project.
