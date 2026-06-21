"""
Conexión a PostgreSQL con SQLAlchemy Async.

=====================================================================
¿CÓMO FUNCIONA LA CONEXIÓN A POSTGRESQL?
=====================================================================

Para conectarte a PostgreSQL desde Python necesitás 3 cosas:

1. UN DRIVER (asyncpg)
   -----------------------
   Es la librería que "habla" el protocolo de PostgreSQL.
   Es como un traductor: convierte tus queries de Python a algo
   que PostgreSQL entiende, y viceversa.
   
   Hay varios drivers:
   - psycopg2     → Síncrono, el más clásico
   - asyncpg      → Asíncrono, el más rápido ← Lo usamos nosotros
   - psycopg3     → Síncrono + Async, más nuevo
   
   ¿Por qué async? Porque FastAPI es async. Si usás un driver síncrono,
   cada query BLOQUEA el event loop y tu API se vuelve lenta.

2. UN ORM (SQLAlchemy)
   -----------------------
   En vez de escribir SQL crudo:
       "SELECT * FROM documents WHERE id = 5"
   
   Escribís Python:
       session.query(Document).filter(Document.id == 5)
   
   SQLAlchemy traduce tu código Python a SQL automáticamente.
   También maneja conexiones, transacciones, migraciones, etc.

3. UNA URL DE CONEXIÓN (DATABASE_URL)
   -----------------------
   Formato: postgresql+asyncpg://usuario:password@host:puerto/base_datos
   
   Desglose de nuestra URL:
   
   postgresql+asyncpg://postgres:postgres@localhost:5432/rag_db
   │          │         │        │        │         │    │
   │          │         │        │        │         │    └── Nombre de la DB
   │          │         │        │        │         └── Puerto (5432 = default de PG)
   │          │         │        │        └── Host (localhost porque corre en Docker)
   │          │         │        └── Password
   │          │         └── Usuario
   │          └── Driver (asyncpg)
   └── Dialecto (postgresql)

=====================================================================
¿QUÉ ES UN ENGINE?
=====================================================================

El Engine es el punto central de conexión a la base de datos.
NO es una conexión individual — es una FÁBRICA de conexiones.

Internamente mantiene un "connection pool" (pileta de conexiones):
- En vez de abrir/cerrar una conexión por cada request (lento),
  mantiene varias conexiones abiertas y las reutiliza.
- Cuando tu código pide una conexión, el pool le da una disponible.
- Cuando tu código termina, la conexión vuelve al pool.

  Request 1 ──→ ┌─────────────────┐
  Request 2 ──→ │  Connection Pool │ ──→ PostgreSQL
  Request 3 ──→ │  (5-20 conns)    │
                └─────────────────┘

=====================================================================
¿QUÉ ES UNA SESSION?
=====================================================================

La Session es tu "ventana de trabajo" con la base de datos.
Representa una conversación con la DB:

    async with get_session() as session:
        # Acá estás "hablando" con la DB
        resultado = await session.execute(query)
        # Cuando salís del bloque, la session se cierra limpiamente

La session maneja transacciones automáticamente:
- Si todo sale bien → COMMIT (guarda los cambios)
- Si hay un error   → ROLLBACK (deshace todo)

=====================================================================
"""

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings


# =====================================================================
# 1. CREAR EL ENGINE (fábrica de conexiones)
# =====================================================================
engine = create_async_engine(
    settings.database_url,
    # ↑ Lee la URL desde nuestra config centralizada (.env)

    echo=False,
    # ↑ Cambiado a False para mantener la consola limpia.
    #   (Ignora settings.debug momentáneamente). 
    #   Si necesitás debugear una query puntual, ponelo en True.


    pool_size=5,
    # ↑ Mantiene 5 conexiones abiertas permanentemente.
    #   Es como tener 5 "líneas telefónicas" siempre listas.

    max_overflow=10,
    # ↑ Si las 5 conexiones están ocupadas, puede crear hasta 10 más
    #   temporalmente. Total máximo = pool_size + max_overflow = 15.
    #   Las extras se cierran cuando ya no se necesitan.
)

# =====================================================================
# 2. CREAR LA SESSION FACTORY
# =====================================================================
async_session_factory = async_sessionmaker(
    engine,
    # ↑ Le dice "usá este engine para conseguir conexiones"

    class_=AsyncSession,
    # ↑ Que las sessions sean async (para usar con await)

    expire_on_commit=False,
    # ↑ Después de hacer commit, los objetos siguen siendo accesibles.
    #   Sin esto, después de `session.commit()` no podrías leer
    #   los atributos del objeto sin hacer otra query.
    #   Ejemplo: después de crear un documento, querés devolver su ID.
)


# =====================================================================
# 3. DEPENDENCY INJECTION PARA FASTAPI
# =====================================================================
async def get_session() -> AsyncSession:
    """
    Genera una session de base de datos para cada request.
    
    ¿Cómo se usa? Con FastAPI Dependency Injection:
    
        @app.get("/ejemplo")
        async def mi_endpoint(session: AsyncSession = Depends(get_session)):
            resultado = await session.execute(...)
            return resultado
    
    FastAPI automáticamente:
    1. Llama a get_session() antes de tu endpoint
    2. Le pasa la session a tu función
    3. Cuando tu endpoint termina, continúa el generator (cierra la session)
    
    El "yield" es clave:
    - Todo ANTES del yield se ejecuta ANTES del endpoint
    - Todo DESPUÉS del yield se ejecuta DESPUÉS del endpoint (cleanup)
    
    Es como un try/finally automático:
        session = async_session_factory()  # Antes
        try:
            yield session                  # Tu endpoint usa la session
        finally:
            await session.close()          # Después (siempre se ejecuta)
    """
    async with async_session_factory() as session:
        yield session
