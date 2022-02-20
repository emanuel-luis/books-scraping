from sqlalchemy.orm import relationship
from sqlalchemy import Column, Float, ForeignKey, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm.decl_api import DeclarativeMeta

from .tools import Table

Base: DeclarativeMeta = declarative_base()


class Book(Base, Table):
    __tablename__ = 'Book'

    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey('Category.id'))
    name = Column(String(255))
    category = relationship('Category', backref='Category.name',
                            primaryjoin='Book.category_id==Category.id')
    price = Column(Float, nullable=False)
    stock = Column(Integer)
    rating = Column(Integer)
    description = Column(String(1700))

    def __repr__(self) -> str:
        return f'<Book(name={self.name}, category={self.category}, price={self.price}, stock={self.stock}, rating={self.rating}, description={self.description[:25]}...)>'

    @classmethod
    def handler(cls, *objects: dict):
        query = cls.to_tuple()
        to_create = []

        for obj in objects:
            category = obj.get('category')
            del obj['category']

            category_id = obj['category_id'] = Category.mapping[category]
            name = obj.get('name')

            if (name, category_id) in query:
                cls.update(where=dict(name=name, category_id=category_id),
                           **obj)
            else:
                to_create.append(obj)

        cls.create(*to_create)

    @classmethod
    def to_tuple(cls):
        query = cls.read()
        return [(book.name, book.category) for book in query]


class Category(Base, Table):
    __tablename__ = 'Category'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True)

    def __repr__(self) -> str:
        return f'<Category(name={self.name})>'

    @classmethod
    def handler(cls, *objects):
        query = cls.to_list()
        cls.create(*filter(lambda o: o['name'] not in query, objects))

    @classmethod
    def to_list(cls):
        return [category.name 
                for category in cls.query or cls.read()]

    @classmethod
    @property
    def mapping(cls):
        return {category.name: category.id 
                for category in cls.query or cls.read()}
