# ──────────────────────────────────────────────
# Stage 1 – Build
# ──────────────────────────────────────────────
FROM node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293 AS builder

WORKDIR /app

# Copiar manifiestos primero → mejor uso de cache de capas
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Copiar el resto del código fuente
COPY frontend/ ./

# Generar bundle de producción en /app/dist
RUN npm run build

# ──────────────────────────────────────────────
# Stage 2 – Serve
# ──────────────────────────────────────────────
FROM nginx:stable-alpine@sha256:97d490c12ba55b4946b01546d1c3ed324e8d41ab1c9fcb2a616aa470620e5b46 AS runner

# Limpiar página de bienvenida por defecto
RUN rm -rf /usr/share/nginx/html/*

# Copiar el build estático desde stage anterior
COPY --from=builder /app/dist /usr/share/nginx/html

# Configuración personalizada de Nginx (SPA + gzip + cache)
COPY infra/proxy/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
