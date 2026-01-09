import streamlit as st

st.set_page_config(
    page_title="Monitor de Noticias",
    page_icon="📰",
    layout="wide",
)

st.title("📰 Monitor de Noticias")

st.markdown("""
## Bienvenido al Monitor de Noticias

Esta aplicación te permite:
- 🔍 Buscar y analizar noticias recientes de múltiples fuentes
- 🤖 Identificar duplicados automáticamente con IA
- 📊 Generar resúmenes de las noticias encontradas
- 💾 Exportar los resultados en formato JSON

### Cómo usar la aplicación

1. **Ve a la página "Dashboard"** usando el menú lateral
2. **Sube tu archivo CSV** con las fuentes de noticias (columnas: `siteURL`, `web`)
3. **Configura los parámetros** de búsqueda (días recientes, workers, etc.)
4. **Haz clic en "Buscar Noticias"** y espera los resultados
5. **Revisa los grupos** de noticias y sus resúmenes
6. **Descarga el JSON** con todos los resultados

---

""")

st.info("👈 Usa el menú lateral para navegar al Dashboard")

# Footer
st.markdown("---")
st.caption("Monitor de Noticias | Powered by OpenAI & Streamlit")