import scrapy
import sqlite3
import json
from scrapy_splash import SplashRequest
from bs4 import BeautifulSoup

class WholesaleSpider(scrapy.Spider):
    name = "wholesale"
    start_urls = [
        # Replace with real URLs after checking robots.txt and ToS
        "https://www.alibaba.com/trade/search?fsb=y&IndexArea=product_en&CatId=&SearchText=gpu",
        "https://www.wholesalecentral.com/electronics.htm",
        "https://www.dhgate.com/wholesale/drones.html",
    ]

    def __init__(self):
        try:
            self.conn = sqlite3.connect("wholesale.db")
            self.cursor = self.conn.cursor()
            self.cursor.execute("""
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
            """)
            self.conn.commit()
        except sqlite3.Error as e:
            self.log(f"Database error: {e}")

    def start_requests(self):
        for url in self.start_urls:
            yield SplashRequest(url, self.parse, args={"wait": 2.0})

    def parse(self, response):
        # Parse HTML with BeautifulSoup
        soup = BeautifulSoup(response.text, "html.parser")
        for product in soup.select("div.product-card"):
            try:
                # Extract text with BeautifulSoup
                store_name = product.find("h2").get_text(strip=True) if product.find("h2") else "N/A"
                price = product.find("span", class_="price").get_text(strip=True) if product.find("span", class_="price") else "N/A"
                contact = product.find("a", class_="contact-link")["href"] if product.find("a", class_="contact-link") else "N/A"
                address = product.find("span", class_="address").get_text(strip=True) if product.find("span", class_="address") else "N/A"
                resale_terms = product.find("div", class_="resale-policy").get_text(strip=True) if product.find("div", class_="resale-policy") else ""

                resale_status = self.determine_resale_status(resale_terms)
                trust_score = self.calculate_trust_score(product)

                self.cursor.execute("""
                    INSERT INTO suppliers (category, store_name, price, contact, address, resale_status, trust_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    response.url.split("/")[-1],
                    store_name,
                    price,
                    contact,
                    address,
                    resale_status,
                    trust_score
                ))
                self.conn.commit()

                yield {
                    "category": response.url.split("/")[-1],
                    "store_name": store_name,
                    "price": price,
                    "contact": contact,
                    "store_url": response.url,
                    "address": address,
                    "resale_status": resale_status,
                    "trust_score": trust_score
                }
            except Exception as e:
                self.log(f"Error parsing product: {e}")

    def determine_resale_status(self, resale_terms):
        if not resale_terms:
            return "Unknown"
        if "Authorized Reseller" in resale_terms or "Bulk Orders Allowed" in resale_terms:
            return "Resale Approved"
        if "No Resale" in resale_terms:
            return "Restricted"
        return "Unknown"

    def calculate_trust_score(self, product):
        score = 0
        try:
            reviews = product.find("span", class_="review-count").get_text(strip=True) if product.find("span", class_="review-count") else "0"
            if reviews and int(reviews) > 100:
                score += 3
        except (ValueError, TypeError):
            pass
        try:
            rating = product.find("span", class_="rating").get_text(strip=True) if product.find("span", class_="rating") else "0"
            if rating and float(rating) > 4.0:
                score += 5
        except (ValueError, TypeError):
            pass
        try:
            years = product.find("span", class_="years-active").get_text(strip=True) if product.find("span", class_="years-active") else "0"
            if years and int(years) > 5:
                score += 2
        except (ValueError, TypeError):
            pass
        return min(score, 10)

    def close_spider(self, spider):
        try:
            self.conn.commit()
            self.conn.close()
        except sqlite3.Error as e:
            self.log(f"Error closing database: {e}")
