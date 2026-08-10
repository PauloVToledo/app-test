# Backend — TaskFlow

## Organización

- `app/main.py`: aplicación FastAPI, modelos, endpoints e inicialización.
- `tests/`: pruebas unitarias y de integración del servicio.
- `data/`: SQLite y archivos de migración heredados generados localmente; no
  se versionan.
- `create_user.py`: script para crear o actualizar usuarios en PostgreSQL.

El módulo se ejecuta como `app.main:app`. No muevas los datos al paquete
`app/`: `backend/data/` es el límite persistente y en Docker se monta como
`/app/data`.

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

Todo cambio de API debe conservar una migración compatible para SQLite y
probar el CRUD autenticado: crear (`201`), listar, actualizar y eliminar
(`204`).
