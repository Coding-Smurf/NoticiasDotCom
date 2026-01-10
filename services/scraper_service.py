"""
News Scraper Service
Servicio para extraer artículos de periódicos locales de Boadilla del Monte.
"""

from typing import List, Set, Dict
from bs4 import BeautifulSoup
import requests
from urllib.parse import urljoin, urlparse
import logging

from utils.dom_utils import prune_noise
from utils.url_utils import is_valid_article_url, clean_url
from utils.html_date_extractor import HTMLDateExtractor

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

REQUEST_TIMEOUT = 15


class NewsScraperService:
    """Servicio para scraping de noticias."""
    
    def __init__(self, timeout: int = REQUEST_TIMEOUT):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.date_extractor = HTMLDateExtractor()
    
    def scrape_site(self, url: str) -> List[Dict[str, str]]:
        """
        Extrae artículos de una URL con sus fechas.
        
        Args:
            url: URL del sitio a scrapear
            
        Returns:
            Lista de dicts con {url, date}
        """
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            prune_noise(soup)
            
            return self._extract_articles(soup, url)
        
        except requests.RequestException as e:
            logger.error(f"Error scraping {url}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error scraping {url}: {e}")
            return []
    
    def scrape_multiple(self, urls: List[str]) -> List[Dict[str, str]]:
        """
        Extrae artículos de múltiples URLs.
        
        Args:
            urls: Lista de URLs a scrapear
            
        Returns:
            Lista de dicts únicos con {url, date}
        """
        all_articles = []
        seen_urls = set()
        
        for url in urls:
            logger.info(f"Scraping: {url}")
            articles = self.scrape_site(url)
            
            if articles:
                logger.info(f"✅ Found {len(articles)} articles")
                
                # Deduplicar por URL
                for article in articles:
                    if article['url'] not in seen_urls:
                        all_articles.append(article)
                        seen_urls.add(article['url'])
            else:
                logger.warning(f"❌ No articles found in {url}")
        
        return all_articles
    
    def _extract_articles(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, str]]:
        """Extrae URLs de artículos con fechas del DOM."""
        articles = []
        
        for a in soup.find_all("a", href=True):
            if self._is_likely_article(a, base_url):
                full_url = urljoin(base_url, a["href"])
                full_url = clean_url(full_url)
                
                if is_valid_article_url(full_url):
                    # Extraer fecha cercana al enlace
                    date = self.date_extractor.extract_date_from_link(a, soup)
                    
                    articles.append({
                        'url': full_url,
                        'date': date
                    })
        
        return articles
    
    @staticmethod
    def _is_likely_article(a_tag, base_domain: str) -> bool:
        """Heurística para detectar si un enlace es un artículo."""
        href = a_tag.get("href", "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            return False
        
        text = a_tag.get_text(strip=True)
        if len(text) < 15:
            return False
        
        full_url = urljoin(base_domain, href)
        if urlparse(base_domain).netloc not in full_url:
            return False
        
        parent = a_tag.parent
        
        # Está en estructura de artículo
        if parent and parent.find_parent(["article", "h1", "h2", "h3", "h4"]):
            return True
        
        # Tiene imagen cerca
        if parent and parent.find("img"):
            return True
        
        # Tiene clase de artículo
        parent_class = " ".join(parent.get("class", [])).lower() if parent else ""
        article_keywords = ["article", "post", "noticia", "news", "item", "entry"]
        if any(word in parent_class for word in article_keywords):
            return True
        
        # Texto en rango típico de títulos
        if 20 < len(text) < 200:
            return True
        
        return False