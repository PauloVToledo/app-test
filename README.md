# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

## Getting Started

### Prerequisites

- [Node.js](https://nodejs.org/) (v18 or higher recommended)
- npm (included with Node.js)

### Installation

Clone the repository and install the dependencies:

```bash
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

TaskFlow incluye una API FastAPI, SQLite y autenticación con usuario y
contraseña. Para el entorno local se requiere Python 3.10 o superior.

Antes de iniciar la API, crea el primer usuario. El archivo resultante
`backend/data/users.json` contiene únicamente hashes de contraseña y está
ignorado por Git:

```bash
python backend/create_user.py --username admin
```

El script pide la contraseña de forma interactiva. Para automatizaciones, usa
la variable de entorno temporal `TASKFLOW_CREATE_USER_PASSWORD`; no la
incluyas en archivos versionados.

Inicia el backend en una terminal:

```bash
python -m pip install -r backend/requirements.txt
python -m uvicorn app:app --app-dir backend --reload --port 8000
```

Después, en otra terminal, inicia el frontend:

```bash
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser to see the app running.
Vite redirige las llamadas a `/api` hacia el backend local. Las tareas se
guardan en `backend/data/taskflow.db` y cada usuario solo puede acceder a sus
propias tareas. La sesión se mantiene únicamente en memoria del navegador.

### Ejecutar con Docker

El despliegue Docker usa Caddy como proxy TLS. Caddy solicita y renueva el
certificado HTTPS automáticamente mediante ACME; el backend y Nginx no se
publican directamente. Antes de iniciar, crea `.env` a partir de la plantilla
y configura un nombre DNS público que ya apunte a la IP del servidor:

```bash
cp .env.example .env
# Edita .env: TASKFLOW_DOMAIN=tasks.tu-dominio.com
```

Los puertos TCP 80 y 443 deben estar abiertos hacia el servidor y no pueden
estar ocupados por otro proxy. Después inicia el stack:

```bash
docker compose up --build
```

Abre `https://<TASKFLOW_DOMAIN>`. Las peticiones HTTP se redirigen a HTTPS y
las respuestas HTTPS incluyen HSTS (`max-age=31536000; includeSubDomains`). No
actives este despliegue con un dominio temporal ni habilites subdominios que no
puedan usar HTTPS: los navegadores recordarán esa política durante un año.

El backend no publica un puerto hacia el host y el frontend solo es accesible
para Caddy dentro de Docker. Para crear un usuario en Docker:

```bash
docker compose exec backend python create_user.py --username admin
```

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
npm run build
```

To preview the production build locally:

```bash
npm run preview
```

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and Oxlint's TypeScript related rules in your project.
