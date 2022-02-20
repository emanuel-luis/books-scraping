from selenium.webdriver.firefox.webdriver import WebDriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from .webscrapping import Book
from itertools import cycle
from time import sleep
EMPTY_SOURCE = '<html><head></head><body></body></html>'


def get_source(driver, element):
    with BrowserTab(driver, element) as source:
        return source


class BrowserTab:
    def __init__(self, driver: WebDriver, element) -> None:
        self.link = element.find_element(By.TAG_NAME, 'a')
        self.driver = driver
        self.homepage = driver.current_window_handle

    def __enter__(self):
        self.link.send_keys(Keys.CONTROL, Keys.ENTER)
        sleep(0.5)
        bookpage = self.driver.window_handles[1]
        self.driver.switch_to.window(bookpage)

        try:
            book = Book(self.driver.page_source)
        except:
            self.__exit__()
            sleep(0.1)
            return self.__enter__()
        
        return book

    def __exit__(self, *args, **kwargs):
        self.driver.close()
        self.driver.switch_to.window(self.homepage)
        return True


class Browser:
    def __init__(self, driver: WebDriver) -> None:
        self.driver = driver
        self.first_page = True

    def next_page(self):
        if self.first_page:
            self.first_page = False
            return True

        try:
            button = self.driver.find_element(By.CLASS_NAME, 'next')
            button.find_element(By.TAG_NAME, 'a').click()
        except:
            return False
        return True

    def products(self):
        elements = self.driver.find_elements(By.CLASS_NAME, 'product_pod')
        yield from map(get_source, cycle([self.driver]), elements)

    def __iter__(self):
        while self.next_page():
            yield from self.products()
        self.driver.quit()
