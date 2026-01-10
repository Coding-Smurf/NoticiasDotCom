import streamlit as st
import json
from datetime import datetime, timedelta

from services.scraper_service import NewsScraperService
from services.deduplication_service import DeduplicationService
from services.article_content_extractor import ArticleContentExtractor
from services.article_synthesis_service import ArticleSynthesisService
from config.sources import NEWS_SOURCES

st.set_page_config(
    page_title="Dashboard - Monitor de Noticias",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Monitor de Noticias")

if 'scraper' not in st.session_state:
    st.session_state.scraper = NewsScraperService(timeout=15)

scraper = st.session_state.scraper

# Sidebar config
with st.sidebar:
    st.header("⚙️ Configuración")
    
    days_threshold = st.slider(
        "Días recientes",
        min_value=1,
        max_value=90,
        value=7,
        step=1,
        help="Filtrar artículos de los últimos N días"
    )

# Main action button
if st.button("🔍 Escanear y Agrupar Noticias", use_container_width=True, type="primary"):
    # Obtener API key de secrets
    try:
        openai_api_key = st.secrets["OPENAI_API_KEY"]
    except KeyError:
        st.error("❌ No se encontró OPENAI_API_KEY en .streamlit/secrets.toml")
        st.info("Crea el archivo `.streamlit/secrets.toml` con:\n```\nOPENAI_API_KEY = \"sk-your-key-here\"\n```")
        st.stop()
    
    # Step 1: Extract URLs
    with st.spinner("📡 Extrayendo URLs de noticias..."):
        all_articles = scraper.scrape_multiple(NEWS_SOURCES)
        
        if not all_articles:
            st.error("No se encontraron artículos")
            st.stop()
        
        # Filter by date
        cutoff_date = datetime.now() - timedelta(days=days_threshold)
        filtered_articles = []
        no_date_count = 0
        old_date_count = 0
        
        for article in all_articles:
            if not article.get('date'):
                no_date_count += 1
                continue
            
            try:
                article_date = datetime.fromisoformat(article['date'].replace('Z', '+00:00'))
                if article_date.replace(tzinfo=None) >= cutoff_date:
                    filtered_articles.append(article)
                else:
                    old_date_count += 1
            except (ValueError, AttributeError):
                no_date_count += 1
        
        st.session_state.articles_data = filtered_articles
        
        st.success(f"✅ {len(filtered_articles)} artículos extraídos")
        if no_date_count > 0 or old_date_count > 0:
            st.info(f"ℹ️ Excluidos: {no_date_count} sin fecha, {old_date_count} antiguos")
    
    # Step 2: Extract content
    with st.spinner("📄 Extrayendo contenido de artículos..."):
        extractor = ArticleContentExtractor()
        urls = [a['url'] for a in st.session_state.articles_data]
        
        progress_bar = st.progress(0)
        url_contents = {}
        
        for i, url in enumerate(urls):
            content = extractor.extract_content(url)
            if content:
                url_contents[url] = content
            progress_bar.progress((i + 1) / len(urls))
        
        progress_bar.empty()
        
        st.session_state.url_contents = url_contents
        
        st.success(f"✅ Contenido extraído de {len(url_contents)}/{len(urls)} artículos")
    
    # Step 3: Group similar articles
    with st.spinner("🔗 Agrupando artículos similares..."):
        try:
            deduplicator = DeduplicationService(
                similarity_threshold=0.75,
                bm25_weight=0.30,
                openai_api_key=openai_api_key
            )
            groups = deduplicator.group_similar_articles(url_contents)
            
            st.session_state.groups = groups
            st.session_state.deduplicator_instance = deduplicator
            
            stats = deduplicator.get_statistics(groups)
            
            st.success(f"✅ {stats['duplicated_groups']} grupos con duplicados encontrados")
            
        except Exception as e:
            st.error(f"Error al agrupar: {e}")
            import traceback
            st.code(traceback.format_exc())
            st.stop()
    
    # Step 4: Synthesize articles
    with st.spinner("✨ Sintetizando artículos con GPT-4o-mini..."):
        try:
            synthesizer = ArticleSynthesisService(openai_api_key)
            
            progress_bar = st.progress(0)
            
            def update_progress(progress):
                progress_bar.progress(progress)
            
            synthesized = synthesizer.synthesize_all_groups(
                groups, 
                url_contents,
                progress_callback=update_progress
            )
            
            progress_bar.empty()
            
            st.session_state.synthesized_articles = synthesized
            
            st.success(f"✅ {len(synthesized)} artículos sintetizados")
            
        except Exception as e:
            st.error(f"Error al sintetizar: {e}")
            import traceback
            st.code(traceback.format_exc())

# Display synthesized articles if available
if 'synthesized_articles' in st.session_state:
    st.markdown("---")
    st.markdown("### 📰 Noticias Sintetizadas")
    
    articles = st.session_state.synthesized_articles
    
    # Summary metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Artículos", len(articles))
    with col2:
        multi_source = sum(1 for a in articles if a.get('group_size', 1) > 1)
        st.metric("Multi-fuente", multi_source)
    with col3:
        single_source = sum(1 for a in articles if a.get('group_size', 1) == 1)
        st.metric("Fuente única", single_source)
    
    st.markdown("---")
    
    # Display articles as clickable list
    for i, article in enumerate(articles):
        title = article.get('title', 'Sin título')
        summary = article.get('summary', '')
        group_size = article.get('group_size', 1)
        
        # Icon based on group size
        icon = "📰" if group_size == 1 else f"📊 ({group_size} fuentes)"
        
        # Create expandable article
        with st.expander(f"{icon} {title}", expanded=False):
            if summary and summary != title:
                st.markdown(f"**{summary}**")
                st.markdown("---")
            
            # Display article content with markdown
            st.markdown(article.get('content', ''))
            
            # Show sources if multiple
            if group_size > 1:
                st.markdown("---")
                st.markdown("**Fuentes:**")
                for url in article.get('source_urls', []):
                    st.markdown(f"- {url}")