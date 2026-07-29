import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

st.title("Find Your Village")
st.write("Build your team")

st.subheader("Tell us about your situation and we will help find you support")

@st.cache_data(ttl=600)
def load_providers():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    client = gspread.authorize(creds)
    sheet = client.open_by_key(st.secrets["providers"]).sheet1
    return pd.DataFrame(sheet.get_all_records())

df=load_providers()
st.dataframe(df)