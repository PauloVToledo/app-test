# Backend — TaskFlow

## Organización

- `app/main.py`: aplicación FastAPI, modelos, endpoints e inicialización.
- `tests/`: pruebas unitarias y de integración del servicio.
- `data/`: fuente heredada de una sola lectura para migrar SQLite/JSON; no se
  versiona ni se usa como persistencia en ejecución.
- `create_user.py`: script para crear o actualizar usuarios en PostgreSQL.

El módulo se ejecuta como `app.main:app`. Las tareas, usuarios y sesiones se
persisten en PostgreSQL (`postgres_data`). Al iniciar, la migración idempotente
importa `backend/data/taskflow.db` y `users.json` una única vez si existen;
después, ese directorio sólo se monta como `/legacy-data:ro`.

## Contrato HTTP

- `GET`, `POST`, `PUT`, `DELETE /api/tasks`; todas requieren `Bearer`.
- Una tarea contiene `id`, `title`, `description`, `priority`, `status` y
  `dueDate`. Internamente el modelo usa `due_date` y Pydantic expone el alias
  `dueDate`.
- `POST /api/auth/login`, `/refresh` y `/logout` conservan los nombres de
  campos camelCase documentados en el README.

## Desarrollo y verificación

Usar el Python confirmado:

```powershell
& 'C:\Users\paulo\AppData\Local\Programs\Python\Python313\python.exe' -m pip install -r requirements.txt
& 'C:\Users\paulo\AppData\Local\Programs\Python\Python313\python.exe' -m uvicorn app.main:app --reload --port 8000
& 'C:\Users\paulo\AppData\Local\Programs\Python\Python313\python.exe' -m unittest discover -s tests
```

Todo cambio de esquema debe ser compatible con PostgreSQL y conservar una
migración idempotente para instalaciones SQLite heredadas. Probar el CRUD
autenticado: crear (`201`), listar, actualizar y eliminar (`204`).
