from .models import Book
from .setup import session


def create(log=True, **kwargs):
    book = Book(**kwargs)
    session.add(book)
    session.commit()
    if log:
        print(f'[CREATED] {book} has been inserted in database.')
    return book


def delete(*, where):
    query = read(where=where)
    for book in query:
        session.delete(book)
        print(f'[DELETED] {book} has been deleted from database.')
    
    session.commit()

def read(*, where):
    query = session.query(Book)
    for key, value in where.items():
        query = query.filter(getattr(Book, key) == value)
    
    return query.all()


def update(*, where: dict, **kwargs):
    query = read(where=where)
    for book in query:
        for key, value in kwargs.items():
            setattr(book, key, value)
        print(f'[UPDATED] {book} has been updated.')
    
    if len(query) == 0:
        print(f'[CREATED] created {create(log=False, **kwargs)} after trying to update a nonexistent row.')
    
    session.commit()
