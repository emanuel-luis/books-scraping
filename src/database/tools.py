from typing import TypeVar
from alive_progress import alive_bar, alive_it
import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import sqlalchemy.orm.session

engine = create_engine(f'sqlite:///library.db', echo=False)
session: sqlalchemy.orm.session.Session = sessionmaker(bind=engine).__call__()
Self = TypeVar("Self", bound="Table")


def commit(func):
    def wrapped(*args, **kwargs):
        func(*args, **kwargs)
        session.commit()

    return wrapped


class Table:
    @classmethod
    @commit
    def create(cls, *objects) -> None:
        if not objects:
            return

        t = f'Adding {len(objects)} object(s) ' \
            f'into {cls.__tablename__} table...'
        for obj in alive_it(objects, title=t):
            new_object = (cls(**obj)
                          if isinstance(obj, dict)
                          else cls(objects))

            session.add(new_object)

    @classmethod
    def read(cls, *, where: dict = {}):
        query = session.query(cls)

        for key, value in where.items():
            query = query.filter(getattr(cls, key) == value)

        return query.all()

    @classmethod
    @commit
    def update(cls, *, where: dict, **kwargs) -> None:
        objects = cls.read(where=where)

        if not objects:
            print('Tried to update a non-existent'
                  f'row from {cls.__tablename__}')
            return

        for obj in objects:
            for key, value in kwargs.items():
                setattr(obj, key, value)

    @classmethod
    @commit
    def delete(cls, *, where: dict) -> None:
        objects = cls.read(where=where)

        if not objects:
            print('Tried to delete a non-existent'
                  f'row from {cls.__tablename__}')
            return

        t = f'Deleting {len(objects)} object(s) ' \
            f'from {cls.__tablename__} table...'
        for obj in alive_it(objects, title=t):
            session.delete(obj)
