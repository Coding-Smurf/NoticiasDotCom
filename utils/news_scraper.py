import csv
import json
import requests
import time
from bs4 import BeautifulSoup
from datetime import datetime
from dateutil import parser as date_parser
from urllib.parse import urljoin
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import io

class NewsScraper:
    """Simple news scraper following KISS principles"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = OpenAI(api_key=api_key) if api_key else None
        self.print_lock = Lock()
        
        # Default config
        self.config = {
            "recent_days": 30,
            "request_delay": 1,
            "max_retries": 3,
            "max_workers_sites": 5,
            "max_workers_articles": 10,
            "max_workers_summaries": 5,
            "model_name": "gpt-4o-mini"
        }
    
    def update_config(self, new_config: dict):
        """Update configuration"""
        self.config.update(new_config)
    
    def safe_print(self, *args, **kwargs):
        """Thread-safe printing"""
        with self.print_lock:
            print(*args, **kwargs)
    
    # --- FILE LOADING ---
    
    def load_sites_from_file(self, file) -> list[str]:
        """Load sites from uploaded CSV file"""
        try:
            content = file.read().decode('utf-8')
            reader = csv.DictReader(io.StringIO(content))
            return [row["siteURL"] for row in reader if row.get("web") == "1"]
        except Exception as e:
            self.safe_print(f"Error loading CSV: {e}")
            return []
    
    # --- WEB SCRAPING ---
    
    def fetch_page(self, url: str) -> tuple[str, str]:
        """Fetch HTML from URL"""
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        try:
            response = requests.get(url, headers=headers, timeout=20)
            response.raise_for_status()
            return response.text, response.url
        except Exception as e:
            self.safe_print(f"[ERROR] {url}: {e}")
            return "", ""
    
    def extract_links_with_titles(self, html: str, base_url: str) -> list[dict]:
        """Extract article links and titles from HTML"""
        soup = BeautifulSoup(html, "html.parser")
        articles = []
        seen_urls = set()
        
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            title = a_tag.get_text(strip=True)
            
            # Filter by title length
            if not title or len(title) < 15 or len(title) > 300:
                continue
            
            # Skip common patterns
            skip_patterns = ["javascript:", "mailto:", "#", "login", "admin", 
                            "tag/", "category/", "autor/", "author/", "page/"]
            if any(p in href.lower() for p in skip_patterns):
                continue
            
            skip_texts = ["leer más", "read more", "ver más", "click here", 
                         "siguiente", "anterior", "next", "prev"]
            if any(t in title.lower() for t in skip_texts):
                continue
            
            full_url = urljoin(base_url, href)
            
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)
            
            articles.append({
                "title": title,
                "url": full_url
            })
        
        return articles
    
    def fetch_article_content(self, url: str) -> str:
        """Fetch full article content"""
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Remove non-content tags
            for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
                tag.decompose()
            
            article_text = soup.get_text(separator="\n", strip=True)
            lines = [line.strip() for line in article_text.split("\n") if line.strip()]
            clean_text = "\n".join(lines)
            
            return clean_text[:5000]
        except Exception as e:
            self.safe_print(f"[ERROR] Fetching article: {e}")
            return ""
    
    # --- AI PROCESSING ---
    
    def ask_ai(self, prompt: str) -> str:
        """Simple AI request wrapper"""
        if not self.client:
            return ""
        
        for attempt in range(self.config["max_retries"]):
            try:
                response = self.client.chat.completions.create(
                    model=self.config["model_name"],
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                self.safe_print(f"[WARN] AI attempt {attempt+1}: {e}")
                time.sleep(3)
        return ""
    
    def filter_news_with_ai(self, articles: list[dict], page_text: str) -> list[dict]:
        """Filter real news articles using AI"""
        if not articles:
            return []
        
        articles_list = "\n".join([
            f"{i+1}. {a['title']}" 
            for i, a in enumerate(articles[:40])
        ])
        
        prompt = f"""Analiza esta lista de posibles artículos de un sitio de noticias.

ARTÍCULOS:
{articles_list}

TEXTO DE LA PÁGINA (busca aquí las fechas de publicación):
{page_text[:8000]}

Para cada artículo que SEA una noticia real (no menú, categoría, publicidad), busca su fecha en el texto.

Responde SOLO JSON array:
[
  {{"num": 1, "date": "2024-01-15"}},
  {{"num": 3, "date": "05/01/2025"}}
]

Solo incluye los que SÍ son noticias con su fecha."""

        response_text = self.ask_ai(prompt)
        if not response_text:
            return articles
        
        # Clean JSON response
        if "```" in response_text:
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        
        try:
            ai_results = json.loads(response_text)
            
            filtered = []
            for item in ai_results:
                num = item.get("num")
                if num and 0 < num <= len(articles):
                    article = articles[num - 1].copy()
                    article["date"] = item.get("date")
                    filtered.append(article)
            
            return filtered
        except:
            return articles
    
    # --- DATE FILTERING ---
    
    def is_recent(self, date_str: str) -> bool:
        """Check if date is within recent_days"""
        if not date_str:
            return True
        try:
            parsed = date_parser.parse(date_str, fuzzy=True, dayfirst=True)
            delta = (datetime.now() - parsed).days
            return 0 <= delta <= self.config["recent_days"]
        except:
            return True
    
    # --- MAIN PROCESSING ---
    
    def process_single_site(self, site: str, idx: int, total: int) -> list[dict]:
        """Process a single news site"""
        self.safe_print(f"[{idx}/{total}] {site}")
        
        html, final_url = self.fetch_page(site)
        if not html:
            self.safe_print("      ✗ Error de conexión\n")
            return []

        raw_articles = self.extract_links_with_titles(html, final_url or site)
        self.safe_print(f"      → {len(raw_articles)} enlaces extraídos")
        
        if not raw_articles:
            self.safe_print("      ✗ Sin enlaces\n")
            return []
        
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        page_text = soup.get_text(separator="\n")
        
        filtered = self.filter_news_with_ai(raw_articles, page_text)
        
        recent = [
            {**a, "source": site}
            for a in filtered
            if self.is_recent(a.get("date"))
        ]
        
        self.safe_print(f"      ✓ {len(recent)} noticias recientes\n")
        time.sleep(self.config["request_delay"])
        
        return recent
    
    def process_all_sites(self, sites: list[str]) -> list[dict]:
        """Process all sites in parallel"""
        all_news = []
        with ThreadPoolExecutor(max_workers=self.config["max_workers_sites"]) as executor:
            future_to_site = {
                executor.submit(self.process_single_site, site, idx, len(sites)): site 
                for idx, site in enumerate(sites, 1)
            }
            
            for future in as_completed(future_to_site):
                site_news = future.result()
                all_news.extend(site_news)
        
        return all_news
    
    # --- DUPLICATE DETECTION ---
    
    def group_duplicates(self, articles: list[dict]) -> list[list[int]]:
        """Group duplicate articles using AI"""
        if len(articles) <= 1:
            return [[0]] if articles else []
        
        titles_list = "\n".join([
            f"{i}. {a['title']}"
            for i, a in enumerate(articles)
        ])
        
        prompt = f"""Analiza estos títulos de artículos y agrupa los que hablan de la MISMA noticia.

TÍTULOS:
{titles_list}

Responde SOLO un JSON array de arrays con los índices agrupados:
[
  [0, 1],
  [2],
  [3, 5],
  [4]
]

Cada subarray contiene los índices de artículos que son duplicados (misma noticia).
Si un artículo no tiene duplicados, va solo en su array."""

        response_text = self.ask_ai(prompt)
        if not response_text:
            return [[i] for i in range(len(articles))]
        
        # Clean JSON response
        if "```" in response_text:
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        
        try:
            groups = json.loads(response_text)
            if isinstance(groups, list):
                return groups
        except:
            pass
        
        return [[i] for i in range(len(articles))]
    
    # --- SUMMARIZATION ---
    
    def summarize_single_group(self, group_indices: list[int], all_news: list[dict], group_idx: int) -> dict:
        """Summarize a single group of articles"""
        group_articles = [all_news[i] for i in group_indices]
        
        # Fetch all article contents in parallel
        articles_with_content = []
        with ThreadPoolExecutor(max_workers=self.config["max_workers_articles"]) as executor:
            future_to_article = {
                executor.submit(self.fetch_article_content, article["url"]): article 
                for article in group_articles
            }
            
            for future in as_completed(future_to_article):
                article = future_to_article[future]
                content = future.result()
                articles_with_content.append((article, content))
        
        # Build text for AI
        articles_text = ""
        for i, (article, content) in enumerate(articles_with_content, 1):
            if not content:
                articles_text += f"\n--- ARTÍCULO {i} ---\nTítulo: {article['title']}\nURL: {article['url']}\nContenido: [No disponible]\n"
            else:
                articles_text += f"\n--- ARTÍCULO {i} ---\nTítulo: {article['title']}\nURL: {article['url']}\nContenido: {content[:3000]}\n"
        
        # Generate summary
        if len(group_articles) == 1:
            prompt = f"""Resume este artículo de forma concisa (2-3 frases).

{articles_text}

Responde SOLO el resumen como texto plano, sin JSON."""
        else:
            prompt = f"""Estos artículos hablan de la MISMA noticia. Resume la noticia combinando la información de todos (2-3 frases).

{articles_text}

Responde SOLO el resumen como texto plano, sin JSON."""

        summary = self.ask_ai(prompt)
        
        # Clean up response
        if summary.startswith('"') and summary.endswith('"'):
            summary = summary[1:-1]
        if summary.startswith('```') or summary.endswith('```'):
            summary = summary.replace('```', '').strip()
        
        if not summary:
            summary = "Resumen no disponible"
        
        return {
            "group_idx": group_idx,
            "group_indices": group_indices,
            "summary": summary,
            "is_duplicate": len(group_indices) > 1
        }
    
    def summarize_groups(self, groups: list[list[int]], all_news: list[dict]) -> list[dict]:
        """Summarize all groups in parallel"""
        with ThreadPoolExecutor(max_workers=self.config["max_workers_summaries"]) as executor:
            future_to_group = {
                executor.submit(self.summarize_single_group, group_indices, all_news, group_idx): group_idx
                for group_idx, group_indices in enumerate(groups, 1)
            }
            
            for future in as_completed(future_to_group):
                result = future.result()
                
                # Update articles with summary
                for i in result["group_indices"]:
                    all_news[i]["summary"] = result["summary"]
                    all_news[i]["group_id"] = result["group_idx"]
                    all_news[i]["is_duplicate"] = result["is_duplicate"]
        
        return all_news