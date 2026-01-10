"""Utilidades para detección y parsing de fechas."""

import re
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Meses en español
MESES_ES = {
    'enero': 1, 'ene': 1,
    'febrero': 2, 'feb': 2,
    'marzo': 3, 'mar': 3,
    'abril': 4, 'abr': 4,
    'mayo': 5, 'may': 5,
    'junio': 6, 'jun': 6,
    'julio': 7, 'jul': 7,
    'agosto': 8, 'ago': 8,
    'septiembre': 9, 'sep': 9, 'sept': 9,
    'octubre': 10, 'oct': 10,
    'noviembre': 11, 'nov': 11,
    'diciembre': 12, 'dic': 12,
}


def parse_date_flexible(date_string: str) -> Optional[str]:
    """
    Intenta parsear una fecha en múltiples formatos.
    
    Returns:
        Fecha en formato ISO (YYYY-MM-DD) o None
    """
    if not date_string:
        return None
    
    date_string = date_string.strip().lower()
    
    # Limpiar caracteres extra
    date_string = re.sub(r'\s+', ' ', date_string)
    
    # Patrones comunes (en orden de especificidad)
    patterns = [
        # ISO: 2026-01-09T10:30:00
        (r'(\d{4})-(\d{2})-(\d{2})(?:t|\s)', lambda m: f"{m.group(1)}-{m.group(2)}-{m.group(3)}"),
        
        # ISO simple: 2026-01-09
        (r'(\d{4})-(\d{2})-(\d{2})', lambda m: f"{m.group(1)}-{m.group(2)}-{m.group(3)}"),
        
        # dd.mm.yyyy (con puntos)
        (r'(\d{1,2})\.(\d{1,2})\.(\d{4})', 
         lambda m: f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"),
        
        # dd/mm/yyyy
        (r'(\d{1,2})/(\d{1,2})/(\d{4})', 
         lambda m: f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"),
        
        # dd-mm-yyyy
        (r'(\d{1,2})-(\d{1,2})-(\d{4})', 
         lambda m: f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"),
        
        # yyyy/mm/dd
        (r'(\d{4})/(\d{1,2})/(\d{1,2})', 
         lambda m: f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"),
        
        # "9 de enero de 2026" (con "de")
        (r'(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+de\s+(\d{4})', parse_spanish_date),
        
        # "9 enero 2026" (SIN "de") - NUEVO
        (r'(\d{1,2})\s+([a-záéíóúñ]+)\s+(\d{4})', parse_spanish_date),
        
        # "enero 9, 2026"
        (r'([a-záéíóúñ]+)\s+(\d{1,2}),?\s+(\d{4})', parse_spanish_date_reverse),
        
        # "9/1/2026" o "09/01/2026" (flexible)
        (r'(\d{1,2})/(\d{1,2})/(\d{2,4})', parse_flexible_slash_date),
    ]
    
    for pattern, handler in patterns:
        match = re.search(pattern, date_string)
        if match:
            try:
                result = handler(match)
                if result and is_valid_date(result):
                    logger.debug(f"Parseado '{date_string}' -> '{result}'")
                    return result
            except Exception as e:
                logger.debug(f"Error parsing date '{date_string}': {e}")
                continue
    
    return None


def parse_spanish_date(match) -> Optional[str]:
    """Parsea formato: 9 de enero de 2026 O 9 enero 2026"""
    day = int(match.group(1))
    month_name = match.group(2).lower()
    year = int(match.group(3))
    
    month = MESES_ES.get(month_name)
    if not month:
        return None
    
    return f"{year}-{month:02d}-{day:02d}"


def parse_spanish_date_reverse(match) -> Optional[str]:
    """Parsea formato: enero 9, 2026"""
    month_name = match.group(1).lower()
    day = int(match.group(2))
    year = int(match.group(3))
    
    month = MESES_ES.get(month_name)
    if not month:
        return None
    
    return f"{year}-{month:02d}-{day:02d}"


def parse_flexible_slash_date(match) -> Optional[str]:
    """Parsea fechas con / de forma flexible."""
    part1 = int(match.group(1))
    part2 = int(match.group(2))
    part3 = int(match.group(3))
    
    # Ajustar año si es de 2 dígitos
    if part3 < 100:
        part3 = 2000 + part3 if part3 < 50 else 1900 + part3
    
    # dd/mm/yyyy (más común en España)
    return f"{part3}-{part2:02d}-{part1:02d}"


def is_valid_date(date_str: str) -> bool:
    """Valida que la fecha sea razonable."""
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d')
        
        # Rango razonable: no más de 5 años en el pasado ni en el futuro
        now = datetime.now()
        min_date = datetime(now.year - 5, 1, 1)
        max_date = datetime(now.year + 2, 12, 31)
        
        return min_date <= date <= max_date
    except ValueError:
        return False