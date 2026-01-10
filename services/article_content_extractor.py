"""
Servicio para extraer contenido de artículos.
Extrae títulos y texto principal de URLs para análisis semántico.
"""

from typing import Dict, Optional, List
import requests
from bs4 import BeautifulSoup
import logging
import re

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

REQUEST_TIMEOUT = 15
MAX_CONTENT_LENGTH = 8000  # Aumentado para OpenAI


class ArticleContentExtractor:
    """Extrae contenido relevante de artículos para análisis semántico."""
    
    def __init__(self, timeout: int = REQUEST_TIMEOUT):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
    
    def _clean_text(self, text: str) -> str:
        """Limpia texto removiendo caracteres extraños y espacios múltiples."""
        # Normalizar espacios en blanco
        text = re.sub(r'\s+', ' ', text)
        # Remover líneas vacías múltiples
        text = re.sub(r'\n\s*\n', '\n', text)
        return text.strip()
    
    def _is_boilerplate(self, text: str) -> bool:
        """Detecta si un texto es boilerplate (footer, legal, cookies, etc)."""
        text_lower = text.lower()
        boilerplate_keywords = [
            'cookies', 'política de privacidad', 'aviso legal', 'todos los derechos',
            'copyright', 'términos y condiciones', 'suscríbete', 'newsletter',
            'síguenos en', 'compartir en', 'redes sociales', 'política de cookies',
            'aceptar cookies', 'cerrar', 'más información', 'leer más tarde',
            'publicidad', 'patrocinado', 'anuncio', 'comparte este artículo'
        ]
        
        # Si el texto es muy corto y contiene keywords de boilerplate
        if len(text) < 100:
            return any(keyword in text_lower for keyword in boilerplate_keywords)
        
        return False
    
    def _extract_metadata(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extrae metadata relevante (description, keywords, author)."""
        metadata = {}
        
        # Meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'}) or \
                   soup.find('meta', attrs={'property': 'og:description'})
        if meta_desc and meta_desc.get('content'):
            metadata['description'] = meta_desc.get('content').strip()
        
        # Meta keywords
        meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
        if meta_keywords and meta_keywords.get('content'):
            metadata['keywords'] = meta_keywords.get('content').strip()
        
        # Author
        author = soup.find('meta', attrs={'name': 'author'}) or \
                soup.find('meta', attrs={'property': 'article:author'})
        if author and author.get('content'):
            metadata['author'] = author.get('content').strip()
        
        return metadata
    
    def _extract_article_body(self, soup: BeautifulSoup) -> List[str]:
        """
        Extrae el cuerpo del artículo de forma inteligente.
        Busca contenedores típicos de artículos y extrae párrafos relevantes.
        """
        paragraphs = []
        
        # Buscar contenedores comunes de artículos
        article_containers = [
            soup.find('article'),
            soup.find('div', class_=re.compile(r'article|content|post|entry|body', re.I)),
            soup.find('main'),
            soup.find('div', attrs={'role': 'main'}),
        ]
        
        # Usar el primer contenedor válido
        container = None
        for c in article_containers:
            if c:
                container = c
                break
        
        # Si no hay contenedor, usar todo el body
        if not container:
            container = soup.find('body')
        
        if not container:
            return paragraphs
        
        # Extraer todos los párrafos del contenedor
        for p in container.find_all('p'):
            text = p.get_text(strip=True)
            
            # Filtros de calidad
            if (text and 
                len(text) > 40 and  # Mínimo 40 caracteres
                not self._is_boilerplate(text) and
                not text.startswith('http')):  # No es una URL
                
                paragraphs.append(text)
        
        return paragraphs
    
    def extract_content(self, url: str) -> str:
        """
        Extrae contenido semántico relevante de un artículo.
        
        Estrategia:
        1. Meta description (resumen oficial)
        2. H1 (título principal)
        3. H2 (subtítulo)
        4. Primeros 3-5 párrafos del cuerpo principal
        5. Meta keywords si existen
        
        Args:
            url: URL del artículo
            
        Returns:
            Texto limpio optimizado para embeddings semánticos
        """
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Remover ruido completo
            for tag in soup([
                "script", "style", "nav", "header", "footer", "aside", 
                "noscript", "iframe", "form", "button", "input"
            ]):
                tag.decompose()
            
            content_parts = []
            
            # 1. Metadata
            metadata = self._extract_metadata(soup)
            
            # Meta description primero (suele ser el mejor resumen)
            if 'description' in metadata:
                content_parts.append(f"Resumen: {metadata['description']}")
            
            # 2. Título H1
            h1 = soup.find('h1')
            if h1:
                h1_text = self._clean_text(h1.get_text())
                if h1_text and len(h1_text) > 5:
                    content_parts.append(f"Título: {h1_text}")
            
            # 3. Subtítulo H2 (opcional)
            h2 = soup.find('h2')
            if h2:
                h2_text = self._clean_text(h2.get_text())
                if h2_text and len(h2_text) > 5:
                    content_parts.append(f"Subtítulo: {h2_text}")
            
            # 4. Cuerpo del artículo (primeros 3-5 párrafos de calidad)
            paragraphs = self._extract_article_body(soup)
            
            # Tomar los primeros 4 párrafos más sustanciales
            selected_paragraphs = []
            for p in paragraphs:
                if len(selected_paragraphs) >= 4:
                    break
                # Párrafos más largos tienen más información
                if len(p) > 60:
                    selected_paragraphs.append(p[:400])  # Limitar cada párrafo
            
            if selected_paragraphs:
                content_parts.append("Contenido: " + " ".join(selected_paragraphs))
            
            # 5. Keywords (contexto adicional)
            if 'keywords' in metadata:
                keywords = metadata['keywords'][:200]  # Limitar keywords
                content_parts.append(f"Temas: {keywords}")
            
            # Combinar todo
            full_content = ' '.join(content_parts)
            full_content = self._clean_text(full_content)
            
            # Limitar a 8000 chars (para OpenAI)
            if len(full_content) > MAX_CONTENT_LENGTH:
                full_content = full_content[:MAX_CONTENT_LENGTH]
            
            logger.debug(f"Extraído de {url}: {len(full_content)} chars")
            return full_content
        
        except requests.RequestException as e:
            logger.error(f"Error fetching {url}: {e}")
            return ""
        except Exception as e:
            logger.error(f"Unexpected error extracting content from {url}: {e}")
            return ""
    
    def extract_multiple(self, urls: List[str]) -> Dict[str, str]:
        """
        Extrae contenido de múltiples URLs.
        
        Args:
            urls: Lista de URLs
            
        Returns:
            Dict {url: contenido}
        """
        results = {}
        
        for url in urls:
            content = self.extract_content(url)
            if content:
                results[url] = content
        
        return results