"""
Clase Base para todos los modelos SQLAlchemy.
"""

from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """
    Clase base para todos los modelos de SQLAlchemy.
    Todos nuestros modelos de base de datos heredarán de esta clase.
    Esto permite que SQLAlchemy sepa cuáles son todas nuestras tablas
    para poder crearlas.
    """
    pass
