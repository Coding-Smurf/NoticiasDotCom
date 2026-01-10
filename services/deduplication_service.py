"""
Servicio de deduplicación de noticias usando clustering jerárquico híbrido.
Combina BM25 (similitud léxica) + embeddings OpenAI (similitud semántica).
"""

from typing import List, Dict, Tuple
import logging
import numpy as np
from openai import OpenAI
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import umap
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform
import re

logger = logging.getLogger(__name__)


class DeduplicationService:
    """Servicio para detectar y agrupar artículos duplicados usando clustering híbrido."""
    
    def __init__(self, similarity_threshold: float = 0.85, bm25_weight: float = 0.3, openai_api_key: str = None):
        """
        Args:
            similarity_threshold: Umbral de similitud combinada (0.0 a 1.0)
            bm25_weight: Peso de BM25 vs embeddings (0.3 = 30% BM25, 70% embeddings)
            openai_api_key: API key de OpenAI
        """
        self.similarity_threshold = similarity_threshold
        self.bm25_weight = bm25_weight
        
        if openai_api_key:
            logger.info("Inicializando cliente OpenAI...")
            self.client = OpenAI(api_key=openai_api_key)
            logger.info("Cliente OpenAI listo ✓")
        else:
            raise ValueError("Se requiere openai_api_key")
        
        # Para almacenar embeddings y poder hacer PCA después
        self.last_embeddings = None
        self.last_urls = None
        self.last_cluster_labels = None
    
    def _preprocess_text(self, text: str) -> str:
        """Preprocesa texto para BM25: lowercase y tokens."""
        text = text.lower()
        # Mantener palabras importantes
        text = re.sub(r'[^\w\s]', ' ', text)
        return text
    
    def _compute_bm25_similarity(self, texts: List[str]) -> np.ndarray:
        """
        Calcula similitud BM25 entre textos.
        
        Returns:
            Matriz de similitud BM25 (n_samples, n_samples)
        """
        # Preprocesar textos
        processed_texts = [self._preprocess_text(t) for t in texts]
        
        # TF-IDF como aproximación de BM25
        vectorizer = TfidfVectorizer(
            max_features=500,
            ngram_range=(1, 2),  # Unigrams y bigrams
            min_df=1,
            max_df=0.8
        )
        
        tfidf_matrix = vectorizer.fit_transform(processed_texts)
        bm25_similarity = cosine_similarity(tfidf_matrix)
        
        return bm25_similarity
    
    def _get_openai_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Obtiene embeddings de OpenAI en batch.
        
        Returns:
            Array de embeddings (n_samples, embedding_dim)
        """
        logger.info(f"Solicitando embeddings a OpenAI para {len(texts)} textos...")
        
        # Truncar textos si son muy largos (OpenAI tiene límite de ~8000 tokens)
        truncated_texts = [text[:8000] for text in texts]
        
        # Llamada a la API de OpenAI
        response = self.client.embeddings.create(
            model="text-embedding-3-small",
            input=truncated_texts
        )
        
        # Extraer embeddings
        embeddings = np.array([item.embedding for item in response.data])
        
        logger.info(f"Embeddings recibidos: shape {embeddings.shape}")
        return embeddings
    
    def group_similar_articles(self, url_contents: Dict[str, str]) -> List[List[str]]:
        """
        Agrupa URLs de artículos similares usando clustering jerárquico híbrido.
        Combina BM25 (léxico) + embeddings OpenAI (semántico).
        
        Args:
            url_contents: Dict {url: contenido_texto}
            
        Returns:
            Lista de grupos, donde cada grupo es una lista de URLs similares
        """
        if not url_contents:
            return []
        
        # Filtrar URLs sin contenido
        valid_pairs = [(url, content) for url, content in url_contents.items() if content]
        
        if not valid_pairs:
            logger.warning("No hay artículos con contenido")
            return [[url] for url in url_contents.keys()]
        
        if len(valid_pairs) == 1:
            return [[valid_pairs[0][0]]]
        
        urls = [pair[0] for pair in valid_pairs]
        contents = [pair[1] for pair in valid_pairs]
        
        # 1. Generar embeddings con OpenAI
        embeddings = self._get_openai_embeddings(contents)
        semantic_similarity = cosine_similarity(embeddings)
        
        # 2. Calcular similitud BM25 (léxica)
        logger.info(f"Calculando similitud BM25...")
        bm25_similarity = self._compute_bm25_similarity(contents)
        
        # 3. Ajustar peso BM25 adaptativamente
        # Para pares del mismo dominio problemático, aumentar peso BM25
        from urllib.parse import urlparse
        domains = [urlparse(url).netloc for url in urls]
        
        # Dominios problemáticos (estructura similar pero contenido diferente)
        problematic_domains = {'boadilladigital.es', 'soydemadrid.com'}
        
        # Crear matriz de pesos adaptativos
        adaptive_weights = np.full((len(urls), len(urls)), self.bm25_weight)
        
        for i in range(len(urls)):
            for j in range(i + 1, len(urls)):
                if domains[i] == domains[j] and domains[i] in problematic_domains:
                    # Aumentar peso BM25 para artículos del mismo dominio problemático
                    adaptive_weights[i, j] = 0.6  # 60% BM25, 40% semántico
                    adaptive_weights[j, i] = 0.6
        
        # 4. Combinar similitudes con pesos adaptativos
        logger.info(f"Combinando similitudes (BM25: {self.bm25_weight:.0%} base, adaptativo para dominios problemáticos)...")
        hybrid_similarity = np.zeros_like(semantic_similarity)
        
        for i in range(len(urls)):
            for j in range(len(urls)):
                w = adaptive_weights[i, j]
                hybrid_similarity[i, j] = w * bm25_similarity[i, j] + (1 - w) * semantic_similarity[i, j]
        
        # Guardar embeddings para visualización
        self.last_embeddings = embeddings
        self.last_urls = urls
        
        # Convertir a distancia
        distance_matrix = 1 - hybrid_similarity
        np.fill_diagonal(distance_matrix, 0)
        distance_matrix = np.clip(distance_matrix, 0, 2)
        
        # Convertir a formato condensado para scipy
        condensed_distances = squareform(distance_matrix, checks=False)
        
        # Clustering jerárquico
        logger.info(f"Aplicando clustering jerárquico (threshold={1-self.similarity_threshold:.2f})...")
        linkage_matrix = linkage(condensed_distances, method='average')
        
        # Cortar el dendrograma
        distance_threshold = 1 - self.similarity_threshold
        cluster_labels = fcluster(linkage_matrix, distance_threshold, criterion='distance')
        
        # Agrupar URLs por cluster
        clusters = {}
        for idx, label in enumerate(cluster_labels):
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(urls[idx])
        
        groups = list(clusters.values())
        
        # Crear mapeo consistente con display
        url_to_display_group = {}
        for display_group_id, group in enumerate(groups, 1):
            for url in group:
                url_to_display_group[url] = display_group_id
        
        display_labels = np.array([url_to_display_group[url] for url in urls])
        self.last_cluster_labels = display_labels
        
        # Estadísticas
        multi_article_groups = [g for g in groups if len(g) > 1]
        single_article_groups = [g for g in groups if len(g) == 1]
        
        logger.info(f"Agrupados {len(urls)} URLs en {len(groups)} grupos")
        logger.info(f"  - {len(multi_article_groups)} grupos con múltiples artículos")
        logger.info(f"  - {len(single_article_groups)} artículos únicos")
        
        # Mostrar ejemplos con scores
        for i, group in enumerate(multi_article_groups[:3]):
            logger.info(f"Grupo {i+1} ({len(group)} artículos):")
            for j, url1 in enumerate(group[:2]):
                idx1 = urls.index(url1)
                logger.info(f"  - {contents[idx1][:80]}...")
                if j < len(group) - 1:
                    url2 = group[j + 1]
                    idx2 = urls.index(url2)
                    sem_score = semantic_similarity[idx1, idx2]
                    bm25_score = bm25_similarity[idx1, idx2]
                    hybrid_score = hybrid_similarity[idx1, idx2]
                    logger.info(f"    vs próximo: Sem={sem_score:.3f}, BM25={bm25_score:.3f}, Híbrido={hybrid_score:.3f}")
        
        return groups
    
    def get_umap_visualization_data(self) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """
        Genera datos para visualización UMAP 2D.
        
        UMAP preserva mejor la estructura local y global que PCA.
        
        Returns:
            Tuple of (umap_coords, cluster_labels, urls)
            - umap_coords: Array (n_samples, 2) con coordenadas 2D
            - cluster_labels: Array (n_samples,) con labels de cluster
            - urls: Lista de URLs correspondientes
        """
        if self.last_embeddings is None:
            raise ValueError("Debes ejecutar group_similar_articles() primero")
        
        # Aplicar UMAP para reducir a 2D
        logger.info("Aplicando UMAP para reducción dimensional...")
        
        reducer = umap.UMAP(
            n_components=2,
            n_neighbors=15,  # Balance entre estructura local y global
            min_dist=0.1,    # Mínima distancia entre puntos
            metric='cosine', # Métrica apropiada para embeddings
            random_state=42
        )
        
        umap_coords = reducer.fit_transform(self.last_embeddings)
        
        logger.info(f"UMAP completado: {umap_coords.shape}")
        
        return umap_coords, self.last_cluster_labels, self.last_urls
    
    def get_statistics(self, groups: List[List[str]]) -> Dict:
        """Genera estadísticas de los grupos."""
        total_articles = sum(len(group) for group in groups)
        duplicated_groups = [g for g in groups if len(g) > 1]
        single_groups = [g for g in groups if len(g) == 1]
        
        return {
            "total_articles": total_articles,
            "total_groups": len(groups),
            "unique_news": len(groups),
            "duplicated_groups": len(duplicated_groups),
            "single_articles": len(single_groups),
            "duplicate_rate": len(duplicated_groups) / len(groups) if groups else 0,
        }