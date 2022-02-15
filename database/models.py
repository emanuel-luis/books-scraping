from sqlalchemy.engine import Engine
from sqlalchemy import Column, Float, Integer, String
from sqlalchemy.ext.declarative import declarative_base


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)


Base = declarative_base()


class Book(Base):
    __tablename__ = 'book'

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    category = Column(String(255), nullable=False)
    price = Column(Float, nullable=False)
    stock = Column(Integer)
    rating = Column(Integer)
    
    def __repr__(self) -> str:
        return f'<Book(name={self.name}, category={self.category}, '\
            f'price={self.price}, stock={self.stock})>'
