import streamlit as st

st.title("📈 Analytics")

option = st.selectbox(
    "Choose a metric",
    ["Revenue", "Users", "Conversion Rate"]
)

st.success(f"Selected metric: {option}")
