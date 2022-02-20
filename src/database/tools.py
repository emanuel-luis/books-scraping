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
        try:
            func(*args, **kwargs)
            session.commit()
        except Exception as e:
            print(f'[LOG] Failed while running {func.__name__}.')
            print(f'\t---> {e}')

    return wrapped


class Table:
    @classmethod
    @commit
    def create(cls, *objects) -> None:
        t = f'[DATABASE] Adding {len(objects)} object(s) ' \
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

        t = f'[DATABASE] Updating {len(objects)} object(s) ' \
            f'from {cls.__tablename__} table...'

        if not objects:
            print('[LOG] Tried to update a non-existent'
                  f'row from {cls.__tablename__}')
            return

        for obj in alive_it(objects, title=t):
            for key, value in kwargs.items():
                setattr(obj, key, value)

    @classmethod
    @commit
    def delete(cls, *, where: dict) -> None:
        objects = cls.read(where=where)

        t = f'[DATABASE] Deleting {len(objects)} object(s) ' \
            f'from {cls.__tablename__} table...'
        for obj in alive_it(objects, title=t):
            session.delete(obj)
