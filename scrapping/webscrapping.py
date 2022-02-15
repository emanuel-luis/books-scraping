from bs4 import BeautifulSoup
import requests
import re
import os

curdir = os.path.dirname(os.path.realpath(__file__))


def euro_rating():
    with open(f'{curdir}/utils/.api_key', encoding='utf-8') as file:
        api_key = file.read()

    url = f"""\
        http://api.currencylayer.com/live\
        ?access_key={api_key}\
        &currencies=EUR, BRL, USD\
        &format=1""".replace(' ', '')

    request = requests.get(url)
    json = request.json()
    quotes = json['quotes']

    return quotes['USDBRL'] / quotes['USDEUR']


EUR_RATING = euro_rating()
RATE_MAP = {
    'One': 1,
    'Two': 2,
    'Three': 3,
    'Four': 4,
    'Five': 5
}


class Book:
    def __init__(self, html: str | bytes) -> None:
        def is_text(x): return not x.text.isspace()
        soup = BeautifulSoup(html, 'lxml')
        
        # NAME and CATEGORY
        breadcrumb = soup.find(class_='breadcrumb')
        elements = [*filter(is_text, breadcrumb)]
        self.name = elements[-1].text
        self.category = elements[-2].text.strip('\n')

        # PRICE
        price_color = soup.find(class_='price_color').text
        self.price = round(float(price_color[1:]) * EUR_RATING, 2)

        # AMOUNT
        instock = soup.find(class_='instock availability').text
        stock = re.sub('\D', '', instock)
        self.stock = int(stock)

        # RATING
        pattern = re.compile('star-rating \w+')
        star_rating = soup.find('p', class_=pattern)
        rating = star_rating.attrs['class'][-1]
        self.rating = RATE_MAP.get(rating.capitalize())
    
    def keys(self):
        return ['name', 'category', 'price', 'stock', 'rating']
    
    def __getitem__(self, key):
        return getattr(self, key)
    
    def __repr__(self) -> str:
        return f'<Book(name="{self.name}", category={self.category}, '\
            f'price={self.price}, stock={self.stock}, rating={self.rating})>'