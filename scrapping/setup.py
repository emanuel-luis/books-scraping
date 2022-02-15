from .automation import *
from .webscrapping import *
from selenium.webdriver import Firefox, FirefoxOptions
from selenium.webdriver.firefox.service import Service

class Setup:
    def __init__(self):
        print('Starting webscrapping.')
        print('-- starting driver...')
        options = FirefoxOptions()
        options.add_argument("--headless") 

        s = Service(r'C:\bin\geckodriver.exe')
        self.driver = Firefox(options=options, service=s)
        print('-- started with sucess!')
        self.driver.get('http://books.toscrape.com/')
        print('-- starting to scrap from Browser\n\n')

    def get_books(self):
        yield from Browser(self.driver)