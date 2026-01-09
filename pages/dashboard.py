import streamlit as st
import json
from datetime import datetime
from utils.news_scraper import NewsScraper

st.set_page_config(
    page_title="Dashboard - Monitor de Noticias",
    page_icon="📊",
    layout="wide",
)

# Initialize scraper
if 'scraper' not in st.session_state:
    api_key = st.secrets.get("OPENAI_API_KEY", "")
    st.session_state.scraper = NewsScraper(api_key)

scraper = st.session_state.scraper

st.title("📊 Dashboard de Noticias")

# Sidebar configuration
with st.sidebar:
    st.header("⚙️ Configuración")
    
    recent_days = st.slider(
        "Días recientes",
        min_value=1,
        max_value=90,
        value=30,
        help="Filtrar noticias de los últimos N días"
    )
    
    max_workers_sites = st.slider(
        "Workers (Sitios)",
        min_value=1,
        max_value=10,
        value=5,
        help="Sitios procesados en paralelo"
    )
    
    max_workers_articles = st.slider(
        "Workers (Artículos)",
        min_value=1,
        max_value=20,
        value=10,
        help="Artículos procesados en paralelo"
    )
    
    max_workers_summaries = st.slider(
        "Workers (Resúmenes)",
        min_value=1,
        max_value=10,
        value=5,
        help="Resúmenes generados en paralelo"
    )
    
    request_delay = st.number_input(
        "Delay entre requests (seg)",
        min_value=0.0,
        max_value=5.0,
        value=1.0,
        step=0.5
    )

# Update config
scraper.update_config({
    "recent_days": recent_days,
    "max_workers_sites": max_workers_sites,
    "max_workers_articles": max_workers_articles,
    "max_workers_summaries": max_workers_summaries,
    "request_delay": request_delay,
})

# Main content
st.markdown("---")

# File upload
uploaded_file = st.file_uploader(
    "📁 Sube tu archivo CSV con las fuentes",
    type=['csv'],
    help="El CSV debe tener columnas: siteURL, web (1 para activado)"
)

if uploaded_file:
    st.success(f"✅ Archivo cargado: {uploaded_file.name}")
    
    if st.button("🔍 Buscar Noticias", type="primary", use_container_width=True):
        with st.spinner("🔄 Procesando sitios..."):
            # Progress tracking
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Load sites from uploaded file
            sites = scraper.load_sites_from_file(uploaded_file)
            status_text.text(f"📍 {len(sites)} sitios cargados")
            progress_bar.progress(10)
            
            if not sites:
                st.error("❌ No se encontraron sitios válidos en el CSV")
            else:
                # Process sites
                status_text.text("🌐 Extrayendo noticias...")
                all_news = scraper.process_all_sites(sites)
                progress_bar.progress(50)
                
                if not all_news:
                    st.warning("⚠️ No se encontraron noticias recientes")
                else:
                    # Group and summarize
                    status_text.text("🔗 Agrupando duplicados...")
                    groups = scraper.group_duplicates(all_news)
                    progress_bar.progress(70)
                    
                    status_text.text("📝 Generando resúmenes...")
                    all_news = scraper.summarize_groups(groups, all_news)
                    progress_bar.progress(100)
                    
                    # Store results
                    st.session_state.results = all_news
                    st.session_state.groups = groups
                    
                    status_text.text("✅ Proceso completado")
                    st.balloons()

# Display results
if 'results' in st.session_state and st.session_state.results:
    st.markdown("---")
    st.header("📊 Resultados")
    
    results = st.session_state.results
    groups = st.session_state.groups
    
    # Stats
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📰 Total Artículos", len(results))
    with col2:
        unique_sources = len(set(article.get('source', '') for article in results))
        st.metric("🌐 Fuentes", unique_sources)
    with col3:
        st.metric("📑 Grupos", len(groups))
    with col4:
        duplicates = sum(1 for g in groups if len(g) > 1)
        st.metric("🔗 Duplicados", duplicates)
    
    # Display groups
    st.markdown("### 📋 Grupos de Noticias")
    
    for group_idx, group_indices in enumerate(groups, 1):
        with st.expander(
            f"**Grupo {group_idx}** - {len(group_indices)} artículo(s)",
            expanded=(len(group_indices) > 1)
        ):
            # Summary
            first_article = results[group_indices[0]]
            if first_article.get('summary'):
                st.info(f"**Resumen:** {first_article['summary']}")
            
            # Articles
            for i in group_indices:
                article = results[i]
                
                st.markdown(f"""
                **{article['title']}**
                - 🔗 [{article['url']}]({article['url']})
                - 📍 Fuente: `{article['source']}`
                - 📅 Fecha: {article.get('date', 'N/A')}
                """)
                
                if i < group_indices[-1]:
                    st.markdown("---")
    
    # Download button
    st.markdown("---")
    
    json_str = json.dumps(results, ensure_ascii=False, indent=2)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    st.download_button(
        label="💾 Descargar JSON",
        data=json_str,
        file_name=f"noticias_{timestamp}.json",
        mime="application/json",
        use_container_width=True
    )

else:
    st.info("👆 Sube un archivo CSV y haz clic en 'Buscar Noticias' para comenzar")