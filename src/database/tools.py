from typing import TypeVar
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
    query: dict = {}

    @classmethod
    @commit
    def create(cls, *objects) -> None:
        for obj in objects:
            new_object = (cls(**obj)
                          if isinstance(obj, dict)
                          else cls(objects))
            
            session.add(new_object)
        print(f'[LOG] Created {len(objects)} rows into {cls.__tablename__}.')

    @classmethod
    def read(cls, *, where: dict = {}):

        query = session.query(cls)

        for key, value in where.items():
            query = query.filter(getattr(cls, key) == value)

        query = query.all()

        if not where:
            cls.query = query

        return query

    @classmethod
    @commit
    def update(cls, *, where: dict, **kwargs) -> None:
        objects = cls.read(where=where)

        if not objects:
            print('[LOG] Tried to update a non-existent'
                  f'row from {cls.__tablename__}')
            return

        for obj in objects:
            for key, value in kwargs.items():
                setattr(obj, key, value)

        print(f'[LOG] Updated {len(objects)} '
              f'items from {cls.__tablename__}')

    @classmethod
    @commit
    def delete(cls, *, where: dict) -> None:
        objects = cls.read(where=where)
        for obj in objects:
            session.delete(obj)
        print(f'[LOG] Deleting {len(objects)} rows'
              f' from {cls.__tablename__}...')
