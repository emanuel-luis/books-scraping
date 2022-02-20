import scrapping
from alive_progress import alive_bar
import database as db

with alive_bar(1000) as bar:
    for book in scrapping.get_books():
        w = {'name': book.name, 'category': book.category}

        query = db.read(where=w)
        if len(query) == 0:
            db.create(**book)
        # else:
            # db.update(where=w, **book)
        
        bar()

def main():
    
    pass
if __name__ == '__main__':
    main()