no_ai.pyimport streamlit as st

st.title("Find Your Village")
st.write("Build your team")

st.subheader("Tell us about your situation and we will help find you support")

if st.button("No AI Plz"):
    st.switch_page("pages/no_ai.py")

if st.button("AI Plz"):
    st.switch_page("pages/ai.py")
