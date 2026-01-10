"""Extractor de fechas desde HTML."""

from bs4 import BeautifulSoup, Tag
from typing import Optional
import re
import logging

from utils.date_utils import parse_date_flexible

logger = logging.getLogger(__name__)


class HTMLDateExtractor:
    """Extrae fechas de artículos desde HTML."""
    
    @staticmethod
    def extract_date_from_link(a_tag: Tag, soup: BeautifulSoup) -> Optional[str]:
        """
        Extrae la fecha más cercana a un enlace de artículo.
        
        Estrategia (en orden de prioridad):
        1. Buscar en metadatos del artículo
        2. Buscar en el contenedor más grande (todo el bloque de noticia)
        3. Buscar en hermanos anteriores del enlace
        4. Buscar en elementos cercanos al enlace
        5. Buscar subiendo en el árbol DOM
        """
        # Estrategia 1: Metadatos (si el enlace está dentro de un article)
        article = a_tag.find_parent('article')
        if article:
            date = HTMLDateExtractor._find_date_in_element(article, deep=True)
            if date:
                logger.debug(f"Fecha encontrada en <article>: {date}")
                return date
        
        # Estrategia 2: Buscar en el div contenedor más grande
        # Subir hasta encontrar un div con clase que parezca contenedor de noticia
        container = a_tag.find_parent(['div', 'section'], 
                                     class_=re.compile(r'(node|noticia|news|item|post|entry)', re.I))
        if container:
            date = HTMLDateExtractor._find_date_in_element(container, deep=True)
            if date:
                logger.debug(f"Fecha encontrada en contenedor: {date}")
                return date
        
        # Estrategia 3: Hermanos anteriores (mismo nivel)
        current = a_tag
        for _ in range(3):
            current = current.find_previous_sibling()
            if not current:
                break
            
            text = current.get_text(strip=True)
            if text and len(text) < 50:
                date = parse_date_flexible(text)
                if date:
                    logger.debug(f"Fecha encontrada en hermano: {text} -> {date}")
                    return date
        
        # Estrategia 4: Buscar en el contenedor padre directo
        parent = a_tag.parent
        if parent:
            for child in parent.children:
                if child == a_tag:
                    continue
                
                if hasattr(child, 'get_text'):
                    text = child.get_text(strip=True)
                    if text and len(text) < 50:
                        date = parse_date_flexible(text)
                        if date:
                            logger.debug(f"Fecha encontrada en hijo del padre: {text} -> {date}")
                            return date
            
            date = HTMLDateExtractor._find_date_in_element(parent)
            if date:
                return date
        
        # Estrategia 5: Subir hasta 5 niveles en el árbol
        current = a_tag
        for level in range(5):
            current = current.parent
            if not current:
                break
            
            date = HTMLDateExtractor._find_date_in_element(current)
            if date:
                logger.debug(f"Fecha encontrada subiendo {level+1} niveles")
                return date
        
        return None
    
    @staticmethod
    def _find_date_in_element(element: Tag, deep: bool = False) -> Optional[str]:
        """
        Busca fecha dentro de un elemento específico.
        
        Args:
            element: Elemento donde buscar
            deep: Si True, busca recursivamente en todos los descendientes
        """
        # 1. Buscar <time> con datetime
        time_tag = element.find('time', datetime=True)
        if time_tag:
            date = parse_date_flexible(time_tag['datetime'])
            if date:
                return date
        
        # 2. Buscar <time> sin datetime (solo texto)
        time_tag = element.find('time')
        if time_tag:
            date = parse_date_flexible(time_tag.get_text())
            if date:
                return date
        
        # 3. Buscar clases comunes de fecha (con diferentes patrones)
        date_class_patterns = [
            r'date',
            r'fecha',
            r'published',
            r'entry-date',
            r'post-date',
            r'time',
            r'timestamp',
            r'noticia-fecha',  # Específico para ayuntamiento boadilla
        ]
        
        for pattern in date_class_patterns:
            date_elem = element.find(class_=re.compile(pattern, re.I))
            if date_elem:
                # Buscar dentro del elemento encontrado
                text = date_elem.get_text(strip=True)
                date = parse_date_flexible(text)
                if date:
                    return date
                
                # También buscar en spans hijos (como date-display-single)
                for span in date_elem.find_all(['span', 'div'], recursive=True):
                    text = span.get_text(strip=True)
                    if text:
                        date = parse_date_flexible(text)
                        if date:
                            return date
        
        # 4. Si deep=True, buscar en todos los textos cortos del elemento
        if deep:
            for child in element.descendants:
                if hasattr(child, 'get_text') and child.name:
                    text = child.get_text(strip=True)
                    # Solo textos muy cortos (fechas suelen ser <30 caracteres)
                    if text and 5 < len(text) < 30:
                        # Evitar buscar en textos largos (descripciones, etc)
                        if not child.find_all(['p', 'article']):
                            date = parse_date_flexible(text)
                            if date:
                                return date
        
        return None