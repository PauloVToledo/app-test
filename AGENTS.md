# Mapa del proyecto — TaskFlow

TaskFlow es un monorepo de un gestor de tareas. La interfaz es React/Vite, la
API es FastAPI, las tareas se persisten en SQLite y la autenticación/sesiones
en PostgreSQL. La entrada pública es Caddy; Nginx entrega la SPA y reenvía
`/api/` al servicio backend.

## Mapa estable

| Ruta                | Responsabilidad                                                               |
| ------------------- | ----------------------------------------------------------------------------- |
| `frontend/`         | Aplicación web React, configuración Vite y su imagen de entrega.              |
| `backend/`          | Servicio FastAPI, scripts operativos, pruebas y datos locales no versionados. |
| `infra/proxy/`      | Configuración de Caddy y Nginx para el tráfico del stack.                     |
| `infra/monitoring/` | Configuración declarativa de Loki, Alloy y Grafana.                           |
| `compose.yaml`      | Orquestación de servicios, volúmenes, secretos y perfiles.                    |
| `secrets/`          | Secretos locales montados por Compose; no se versionan.                       |

## Límites invariables

- El cliente consume la API mediante rutas relativas `/api/...`; no usa URLs
  absolutas del backend.
- El servicio `frontend` sólo es accesible desde `caddy`; el servicio
  `backend` no publica puertos en el host.
- Las tareas, usuarios y sesiones se guardan en PostgreSQL mediante el volumen
  Docker `postgres_data`; `backend/data/` sólo conserva fuentes heredadas de
  una migración de una sola lectura.
- Los contratos HTTP, datos persistentes y secretos se cambian sólo con una
  migración/documentación explícita.

Lee el `AGENTS.md` del área que vayas a cambiar para las reglas de desarrollo,
pruebas y compatibilidad de ese componente.

## Política de contexto

- Empieza por el área directamente afectada por la tarea.
- Lee primero el `AGENTS.md` más cercano antes de explorar archivos del componente.
- No explores otros subsistemas salvo que exista una dependencia relevante para la tarea.
- No inspecciones directorios generados, dependencias instaladas, datos locales, logs o artefactos de build salvo que la tarea los requiera explícitamente.
