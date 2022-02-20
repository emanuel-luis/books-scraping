from src import Book, Category, Scrapper


def main():
    library = Scrapper()
    Category.handler(*library.categories)
    Book.handler(*library)


if __name__ == '__main__':
    main()
