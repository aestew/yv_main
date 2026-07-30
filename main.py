import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

st.title("Find Your Village")

st.subheader("Tell us about your situation and we will help find you support")

### Helper Functions ###

## Load in google sheet
@st.cache_data(ttl=600)
def load_data():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    client = gspread.authorize(creds)
    book = client.open_by_key(st.secrets["sheet_id"])
    providers = pd.DataFrame(book.worksheet("providers").get_all_records())
    descriptions = pd.DataFrame(book.worksheet("service_description").get_all_records())
    return providers, descriptions

df, desc = load_data()

def options_from(column):
    """Split multi-value cells into individual unique options."""
    values = set()
    for cell in df[column].dropna():
        for part in str(cell).split(","):
            values.add(part.strip())
    return sorted(values)


## Create DF
df["service_type"] = df["service_type"].str.strip()
desc["service_type"] = desc["service_type"].str.strip()
df = df.merge(desc, on="service_type", how="left")

## Questions
st.header("Build your team")

who = st.pills(
    "Who are you looking for support for?",
    options_from("who_needs_help"),
    selection_mode="multi",
)

age = st.pills(
    "How old is your child?",
    options_from("age_range"),
    selection_mode="multi",
)

areas = st.pills(
    "What are you looking for help with?",
    options_from("support_areas"),
    selection_mode="multi",
)

where = st.pills(
    "Where do you need support?",
    options_from("where_support"),
    selection_mode="multi",
)

def cell_has(cell, picks):
    """True if any of the parent's picks appears in this cell."""
    text = str(cell).lower()
    return any(p.lower() in text for p in picks)

def data_chips(cell):
    """Split an age_range cell into individual chips: '0-3 3-5 6+' -> ['0-3','3-5','6+']"""
    return [c.strip() for c in str(cell).split(",") if c.strip()]


## Build Row Score
def score_row(row):
    # hard filter: age
    if age:
        row_ages = data_chips(row["age_range"])
        if not any(a in row_ages for a in age):
            return 0

    # hard filter: who
    if who:
        row_who = data_chips(row["who_needs_help"])
        if not any(w in row_who for w in who):
            return 0

    # hard filter: where
    if where:
        row_where = data_chips(row["where_support"])
        if not any(x in row_where for x in where):
            return 0

    return 1

# score every provider, keep only those with at least one match, take top 3
scored = df.copy()
scored["match_score"] = scored.apply(score_row, axis=1)
results = scored[scored["match_score"] > 0].sort_values(
    "match_score", ascending=False
).head(3)


st.header("Build Your Village")

if results.empty:
    st.write("No matches yet — try picking a few options above.")
else:
    # group rows by service_type so shared cells can span
    rows_html = ""
    grouped = results.groupby("service_type", sort=False)
    for service_type, group in grouped:
        n = len(group)
        for i, (_, row) in enumerate(group.iterrows()):
            website = f'<a href="{row["website"]}">Website</a>' if row.get("website") else ""
            email = f'<a href="mailto:{row["email_contact"]}">Email</a>' if row.get("email_contact") else ""
            phone = row.get("phone", "")
            organization = row.get("org", "")
            rows_html += "<tr>"
            if i == 0:  # only first row of the group prints the merged cells
                rows_html += f'<td rowspan="{n}">{service_type}</td>'
                rows_html += f'<td rowspan="{n}">{group.iloc[0]["description"]}</td>'
            rows_html += f"<td>{organization}</td><td>{website}</td><td>{email}</td><td>{phone}</td>"
            rows_html += "</tr>"

    table_html = f"""
    <table border="1" style="border-collapse:collapse; width:100%;">
      <thead>
        <tr>
          <th>Service Type</th><th>Description</th><th>Organization</th>
          <th>Website</th><th>Email</th><th>Phone</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
    """
    st.markdown(table_html, unsafe_allow_html=True)