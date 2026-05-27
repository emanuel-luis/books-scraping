
# books-scrapping

> A small ingestion pipeline that scrapes [Books to Scrape](http://books.toscrape.com/) with
> **Selenium + BeautifulSoup** and persists the results to a relational store via
> **SQLAlchemy**.

![python](https://img.shields.io/badge/python-3-blue)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-D71F00?logo=sqlalchemy&logoColor=white)

## What this demonstrates

- **Scrape → model → load** — a complete mini-ETL: navigate (Selenium), parse (BS4), and
  persist to a modeled schema (SQLAlchemy).
- **Relational modeling** — `Book` and `Category` tables with a relationship, not just a flat
  dump.
- **Practical scraping decisions** — switched ChromeDriver → GeckoDriver to handle
  JavaScript-rendered pages in headless mode.

## Data model

| Table | Fields |
| --- | --- |
| `Book` | name, category, price, stock, rating, description |
| `Category` | category metadata (related to `Book`) |

## Tech stack

Python · Selenium (GeckoDriver) · BeautifulSoup4 · SQLAlchemy · SQLite.

## Quickstart

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    |    Unix: source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

> Requires GeckoDriver on PATH.

## Notes

Early portfolio project, framed as **data ingestion → relational store**. Natural upgrades:
swap SQLite for PostgreSQL, add a `to_csv()` export, and parameterize the crawl.

## License

MIT (add a `LICENSE` file).
