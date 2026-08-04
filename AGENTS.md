# Guía para agentes — TaskFlow

## Propósito y arquitectura

TaskFlow es una aplicación de tareas con:

- Frontend React 19 + Vite en `src/`.
- API FastAPI + SQLite en `backend/`.
- Nginx como servidor del frontend y proxy inverso en Docker.

El frontend siempre debe consumir la API mediante la ruta relativa
`/api/tasks`. No introducir URLs absolutas del backend en el código cliente:
Vite resuelve esa ruta en desarrollo y Nginx la resuelve en Docker.

## Áreas del repositorio

| Ruta | Responsabilidad |
| --- | --- |
| `src/App.jsx` | Estado de UI, peticiones HTTP y CRUD de tareas. |
| `src/index.css` | Estilos de la interfaz. |
| `backend/app.py` | Modelos Pydantic, endpoints, acceso SQLite e inicialización. |
| `backend/data/` | Datos locales generados en ejecución; no versionar. |
| `vite.config.js` | Proxy de desarrollo de `/api` a FastAPI. |
| `nginx.conf` | Fallback SPA y proxy de producción a `backend:8000`. |
| `docker-compose.yml` | Orquestación de frontend y backend. |

## Contrato de la API

Conservar el contrato actual al modificar cliente o servidor:

- `GET /api/tasks` devuelve una lista de tareas.
- `POST /api/tasks` crea una tarea y devuelve `201`.
- `PUT /api/tasks/{task_id}` reemplaza una tarea existente.
- `DELETE /api/tasks/{task_id}` devuelve `204`.
- Una tarea usa: `id`, `title`, `description`, `priority`, `status` y
  `dueDate`.
- Valores permitidos: `priority`: `low`, `medium`, `high`; `status`: `todo`,
  `in_progress`, `completed`.
- Todas las rutas de tareas requieren `Authorization: Bearer <token>`.
- `POST /api/auth/login` recibe `username` y `password`, y devuelve
  `accessToken`, `refreshToken` y `expiresIn`. `POST /api/auth/refresh` rota
  un `refreshToken`; `POST /api/auth/logout` invalida la sesión actual.

En Python el campo interno es `due_date`; Pydantic expone y acepta `dueDate`
mediante alias. No cambiar ese alias sin actualizar el frontend y documentar
una migración.

`dueDate` llega inicialmente desde un `<input type="date">`, que puede enviar
una cadena vacía. Al trabajar en validación o formularios, normalizarla antes
de enviarla o permitirla explícitamente en el modelo para evitar respuestas
`422`.

## Desarrollo local

Instalar dependencias del frontend y ejecutarlo:

```powershell
npm install
npm run dev
```

El Python local confirmado es `C:\Users\paulo\AppData\Local\Programs\Python\Python313\python.exe`.
`python` y `py` pueden no estar disponibles en `PATH`; usar la ruta completa
hasta que se corrija el entorno:

```powershell
& 'C:\Users\paulo\AppData\Local\Programs\Python\Python313\python.exe' -m pip install -r backend/requirements.txt
& 'C:\Users\paulo\AppData\Local\Programs\Python\Python313\python.exe' backend/create_user.py --username admin
& 'C:\Users\paulo\AppData\Local\Programs\Python\Python313\python.exe' -m uvicorn app:app --app-dir backend --reload --port 8000
```

Con ambos servicios activos, Vite sirve el frontend en `http://localhost:5173`
y redirige `/api` a `http://127.0.0.1:8000`.

## Docker

Para el entorno integrado:

```powershell
docker compose up --build
```

El frontend se publica en el dominio HTTPS configurado y la documentación de
la API está en `/api`; el backend no se publica directamente en el host. Las
tareas y el archivo local de usuarios se persisten mediante el volumen
`./backend/data:/app/data`; PostgreSQL usa el volumen Docker `postgres_data`
para las sesiones de refresh.

## Verificación antes de entregar

Después de cambios de frontend, ejecutar:

```powershell
npm run lint
npm run build
```

Después de cambios de API, comprobar al menos el ciclo CRUD contra
`/api/tasks`: crear (`201`), listar, actualizar y eliminar (`204`). Para
cambios en la integración, comprobar además una petición a través del proxy de
Vite; y si Docker está disponible, ejecutar el stack compuesto.

## Convenciones de cambio

- Mantener el idioma de interfaz en español y los nombres de valores de API en
  inglés, tal como el contrato existente.
- Preferir cambios pequeños y compatibles. Si se modifica el esquema SQLite,
  añadir una migración compatible en `initialize_database()` o explicar cómo
  se preservan los datos existentes.
- No versionar `backend/data/`, archivos `*.db`, `node_modules/` ni `dist/`.
- No modificar archivos generados ni credenciales locales.
- Actualizar `README.md` cuando cambien comandos de ejecución, puertos,
  variables de entorno, endpoints o el flujo Docker.
