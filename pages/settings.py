import streamlit as st

st.title("⚙️ Settings")

dark_mode = st.toggle("Enable dark mode")
st.write("Dark mode:", dark_mode)
