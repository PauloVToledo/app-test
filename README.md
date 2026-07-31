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

Docker también permite ejecutar el frontend y el backend sin instalar Python:

```bash
docker compose up --build
```

Abre [http://localhost:5173](http://localhost:5173). El backend no publica un
puerto hacia el host en Docker: el frontend lo consume internamente mediante
Nginx. Para crear un usuario en Docker:

```bash
docker compose exec backend python create_user.py --username admin
```

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
