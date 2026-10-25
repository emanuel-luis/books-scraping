from decimal import Decimal

import pytest
from conftest import A_LIGHT, BASE, IN_HER_WAKE, NO_DESC, site_file
from hypothesis import given
from hypothesis import strategies as st

from books_scraping.parse import (
    ParseError,
    parse_listing,
    parse_price,
    parse_product,
    parse_rating,
    parse_stock,
)


def html(rel: str) -> str:
    return site_file(rel).decode("utf-8")


def test_product_exact_fields() -> None:
    book = parse_product(html(A_LIGHT), BASE + A_LIGHT)
    assert book | {"description": None} == {
        "upc": "a897fe39b1053632",
        "url": BASE + A_LIGHT,
        "title": "A Light in the Attic",
        "category": "Poetry",
        "price": Decimal("51.77"),
        "currency": "GBP",
        "stock": 22,
        "rating": 3,
        "num_reviews": 0,
        "description": None,
    }
    description = str(book["description"])
    assert description.startswith("It's hard to imagine a world without A Light in the Attic")


def test_pound_sign_survives_utf8_decoding() -> None:
    assert "Â£" not in html(A_LIGHT)
    assert parse_product(html(IN_HER_WAKE), "u")["currency"] == "GBP"


def test_missing_description_is_none() -> None:
    book = parse_product(html(NO_DESC), "u")
    assert book["description"] is None
    assert book["upc"] == "0123456789abcdef"


def test_first_listing_page() -> None:
    listing = parse_listing(html("index.html"), BASE)
    assert len(listing.product_urls) == 20
    assert listing.product_urls[0] == BASE + A_LIGHT
    assert listing.next_url == BASE + "catalogue/page-2.html"


def test_middle_page_links_are_relative_to_the_page() -> None:
    listing = parse_listing(html("catalogue/page-2.html"), BASE + "catalogue/page-2.html")
    assert listing.next_url == BASE + "catalogue/page-3.html"
    assert listing.product_urls[0] == BASE + "catalogue/in-her-wake_980/index.html"


def test_last_page_has_no_next() -> None:
    listing = parse_listing(html("catalogue/page-50.html"), BASE + "catalogue/page-50.html")
    assert listing.next_url is None
    assert len(listing.product_urls) == 20


BROKEN = {
    "empty": "<html></html>",
    "no-upc": html(A_LIGHT).replace("<th>UPC</th>", "<th>Code</th>"),
    "unknown-currency": html(A_LIGHT).replace(
        "<th>Price (excl. tax)</th><td>£51.77", "<th>Price (excl. tax)</th><td>¥51.77"
    ),
    "unknown-rating": html(A_LIGHT).replace("star-rating Three", "star-rating Zero"),
    "unknown-stock": html(A_LIGHT).replace("In stock (22 available)", "Soon"),
    "no-rating": html(A_LIGHT).replace('class="star-rating Three"', 'class="rating"'),
    "no-breadcrumb": html(A_LIGHT).replace('ul class="breadcrumb"', 'ul class="crumbs"'),
    "bad-review-count": html(A_LIGHT).replace("<td>0</td>", "<td>many</td>"),
}


@pytest.mark.parametrize("broken", BROKEN.values(), ids=BROKEN.keys())
def test_broken_product_raises(broken: str) -> None:
    with pytest.raises(ParseError):
        parse_product(broken, "u")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("£51.77", (Decimal("51.77"), "GBP")),
        ("€5", (Decimal("5.00"), "EUR")),
        ("$0.5", (Decimal("0.50"), "USD")),
    ],
)
def test_parse_price(text: str, expected: tuple[Decimal, str]) -> None:
    assert parse_price(text) == expected


@pytest.mark.parametrize("text", ["", "51.77", "¥51.77", "£1,000.00", "£-1.00", "£1.234"])
def test_parse_price_rejects(text: str) -> None:
    with pytest.raises(ParseError):
        parse_price(text)


@given(st.decimals(min_value=0, max_value=10**7, places=2))
def test_parse_price_round_trip(value: Decimal) -> None:
    assert parse_price(f"£{value}") == (value, "GBP")


def test_rating_and_stock() -> None:
    assert [parse_rating(w) for w in ("One", "Two", "Three", "Four", "Five")] == [1, 2, 3, 4, 5]
    assert parse_stock("In stock (22 available)") == 22
    assert parse_stock("Out of stock") == 0
    with pytest.raises(ParseError):
        parse_rating("Six")
