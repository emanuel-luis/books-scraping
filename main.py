from src import Book, Category, Scrapper


def main():
    scrapper = Scrapper()
    Category.handler(*scrapper.categories)
    Book.handler(*scrapper.books)


if __name__ == '__main__':
    main()
