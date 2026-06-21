"""
Step 6: Generación de Embeddings con sentence-transformers.

Responsabilidad única: convertir texto en vectores numéricos.

¿Por qué está en services/ y no en rag/?
-----------------------------------------
Diferencia conceptual:

    rag/          → transformaciones puras de texto (extractor, chunker, retriever)
                    No dependen de modelos de ML ni de configuración externa.

    services/     → lógica que involucra recursos externos o estado.
                    El modelo de embeddings ES un recurso externo: pesa ~90 MB,
                    tarda ~2 segundos en cargar, y lo reutilizamos entre requests.

El embedding_service maneja ese recurso (el modelo) y lo expone
como un servicio reutilizable para el resto de la app.

Patrón Singleton — ¿por qué?
------------------------------
SentenceTransformer() carga el modelo desde disco a RAM:
    - Descarga el modelo (~90 MB) la primera vez
    - Lo deserializa en memoria (arrays de pesos)
    - Prepara el pipeline de tokenización

Esto tarda ~1-2 segundos. Si lo hiciéramos en cada request:
    - POST /documents con 100 chunks → 100 segundos solo de carga de modelo
    - Inaceptable en producción

Con Singleton: cargamos UNA VEZ al primer request y reutilizamos.
A partir del segundo request, get_embeddings_batch() tarda milisegundos.

¿Por qué no cargarlo en el lifespan startup de main.py?
Porque en desarrollo preferimos "lazy loading": el modelo solo se carga
cuando realmente se necesita (al primer upload). Así la app arranca rápido.
En producción podríamos cambiarlo a eager loading (en startup).

Nota sobre async y el event loop
----------------------------------
model.encode() es una operación CPU-bound (matemáticas de numpy/torch).
Ejecutarla directamente en un endpoint async BLOQUEA el event loop de
FastAPI mientras dura el cálculo, impidiendo atender otros requests.

En este step la dejamos así (síncrona) para mantener simplicidad.
En el Step 15 (Redis + workers) moveremos el procesamiento pesado a
workers en background, resolviendo este problema correctamente.
"""

from loguru import logger
from sentence_transformers import SentenceTransformer


# ── Configuración del modelo ──────────────────────────────────────────────────
# Modelo elegido: all-MiniLM-L6-v2
#   - 384 dimensiones de salida
#   - ~90 MB en disco
#   - Muy rápido (arquitectura MiniLM, 6 capas)
#   - Entrenado para similitud semántica en inglés
#   - Benchmark SBERT: score 68.07 en STS tasks
#
# Alternativas consideradas:
#   - all-mpnet-base-v2        → 768 dims, mejor calidad, ~420 MB (más pesado)
#   - paraphrase-multilingual  → 384 dims, soporta español, ~120 MB
#
# Para un proyecto educativo en inglés, all-MiniLM-L6-v2 es el balance ideal.
# Si el contenido de los PDFs es en español, cambiar a paraphrase-multilingual.
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384   # Número de dimensiones del vector de salida.
                              # Este valor DEBE coincidir con Vector(N) en chunk.py

# Singleton: referencia al modelo cargado.
# None = todavía no cargado. Se inicializa en la primera llamada.
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    """
    Devuelve la instancia del modelo, cargándola si todavía no existe.

    Es la única función que conoce el singleton. El resto del módulo
    usa _get_model() y nunca toca _model directamente.

    Thread safety: en un servidor ASGI (asyncio single-threaded) no hay
    riesgo de race condition. Si en el futuro usamos workers múltiples
    (gunicorn + uvicorn workers), cada proceso tiene su propio _model.
    """
    global _model
    if _model is None:
        logger.info(f"Loading embedding model '{EMBEDDING_MODEL_NAME}'...")
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        logger.info(
            f"Embedding model loaded: {EMBEDDING_MODEL_NAME} "
            f"({EMBEDDING_DIMENSIONS} dimensions)"
        )
    return _model


def get_embedding(text: str) -> list[float]:
    """
    Genera el embedding de un único texto.

    Útil para:
    - Embeber la pregunta del usuario al momento de la búsqueda (Step 8)
    - Tests unitarios

    Args:
        text: El texto a embeber.

    Returns:
        Lista de EMBEDDING_DIMENSIONS floats que representa el texto
        en el espacio vectorial del modelo.
    """
    model = _get_model()
    # normalize_embeddings=True: normaliza el vector a longitud unitaria (norma = 1).
    # Efecto: convierte cosine similarity en simple producto punto (<-> en pgvector).
    # Beneficio: el operador <-> de pgvector es más eficiente con vectores normalizados.
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """
    Genera embeddings para una lista de textos en una sola operación.

    ¿Por qué batch y no llamar get_embedding() N veces?
    ----------------------------------------------------
    sentence-transformers está optimizado para batch processing:
    - Procesa múltiples textos en paralelo (internamente usa numpy batching)
    - Una llamada con 100 chunks es ~10x más rápida que 100 llamadas individuales
    - El modelo tokeniza todos los textos juntos y hace una sola pasada forward

    Args:
        texts: Lista de strings a embeber. Puede estar vacía (devuelve []).

    Returns:
        Lista de listas de floats. El índice i de la salida corresponde
        al texto i de la entrada (orden preservado).
    """
    if not texts:
        return []

    model = _get_model()
    logger.info(f"Generating embeddings for {len(texts)} chunks...")

    # show_progress_bar=False: evita output en consola durante requests HTTP
    vectors = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    logger.info(f"Embeddings generated. Shape: {vectors.shape}")
    # vectors es un numpy array de shape (len(texts), EMBEDDING_DIMENSIONS)
    # .tolist() lo convierte a list[list[float]] que SQLAlchemy/pgvector entiende
    return vectors.tolist()
