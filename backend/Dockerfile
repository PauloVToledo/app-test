FROM python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# La API sólo requiere leer código, secretos y datos heredados. Evitar root
# limita el impacto de una vulnerabilidad en el proceso de la aplicación.
RUN addgroup --system taskflow && adduser --system --ingroup taskflow taskflow
COPY --chown=taskflow:taskflow app ./app
COPY --chown=taskflow:taskflow create_user.py ./

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER taskflow

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
