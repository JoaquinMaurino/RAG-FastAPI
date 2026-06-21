import logging
import sys
from loguru import logger

class InterceptHandler(logging.Handler):
    """
    Este handler intercepta los logs estándar de Python (logging module)
    y los redirige hacia Loguru.
    
    Esto es necesario porque FastAPI, Uvicorn y SQLAlchemy usan el módulo
    `logging` por defecto. Si queremos que toda la consola tenga el mismo
    formato (colores, estructura), tenemos que "secuestrar" esos logs.
    """
    def emit(self, record: logging.LogRecord) -> None:
        # Busca a qué nivel de loguru corresponde este log
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Encuentra desde dónde se originó el log para mantener el nombre del módulo correcto
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )

def setup_logging():
    """
    Configura Loguru como el único logger de toda la aplicación.
    Se debe llamar al principio de main.py.
    """
    # 1. Quitamos la configuración por defecto de loguru
    logger.remove()

    # 2. Agregamos nuestro formato personalizado para consola (stdout)
    # Formato: [Fecha] | NIVEL | modulo:linea - Mensaje
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )
    logger.add(sys.stdout, format=log_format, level="INFO", colorize=True)

    # 3. Interceptamos los logs de Uvicorn y FastAPI
    logging.getLogger().handlers = [InterceptHandler()]
    
    # Reemplazamos los handlers de los loggers clave de Uvicorn
    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
        logging_logger = logging.getLogger(logger_name)
        logging_logger.handlers = [InterceptHandler()]
        # Evitamos que se dupliquen enviando al root logger
        logging_logger.propagate = False
