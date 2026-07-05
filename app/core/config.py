"""
Configuración centralizada de la aplicación.

¿Por qué Pydantic Settings?
--------------------------
En vez de hacer `os.getenv("DATABASE_URL")` en cada archivo (propenso a errores,
sin validación, sin tipos), centralizamos TODA la configuración en una sola clase.

Pydantic Settings hace 3 cosas:
1. Lee las variables de entorno (o un archivo .env)
2. Las valida (si DATABASE_URL no existe, la app NO arranca en vez de fallar después)
3. Les da tipos (str, bool, int) para que tu IDE te autocomplete

¿Cómo funciona?
---------------
Cuando hacés `settings = Settings()`, Pydantic automáticamente:
1. Busca un archivo .env en la raíz del proyecto
2. Lee las variables definidas ahí
3. Las mapea a los atributos de la clase por NOMBRE (case insensitive)
   Ejemplo: DATABASE_URL en .env → database_url en la clase

Si una variable obligatoria falta, lanza un error claro al arrancar.
"""

from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Cada atributo de esta clase corresponde a una variable de entorno.
    
    Ejemplo:
        En .env:     DATABASE_URL=postgresql+asyncpg://...
        En Python:   settings.database_url → "postgresql+asyncpg://..."
    """

    # --- Database ---
    database_url: str
    # No tiene valor por defecto → es OBLIGATORIA.
    # Si no existe en .env, la app explota al arrancar (y eso es bueno,
    # mejor fallar rápido que descubrirlo cuando un usuario hace una query).

    # --- Application ---
    app_name: str = "RAG FastAPI"
    # Tiene valor por defecto → es OPCIONAL.
    # Si no está en .env, usa "RAG FastAPI".

    debug: bool = False
    # Pydantic convierte automáticamente el string "true" a True (bool).

    # --- Storage ---
    upload_dir: str = "uploads"
    # Carpeta donde se guardan los archivos subidos por los usuarios.
    # Relativa a la raíz del proyecto (donde corre uvicorn).

    # --- LLM (Gemini) ---
    gemini_api_key: str
    # API key de Google Gemini. Obligatoria para el endpoint /chat.
    # Se obtiene gratis en https://aistudio.google.com/apikey

    gemini_model: str = "gemini-2.0-flash"
    # Modelo a usar. gemini-2.0-flash es rápido, barato y tiene free tier.
    # Alternativas: gemini-2.5-flash (más inteligente), gemini-2.5-pro (mejor calidad).

    # --- LLM Provider ---
    llm_provider: Literal["gemini", "ollama"] = "gemini"
    # Selecciona el proveedor de LLM. Gemini usa la API de Google,
    # Ollama permite testear localmente con modelos open-source sin gastar cuota.

    # --- Ollama (solo cuando LLM_PROVIDER=ollama) ---
    ollama_model: str = "llama3.2"
    ollama_base_url: str = "http://localhost:11434"

    # --- Memory ---
    memory_strategy: Literal["none", "sliding", "summary", "vector", "hybrid"] = "none"
    memory_sliding_window_size: int = 10
    memory_vector_top_k: int = 5
    memory_summary_threshold: int = 20
    memory_max_context_tokens: int = 2000

    # --- Multi-Query Retrieval ---
    multi_query_enabled: bool = False
    # Activar agrega latencia (~1 LLM call extra) y mejora el recall.
    # Medir el trade-off con el eval framework (Fase 4) antes de activar en producción.
    multi_query_n: int = 3
    # Número de variantes a generar. 3 es un buen balance entre cobertura y costo.

    # --- Hybrid Search (Phase 2.2) ---
    search_mode: Literal["hybrid", "semantic_only", "lexical_only"] = "hybrid"
    # hybrid: semántico + BM25 fusionados con RRF (Reciprocal Rank Fusion).
    # semantic_only: solo búsqueda vectorial (comportamiento pre-2.2).
    # lexical_only: solo full-text search (útil para debug y tests).
    hybrid_rrf_k: int = 60
    # Parámetro k de RRF. Valor clásico de la literatura: 60.
    # Controla cuánto peso tienen los top ranks vs los intermedios.
    # Un k mayor aplana las diferencias entre posiciones.

    # --- Configuración de Pydantic Settings ---
    model_config = SettingsConfigDict(
        env_file=".env",          # Archivo de donde leer las variables
        env_file_encoding="utf-8",
        case_sensitive=False,      # DATABASE_URL == database_url
    )


# Singleton: una sola instancia de Settings para toda la app.
# Se crea al importar este módulo por primera vez.
settings = Settings()
