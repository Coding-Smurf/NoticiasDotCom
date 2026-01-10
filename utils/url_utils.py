"""Utilidades para validación y limpieza de URLs."""

from urllib.parse import urlparse


def is_valid_article_url(url: str) -> bool:
    """Valida si una URL es potencialmente un artículo."""
    url_lower = url.lower()
    
    blacklist = [
        "/category/", "/categories/", "/categoria/",
        "/autor/", "/author/", "/writer/",
        "/tag/", "/tags/", "/tema/", "/etiqueta/",
        "addthis.com", "facebook.com", "twitter.com", "whatsapp.com",
        "/faqs/", "/aviso", "/legal", "/privacidad", "/cookies",
        "/busqueda/", "/search", "/archivo/",
        "?page=", "&page=", "/noticia-madrid/",
        "mailto:", "tel:", "/noticia-opinion",
        "/empresas/zona", "/noticia-comunidad-de-madrid/",
        "/dias-de-lluvia", "/noticias-96.aspx",
        "/www.soydemadrid.com/noticias-",
        "?items_per_page="
    ]
    
    parsed = urlparse(url)
    
    # Homepage
    if parsed.path in ["/", ""]:
        return False
    
    # Último segmento debe tener guiones
    path_segments = parsed.path.strip("/").split("/")
    if path_segments:
        last_segment = path_segments[-1]
        if "-" not in last_segment:
            return False
    
    return not any(pattern in url_lower for pattern in blacklist)


def clean_url(url: str) -> str:
    """Limpia URLs con prefijos de búsqueda."""
    if "/noticias-busqueda/" in url:
        parts = url.split("/noticias-busqueda/todos/")
        if len(parts) > 1:
            rest = parts[1].split("/", 6)
            if len(rest) > 6:
                base = url.split("/noticias-busqueda/")[0]
                return f"{base}/{rest[6]}"
    
    return url