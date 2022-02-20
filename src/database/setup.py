import sqlalchemy.orm.session
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from .models import init_db
import os


name = 'books.db'
engine = create_engine(f'sqlite:///{name}', echo=False)
Session = sessionmaker(bind=engine)

curdir = os.path.dirname(os.path.realpath(__file__))

if not os.path.exists(f'{curdir}/{name}'):
    init_db(engine)

session:sqlalchemy.orm.session.Session = Session()