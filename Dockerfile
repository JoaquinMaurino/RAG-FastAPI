# ============================================
# Dockerfile para la API
# ============================================
# Una imagen Docker es como una "foto" de un sistema operativo
# con todo lo necesario para correr tu aplicación.

# Partimos de una imagen base con Python 3.12 ya instalado.
# "slim" = versión reducida de Debian (más liviana, ~150MB vs ~900MB).
FROM python:3.12-slim

# Directorio de trabajo DENTRO del contenedor.
# Todos los comandos siguientes se ejecutan desde acá.
WORKDIR /app

# Copiamos SOLO el requirements.txt primero.
# ¿Por qué? Docker cachea cada paso. Si el requirements.txt no cambió,
# no reinstala las dependencias (ahorra minutos en cada build).
COPY requirements.txt .

# Instalamos las dependencias.
# --no-cache-dir = no guarda cache de pip (reduce tamaño de la imagen)
RUN pip install --no-cache-dir -r requirements.txt

# Ahora copiamos el resto del código.
# Si solo cambiaste código (no dependencias), Docker reutiliza el
# cache del paso anterior y solo recopia los archivos.
COPY . .

# El puerto donde escucha Uvicorn.
EXPOSE 8000

# Comando que se ejecuta cuando el contenedor arranca.
# uvicorn app.main:app
#   ↑       ↑      ↑
#   │       │      └── Variable "app" dentro de main.py (la instancia de FastAPI)
#   │       └── Archivo app/main.py
#   └── ASGI server
#
# --host 0.0.0.0 = Escucha en todas las interfaces (necesario dentro de Docker)
# --port 8000    = Puerto
# --reload       = Reinicia automáticamente cuando cambiás código (solo para dev)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
