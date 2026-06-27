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

    # --- Memory ---
    memory_strategy: Literal["none", "sliding", "summary", "vector", "hybrid"] = "none"
    memory_sliding_window_size: int = 10
    memory_vector_top_k: int = 5
    memory_summary_threshold: int = 20
    memory_max_context_tokens: int = 2000

    # --- Configuración de Pydantic Settings ---
    model_config = SettingsConfigDict(
        env_file=".env",          # Archivo de donde leer las variables
        env_file_encoding="utf-8",
        case_sensitive=False,      # DATABASE_URL == database_url
    )


# Singleton: una sola instancia de Settings para toda la app.
# Se crea al importar este módulo por primera vez.
settings = Settings()
