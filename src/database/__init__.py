from .models import Book, Category, Base
from .tools import engine

Base.metadata.create_all(engine)

__all__ = ['Book', 'Category']
