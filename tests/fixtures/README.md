# Test fixtures

Saved once (2026-10-25) from https://books.toscrape.com/ with `curl`, bytes intact. The site
sends `Content-Type: text/html` without a charset, so the tests decode the files as UTF-8.

- `site/index.html`, `site/catalogue/page-2.html`, `site/catalogue/page-50.html`: listing pages
  (page 50 has no `next` link).
- `site/catalogue/a-light-in-the-attic_1000/index.html`, `site/catalogue/in-her-wake_980/index.html`:
  product pages as served.
- `site/catalogue/no-description_999/index.html`: a copy of the In Her Wake page, edited by hand:
  the description block removed, the UPC changed to `0123456789abcdef` and the title changed to
  "No Description Sample".
- `frankfurter_latest.json`: the response of
  `https://api.frankfurter.dev/v1/latest?base=GBP&symbols=EUR,USD,BRL` on 2026-10-25.
