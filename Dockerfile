# ──────────────────────────────────────────────
# Stage 1 – Build
# ──────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Copiar manifiestos primero → mejor uso de cache de capas
COPY package.json package-lock.json ./
RUN npm ci --frozen-lockfile

# Copiar el resto del código fuente
COPY . .

# Generar bundle de producción en /app/dist
RUN npm run build

# ──────────────────────────────────────────────
# Stage 2 – Serve
# ──────────────────────────────────────────────
FROM nginx:stable-alpine AS runner

# Limpiar página de bienvenida por defecto
RUN rm -rf /usr/share/nginx/html/*

# Copiar el build estático desde stage anterior
COPY --from=builder /app/dist /usr/share/nginx/html

# Configuración personalizada de Nginx (SPA + gzip + cache)
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
