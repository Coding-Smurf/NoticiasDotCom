"""
Servicio para sintetizar artículos unificados desde grupos de artículos duplicados.
Usa GPT-4o-mini para crear un artículo comprehensivo con toda la información.
Soporta síntesis paralela para mayor velocidad (hasta 10 requests concurrentes).
"""

from typing import List, Dict
import logging
from openai import OpenAI, AsyncOpenAI
import asyncio

logger = logging.getLogger(__name__)


class ArticleSynthesisService:
    """Sintetiza múltiples artículos duplicados en uno solo usando GPT-4o-mini con paralelización."""
    
    def __init__(self, openai_api_key: str, max_concurrent: int = 10):
        self.client = OpenAI(api_key=openai_api_key)
        self.async_client = AsyncOpenAI(api_key=openai_api_key)
        self.model = "gpt-4o-mini"
        self.max_concurrent = max_concurrent
    
    async def synthesize_article_async(self, articles_content: List[str]) -> Dict[str, str]:
        """
        Sintetiza múltiples artículos en uno solo (versión async).
        
        Args:
            articles_content: Lista de contenidos de artículos que hablan de lo mismo
            
        Returns:
            Dict con title, content, summary
        """
        if not articles_content:
            return {
                "title": "Sin contenido",
                "content": "No se pudo generar el artículo.",
                "summary": ""
            }
        
        # Si solo hay un artículo, no es necesario sintetizar
        if len(articles_content) == 1:
            return self._extract_from_single_article(articles_content[0])
        
        # Preparar prompt
        prompt = self._build_synthesis_prompt(articles_content)
        
        try:
            response = await self.async_client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Eres un periodista profesional experto en crear artículos. "
                            "Tu tarea es crear UN artículo unificado y completo a partir de múltiples "
                            "fuentes que hablan del mismo tema. Debes:\n"
                            "1. Combinar toda la información relevante\n"
                            "2. Eliminar redundancias\n"
                            "3. Mantener todos los datos importantes (fechas, nombres, cifras)\n"
                            "4. Escribir de forma clara y profesional\n"
                            "5. Usar formato markdown para estructura (títulos, subtítulos, listas, etc)\n"
                            "6. NO inventar información que no esté en las fuentes\n"
                            "7. NO abusar de las listas"
                        )
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
            )
            
            article_text = response.choices[0].message.content
            return self._parse_generated_article(article_text)
        
        except Exception as e:
            logger.error(f"Error sintetizando artículo: {e}")
            return {
                "title": "Error al generar artículo",
                "content": f"No se pudo generar el artículo: {str(e)}",
                "summary": ""
            }
    
    def _build_synthesis_prompt(self, articles_content: List[str]) -> str:
        """Construye el prompt para sintetizar artículos."""
        sources_text = "\n\n---\n\n".join([
            f"**FUENTE {i+1}:**\n{content}" 
            for i, content in enumerate(articles_content)
        ])
        
        return f"""Tienes {len(articles_content)} artículos de diferentes fuentes que hablan sobre el mismo tema.

{sources_text}

---

Tu tarea es crear UN artículo unificado que:
1. Tenga un título claro y descriptivo
2. Incluya TODA la información relevante de todas las fuentes
3. Esté bien estructurado con secciones si es necesario
4. Sea fácil de leer y comprensible
5. Mantenga todos los datos importantes (fechas, nombres, cifras, etc)

Formato de salida (IMPORTANTE - usa exactamente este formato):

# [TÍTULO DEL ARTÍCULO]

## [Subtítulo 1]

[Contenido del subtítulo 1]

## [Subtítulo 2]

[Contenido del subtítulo 2]

## Conclusión

[Conclusión del artículo]

---

Recuerda: combina la información sin inventar nada nuevo. Si hay contradicciones entre fuentes, menciónalas."""
    
    def _extract_from_single_article(self, content: str) -> Dict[str, str]:
        """Extrae título y contenido de un artículo único."""
        lines = content.split('\n')
        
        title = "Artículo"
        for line in lines:
            line = line.strip()
            if line and len(line) > 10:
                title = line.replace('Título:', '').replace('#', '').strip()
                break
        
        return {
            "title": title[:200],
            "content": content,
            "summary": title
        }
    
    def _parse_generated_article(self, article_text: str) -> Dict[str, str]:
        """Parsea el artículo generado para extraer título, resumen y contenido."""
        lines = article_text.split('\n')
        
        title = "Artículo Sintetizado"
        summary = ""
        content = article_text
        
        for i, line in enumerate(lines):
            line = line.strip()
            if line.startswith('#') and not line.startswith('##'):
                title = line.replace('#', '').strip()
                content = '\n'.join(lines[i+1:]).strip()
                break
        
        for line in lines:
            if '**Resumen:**' in line or '**Summary:**' in line:
                summary = line.split('**', 2)[-1].strip()
                break
        
        return {
            "title": title[:200],
            "content": content,
            "summary": summary[:300] if summary else title
        }
    
    async def _synthesize_group_async(
        self,
        group: List[str],
        url_to_content: Dict[str, str]
    ) -> Dict[str, str]:
        """Sintetiza un grupo de artículos (versión async)."""
        if len(group) > 1:
            articles_content = [
                url_to_content.get(url, "") 
                for url in group 
                if url in url_to_content
            ]
            
            articles_content = [c for c in articles_content if c]
            
            if articles_content:
                article = await self.synthesize_article_async(articles_content)
                article['group_size'] = len(group)
                article['source_urls'] = group
                return article
        else:
            url = group[0]
            content = url_to_content.get(url, "")
            if content:
                article = self._extract_from_single_article(content)
                article['group_size'] = 1
                article['source_urls'] = group
                return article
        
        return None
    
    async def synthesize_all_groups_async(
        self, 
        groups: List[List[str]], 
        url_to_content: Dict[str, str],
        progress_callback=None
    ) -> List[Dict[str, str]]:
        """
        Sintetiza todos los grupos en paralelo (hasta 10 requests concurrentes).
        
        Args:
            groups: Lista de grupos
            url_to_content: Dict {url: contenido}
            progress_callback: Función para reportar progreso
            
        Returns:
            Lista de artículos sintetizados
        """
        # Semáforo para limitar concurrencia a 10
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def process_group_with_semaphore(i, group):
            async with semaphore:
                article = await self._synthesize_group_async(group, url_to_content)
                
                if progress_callback:
                    progress_callback((i + 1) / len(groups))
                
                return article
        
        # Procesar todos los grupos en paralelo
        tasks = [
            process_group_with_semaphore(i, group) 
            for i, group in enumerate(groups)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # Filtrar None
        synthesized_articles = [r for r in results if r is not None]
        
        logger.info(f"Sintetizados {len(synthesized_articles)} artículos de {len(groups)} grupos (paralelo)")
        return synthesized_articles
    
    def synthesize_all_groups(
        self, 
        groups: List[List[str]], 
        url_to_content: Dict[str, str],
        progress_callback=None
    ) -> List[Dict[str, str]]:
        """
        Sintetiza todos los grupos (wrapper sincrónico).
        Ejecuta hasta 10 requests a OpenAI en paralelo.
        
        Args:
            groups: Lista de grupos
            url_to_content: Dict {url: contenido}
            progress_callback: Función para reportar progreso
            
        Returns:
            Lista de artículos sintetizados
        """
        return asyncio.run(
            self.synthesize_all_groups_async(groups, url_to_content, progress_callback)
        )