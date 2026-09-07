# Portal del Observatorio Nacional de IA - Universidad de Cartagena
# Imagen minima: Node 22 con SQLite integrado, sin dependencias externas.
FROM node:22-alpine

ENV NODE_ENV=production \
    TZ=America/Bogota \
    PUERTO=8100 \
    RUTA_BD=/app/datos/portal.sqlite

RUN addgroup -S portal && adduser -S -G portal -u 10010 portal
WORKDIR /app
COPY --chown=portal:portal package.json ./
COPY --chown=portal:portal src ./src
RUN mkdir -p /app/datos && chown -R portal:portal /app/datos
VOLUME ["/app/datos"]

USER portal
EXPOSE 8100

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8100/salud >/dev/null || exit 1

CMD ["node", "--no-warnings", "src/server.js"]
