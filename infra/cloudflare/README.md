# Límites perimetrales de Cloudflare

`rate-limits.tf` declara la protección distribuida de las dos rutas anónimas:

- `POST /api/auth/login`: 5 solicitudes por IP y minuto, mitigación de 15
  minutos.
- `POST /api/telemetry/frontend-errors`: 30 solicitudes por IP y minuto,
  mitigación de un minuto.

La respuesta de bloqueo es `429` y los contadores viven en Cloudflare, por lo
que sobreviven a reinicios del backend y son comunes a todas las réplicas.

## Aplicación segura

1. En Cloudflare deja el registro de `TASKFLOW_DOMAIN` en **Proxied** (nube
   naranja) y restringe el firewall de origen a los rangos de
   <https://www.cloudflare.com/ips>.
2. Exporta `CLOUDFLARE_API_TOKEN` con permisos **Zone WAF Write** y define
   `TF_VAR_cloudflare_zone_id`. No guardes el token ni el zone ID en Git.
3. Desde esta carpeta ejecuta `terraform init`, `terraform plan` y revisa que
   sólo se gestione la fase `http_ratelimit` de esta zona. Después ejecuta
   `terraform apply`.

Cloudflare sólo permite un ruleset de entrada por zona y fase. Terraform toma
propiedad completa de esa fase: si ya existen reglas de rate limiting, impórtalas
o intégralas en `rate-limits.tf` antes de aplicar.

## Prueba de aceptación después del proxy

Con el origen no accesible desde Internet, lanza 6 intentos de login en menos
de 60 segundos desde una misma IP pública. La sexta respuesta debe ser `429`
de Cloudflare y el log del backend debe contener como máximo cinco solicitudes.
Para telemetría, repite con 31 envíos. Haz una segunda prueba con otra IP
pública o una conexión móvil: debe disponer de su propio contador. Conserva el
evento de Cloudflare y los logs del backend como evidencia del despliegue.

## Escalamiento

Cloudflare es la protección primaria. Los límites en memoria de FastAPI se
mantienen como defensa local; antes de ejecutar más de una réplica, migra esos
contadores a Redis mediante operaciones atómicas con TTL. PostgreSQL es una
alternativa si no se opera Redis, pero no es la primera opción para el camino
caliente de autenticación.
