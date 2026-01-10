"""Utilidades para limpieza del DOM."""

from bs4 import BeautifulSoup


def is_likely_noise(tag) -> bool:
    """Identifica elementos de ruido (scripts, ads, navegación)."""
    if tag.name in ["script", "style", "noscript"]:
        return True
    
    attrs = " ".join(tag.get("class", []) + [tag.get("id", "")]).lower()
    
    obvious_noise = ["cookie", "popup", "modal", "advertisement"]
    if any(word in attrs for word in obvious_noise):
        return True
    
    if tag.name in ["nav", "footer", "aside"]:
        for a in tag.find_all("a", href=True):
            if len(a.get_text(strip=True)) > 25:
                return False
        return True
    
    return False


def prune_noise(soup: BeautifulSoup) -> None:
    """Elimina ruido del DOM (modifica el soup in-place)."""
    tags_to_remove = [tag for tag in soup.find_all(True) if is_likely_noise(tag)]
    
    for tag in tags_to_remove:
        tag.decompose()