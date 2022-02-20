from selenium.webdriver.support import expected_conditions as EC
from typing import Generator
from selenium.webdriver import Firefox, FirefoxOptions
from selenium.webdriver.firefox.service import Service
from bs4 import BeautifulSoup
from selenium.webdriver.firefox.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
import requests
import re


def _is_text(string: str) -> bool:
    return not string.isspace() and string


class Scrapper:
    def __init__(self, headless=True) -> None:
        options = FirefoxOptions()
        if headless:
            options.add_argument('--headless')

        service = Service(r'C:\bin\geckodriver.exe', log_path='nul')
        driver = Firefox(options=options, service=service)

        driver.get('https://books.toscrape.com/')

        self.driver = driver
        self.homepage = driver.current_window_handle
        self.has_next_page = True
        self.eur_currency = self.__get_eur_currency()
        self.categories = self.__get_categories()
        self.rating = {
            'One': 1,
            'Two': 2,
            'Three': 3,
            'Four': 4,
            'Five': 5
        }

    def __next__(self) -> bool:
        try:
            yield from map(self.__get_element, self.driver.find_elements(
                By.CLASS_NAME, 'product_pod'))

            button = self.driver.find_element(
                By.XPATH, '//a[text()="next"]')
            button.click()
        except:
            self.has_next_page = False
            self.driver.quit()

    def __iter__(self) -> Generator[str, str, str]:
        while self.has_next_page:
            yield from map(self.__get_book_attrs, next(self))

    def __get_eur_currency(self, api_key='42e068b6c9235f430e2abc6945f16a40') -> float:
        url = 'http://api.currencylayer.com/live'
        query = f'?access_key={api_key}&currencies=EUR,BRL,USD&format=1'

        request = requests.get(f'{url}{query}')
        json = request.json()
        quotes = json['quotes']

        return quotes['USDBRL'] / quotes['USDEUR']

    def __get_book_attrs(self, html: str | bytes) -> dict[str, str | float | int]:
        soup = BeautifulSoup(html, 'lxml')

        *_, c, name = [*filter(_is_text, map(
            lambda x: x.text, soup.find(class_='breadcrumb')))]

        category = c.strip('\n')

        price_color = float(soup.find(class_='price_color').text[1:])
        price = round(price_color, 2)

        instock = soup.find(class_='instock availability').text
        stock = int(re.sub('\D', '', instock))

        star_rating = soup.find('p', class_=re.compile(
            r'^star-rating \w+$')).attrs['class']
        rating = self.rating.get(star_rating[-1])

        header = soup.find('div', id='product_description',
                           class_='sub-header')
        if header is not None:
            description = re.sub('...more', '',
                                 header.find_next('p').text).strip()
        else:
            description = 'No decription.'

        return {
            'name': name,
            'category': category,
            'price': price,
            'stock': stock,
            'rating': rating,
            'description': description
        }

    def __get_categories(self) -> dict[str, int]:
        categories_ul = self.driver.find_element(
            By.XPATH, '//*[@id="default"]/div/div/div/aside/div[2]/ul/li/ul')

        categories = [category.text
                      for category in categories_ul.find_elements(
                          By.TAG_NAME, 'a')
                      ]
        categories.sort()

        return [{'name': category} for category in categories]

    def __get_element(self, element: WebElement) -> Generator[str, None, None]:
        element.find_element(By.TAG_NAME, 'a') \
            .send_keys(Keys.CONTROL, Keys.ENTER)
        self.driver.switch_to.window(self.driver.window_handles[1])

        try:
            WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located(
                    (By.CLASS_NAME, 'breadcrumb')
                )
            )

        except Exception as e:
            print(f'[ERRO] {e}')

        finally:
            source = self.driver.page_source
            self.driver.close()
            self.driver.switch_to.window(self.homepage)
            return source

    def __get_books(self):
        return tuple(self)
