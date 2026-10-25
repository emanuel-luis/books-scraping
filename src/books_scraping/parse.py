"""Pure HTML parsing: no I/O, no clock."""

import re
from decimal import Decimal
from typing import NamedTuple
from urllib.parse import urljoin

from selectolax.lexbor import LexborHTMLParser as HTMLParser

CURRENCIES = {"£": "GBP", "€": "EUR", "$": "USD"}
_RATINGS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
_PRICE = re.compile(r"^\s*(\D)\s*(\d+(?:\.\d{1,2})?)\s*$")
_STOCK = re.compile(r"(\d+)\s+available", re.IGNORECASE)


class ParseError(ValueError):
    """The page does not have the expected structure."""


class Listing(NamedTuple):
    product_urls: list[str]
    next_url: str | None


def parse_price(text: str) -> tuple[Decimal, str]:
    m = _PRICE.match(text)
    if not m or m.group(1) not in CURRENCIES:
        raise ParseError(f"unrecognised price {text!r}")
    return Decimal(m.group(2)).quantize(Decimal("0.01")), CURRENCIES[m.group(1)]


def parse_rating(word: str) -> int:
    try:
        return _RATINGS[word]
    except KeyError:
        raise ParseError(f"unrecognised rating {word!r}") from None


def parse_stock(text: str) -> int:
    m = _STOCK.search(text)
    if m:
        return int(m.group(1))
    if "out of stock" in text.lower():
        return 0
    raise ParseError(f"unrecognised availability {text!r}")


def parse_listing(html: str, page_url: str) -> Listing:
    tree = HTMLParser(html)
    urls = [
        urljoin(page_url, href)
        for a in tree.css("article.product_pod h3 a")
        if (href := a.attributes.get("href"))
    ]
    nxt = tree.css_first("li.next a")
    href = nxt.attributes.get("href") if nxt else None
    return Listing(urls, urljoin(page_url, href) if href else None)


def parse_product(html: str, url: str) -> dict[str, object]:
    tree = HTMLParser(html)

    def text(selector: str) -> str:
        node = tree.css_first(selector)
        if node is None:
            raise ParseError(f"missing {selector}")
        return str(node.text(strip=True))

    crumbs = tree.css("ul.breadcrumb li a")
    if len(crumbs) < 3:
        raise ParseError("missing category breadcrumb")
    table: dict[str, str] = {}
    for row in tree.css("table.table tr"):
        th, td = row.css_first("th"), row.css_first("td")
        if th is not None and td is not None:
            table[str(th.text(strip=True))] = str(td.text(strip=True))
    try:
        upc = table["UPC"]
        price_text = table["Price (excl. tax)"]
        availability = table["Availability"]
        reviews = table["Number of reviews"]
    except KeyError as exc:
        raise ParseError(f"missing product table row {exc}") from None
    stars = tree.css_first("div.product_main p.star-rating")
    if stars is None:
        raise ParseError("missing star rating")
    words = [c for c in str(stars.attributes.get("class") or "").split() if c != "star-rating"]
    price, currency = parse_price(price_text)
    desc_node = tree.css_first("#product_description + p")
    description = str(desc_node.text(strip=True)) if desc_node is not None else ""
    if not reviews.isdigit():
        raise ParseError(f"unrecognised review count {reviews!r}")
    return {
        "upc": upc,
        "url": url,
        "title": text("div.product_main h1"),
        "category": str(crumbs[2].text(strip=True)),
        "price": price,
        "currency": currency,
        "stock": parse_stock(availability),
        "rating": parse_rating(words[0] if words else ""),
        "num_reviews": int(reviews),
        "description": description or None,
    }
