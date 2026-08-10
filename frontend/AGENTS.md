# Frontend — TaskFlow

## Alcance

`src/` contiene la UI React 19; `public/` contiene activos estáticos;
`vite.config.js` configura el desarrollo; `Dockerfile` genera y entrega el
bundle con Nginx. El archivo `infra/proxy/nginx.conf` se copia durante el build
de Docker, por lo que el contexto de build es la raíz del repositorio.

## Contrato con el backend

- Consumir exclusivamente rutas relativas `/api/...`.
- Mantener los valores de API en inglés: prioridades `low`, `medium`, `high` y
  estados `todo`, `in_progress`, `completed`; la UI continúa en español.
- Normalizar un `dueDate` vacío antes de enviarlo para no provocar un `422`.
- Los tokens viven sólo en memoria; no introducir persistencia local sin una
  revisión explícita de seguridad.

## Desarrollo y verificación

Ejecutar desde `frontend/`:

```powershell
npm install
npm run lint
npm run build
```

Vite sirve en `http://localhost:5173` y redirige `/api` a
`http://127.0.0.1:8000`. Conserva el fallback SPA, cabeceras y health check
`/healthz` de Nginx al modificar la entrega de producción.
