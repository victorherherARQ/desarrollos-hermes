# ──────────────────────────────────────────────────────────────────
# Client Mock — Mobile UI for CIBA push notifications
# ──────────────────────────────────────────────────────────────────
FROM node:18-alpine

# Crear directorio de la app
WORKDIR /app

# Instalar dependencias primero (mejor cacheo de capas)
COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund

# Copiar el resto del código
COPY server.js ./
COPY public ./public

# Variables de entorno
ENV NODE_ENV=production \
    PORT=3000

# Exponer puerto
EXPOSE 3000

# Arrancar
CMD ["node", "server.js"]