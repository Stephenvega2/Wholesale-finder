"""Scrapy spider for collecting wholesale supplier data with BeautifulSoup."""

import scrapy
import sqlite3
import json
from scrapy_splash import SplashRequest
from bs4 import BeautifulSoup


class WholesaleSpider(scrapy.Spider):
    """Spider to scrape wholesale supplier data and store in SQLite/JSON."""

    name = "wholesale"
    start_urls = [
        # Placeholder URLs; replace with real URLs after checking robots.txt/ToS
        "https://www.alibaba.com/trade/search?fsb=y&IndexArea=product_en&CatId=&SearchText=gpu",
        "https://www.wholesalecentral.com/electronics.htm",
        "https://www.dhgate.com/wholesale/drones.html",
    ]

    def __init__(self, db_name="wholesale.db", *args, **kwargs):
        """Initialize spider and SQLite database.

        Args:
            db_name (str): Name of the SQLite database file (default: 'wholesale.db').
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.
        """
        super().__init__(*args, **kwargs)
        try:
            self.conn = sqlite3.connect(db_name)
            self.cursor = self.conn.cursor()
            self.cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS suppliers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT,
                    store_name TEXT,
                    price TEXT,
                    contact TEXT,
                    address TEXT,
                    resale_status TEXT,
                    trust_score INTEGER,
                    date_scraped DATE DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self.conn.commit()
        except sqlite3.Error as e:
            self.log(f"Database initialization error: {e}")

    def start_requests(self):
        """Generate Splash requests for start URLs.

        Yields:
            SplashRequest: Request for each URL with JavaScript rendering.
        """
        for url in self.start_urls:
            yield SplashRequest(url, self.parse, args={"wait": 2.0})

    def parse(self, response):
        """Parse response and extract product data.

        Args:
            response: Scrapy response object containing HTML.

        Yields:
            dict: Scraped item data.
        """
        soup = BeautifulSoup(response.text, "html.parser")
        for product in soup.select("div.product-card"):
            item = self._extract_product_data(product, response.url)
            if item:
                self._save_to_database(item)
                print("Scraped Item:")
                print(json.dumps(item, indent=2))
                print("-" * 50)
                yield item

    def _extract_product_data(self, product, url):
        """Extract product data from BeautifulSoup element.

        Args:
            product: BeautifulSoup element representing a product.
            url (str): Source URL of the product.

        Returns:
            dict: Extracted item data, or None if extraction fails.
        """
        try:
            item = {
                "category": url.split("/")[-1],
                "store_url": url,
            }
            item["store_name"] = self._get_text(product, "h2")
            item["price"] = self._get_text(product, "span", class_="price")
            item["contact"] = self._get_attribute(product, "a", "contact-link", "href")
            item["address"] = self._get_text(product, "span", class_="address")
            resale_terms = self._get_text(product, "div", class_="resale-policy")
            item["resale_status"] = self._determine_resale_status(resale_terms)
            item["trust_score"] = self._calculate_trust_score(product)
            return item
        except (AttributeError, TypeError) as e:
            self.log(f"Error extracting product data: {e}")
            return None

    def _get_text(self, element, tag, **kwargs):
        """Extract text from a BeautifulSoup element.

        Args:
            element: BeautifulSoup element to search.
            tag (str): HTML tag to find.
            **kwargs: Additional attributes (e.g., class_).

        Returns:
            str: Extracted text or "N/A" if not found.
        """
        found = element.find(tag, **kwargs)
        return found.get_text(strip=True) if found else "N/A"

    def _get_attribute(self, element, tag, class_name, attr):
        """Extract attribute from a BeautifulSoup element.

        Args:
            element: BeautifulSoup element to search.
            tag (str): HTML tag to find.
            class_name (str): Class name of the element.
            attr (str): Attribute to extract.

        Returns:
            str: Attribute value or "N/A" if not found.
        """
        found = element.find(tag, class_=class_name)
        return found[attr] if found and attr in found.attrs else "N/A"

    def _save_to_database(self, item):
        """Save item to SQLite database.

        Args:
            item (dict): Item data to save.
        """
        try:
            self.cursor.execute(
                """
                INSERT INTO suppliers (
                    category, store_name, price, contact, address,
                    resale_status, trust_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["category"],
                    item["store_name"],
                    item["price"],
                    item["contact"],
                    item["address"],
                    item["resale_status"],
                    item["trust_score"],
                ),
            )
            self.conn.commit()
        except sqlite3.Error as e:
            self.log(f"Database save error: {e}")

    def _determine_resale_status(self, resale_terms):
        """Determine resale status from terms.

        Args:
            resale_terms (str): Resale policy text.

        Returns:
            str: Resale status ("Resale Approved", "Restricted", "Unknown").
        """
        if not resale_terms:
            return "Unknown"
        if "Authorized Reseller" in resale_terms or "Bulk Orders Allowed" in resale_terms:
            return "Resale Approved"
        if "No Resale" in resale_terms:
            return "Restricted"
        return "Unknown"

    def _calculate_trust_score(self, product):
        """Calculate trust score based on reviews, rating, and years active.

        Args:
            product: BeautifulSoup element representing a product.

        Returns:
            int: Trust score (0-10).
        """
        score = 0
        score += self._score_reviews(product)
        score += self._score_rating(product)
        score += self._score_years_active(product)
        return min(score, 10)

    def _score_reviews(self, product):
        """Score reviews based on count.

        Args:
            product: BeautifulSoup element.

        Returns:
            int: Score contribution (0 or 3).
        """
        try:
            reviews = self._get_text(product, "span", class_="review-count")
            return 3 if reviews != "N/A" and int(reviews) > 100 else 0
        except ValueError:
            return 0

    def _score_rating(self, product):
        """Score rating based on value.

        Args:
            product: BeautifulSoup element.

        Returns:
            int: Score contribution (0 or 5).
        """
        try:
            rating = self._get_text(product, "span", class_="rating")
            return 5 if rating != "N/A" and float(rating) > 4.0 else 0
        except ValueError:
            return 0

    def _score_years_active(self, product):
        """Score years active based on value.

        Args:
            product: BeautifulSoup element.

        Returns:
            int: Score contribution (0 or 2).
        """
        try:
            years = self._get_text(product, "span", class_="years-active")
            return 2 if years != "N/A" and int(years) > 5 else 0
        except ValueError:
            return 0

    def close_spider(self, spider):
        """Close the SQLite database connection.

        Args:
            spider: Scrapy spider instance.
        """
        try:
            self.conn.commit()
            self.conn.close()
        except sqlite3.Error as e:
            self.log(f"Database close error: {e}")
