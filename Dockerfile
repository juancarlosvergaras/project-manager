# TecladoIA — imagen para el servidor.
#
# En el servidor no hay teclado: el Bluetooth no viaja por Internet. Esta copia
# corre con el teclado simulado y sirve para preparar reglas y teclas, ver la
# bitácora y descargar la aplicación para el equipo que sí lo tiene cerca.
#
# Por eso no se instala «bleak»: dentro de un contenedor no hay pila Bluetooth
# que valga, y añadirlo solo engordaría la imagen.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TECLADOIA_INICIO=/datos

WORKDIR /app

COPY pyproject.toml README.md LICENSE NOTICE ./
COPY src ./src
RUN pip install --no-cache-dir . && rm -rf /root/.cache

# Usuario propio: nada de correr como root.
RUN useradd --system --create-home --uid 10001 tecladoia \
 && mkdir -p /datos && chown -R tecladoia:tecladoia /datos /app
USER tecladoia

VOLUME ["/datos"]
EXPOSE 8770

# La clave llega por el entorno. El panel se niega a escuchar fuera de
# 127.0.0.1 sin ella, así que un despliegue mal configurado no arranca en vez
# de quedarse abierto de par en par.
ENV TECLADOIA_CLAVE=""

# Basta con comprobar que el panel sigue atendiendo. Pedir una pagina exigiria
# la clave, y un 401 no distingue «vivo» de «roto».
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import socket; socket.create_connection(('127.0.0.1',8770),4).close()"

CMD ["sh", "-c", "exec tecladoia servicio --sin-teclado --sin-tcp \
     --escuchar 0.0.0.0 --clave \"$TECLADOIA_CLAVE\""]
