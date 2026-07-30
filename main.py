import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

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

# Shorten long option labels for display, without touching the sheet.
LABEL_MAP = {
    "Parental Support / Home Organization": "Parental Support",
    "Using and Moving their Body": "Motor Skills",
}
REVERSE_MAP = {short: full for full, short in LABEL_MAP.items()}

def short_label(value):
    return LABEL_MAP.get(value, value)

def full_label(value):
    return REVERSE_MAP.get(value, value)


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
st.title("Find Your Village")
st.caption("FYV helps caregivers build a support system to help their child thrive.")

st.markdown("""
<style>
[data-testid="stExpander"] summary p {
    font-size: 1.25rem;
    font-weight: 600;
}
</style>
""", unsafe_allow_html=True)

st.write("")

with st.expander("Tell us about your situation", expanded=True):
    col1, col2, col3, col4 = st.columns([2, 1.2, 2, 2])

    with col1:
        who = st.multiselect(
            "Who are you looking for support for?",
            options_from("who_needs_help"),
        )
    with col2:
        age = st.selectbox(
            "How old is your child?",
            ["Any"] + options_from("age_range"),
        )
        if age == "Any":
            age = None
    with col3:
        areas_display = st.multiselect(
            "What are you looking for help with?",
            [short_label(o) for o in options_from("support_areas")],
        )
        areas = [full_label(a) for a in areas_display]
    with col4:
        where = st.multiselect(
            "Where do you need support?",
            options_from("where_support"),
        )

with st.expander("Specify Payment Preferences", expanded=True):
    def payment_label(value):
        return "Insurance" if "insurance" in value.lower() else value

    def payment_full(display):
        for v in options_from("payment_ops"):
            if payment_label(v) == display:
                return v
        return display

    payment_choices = ["Any"] + sorted({payment_label(v) for v in options_from("payment_ops")})
    payment_display = st.selectbox("Choose Preferred payment options", payment_choices)
    payment = None if payment_display == "Any" else payment_full(payment_display)

    wants_diagnosis = None
    if payment_display == "Insurance":
        diagnosis_choice = st.selectbox(
            "Most insurances require a diagnosis:",
            [
                "I'd like to get my child a diagnosis",
                "We're OK not getting a diagnosis",
            ],
        )
        wants_diagnosis = diagnosis_choice.startswith("I'd like")


st.write("")  # spacer before results
def cell_has(cell, picks):
    """True if any of the parent's picks appears in this cell."""
    text = str(cell).lower()
    return any(p.lower() in text for p in picks)

def data_chips(cell):
    """Split an age_range cell into individual chips: '0-3 3-5 6+' -> ['0-3','3-5','6+']"""
    return [c.strip() for c in str(cell).split(",") if c.strip()]


## Build Row Score
def score_row(row):
    # hard filters: age, who, where (these exclude)
    if age:
        row_ages = data_chips(row["age_range"])
        if age not in row_ages:
            return 0
    if who:
        row_who = data_chips(row["who_needs_help"])
        if not any(w in row_who for w in who):
            return 0
    if where:
        row_where = data_chips(row["where_support"])
        if not any(x in row_where for x in where):
            return 0

    # passed hard filters — base score of 1 so it still shows
    points = 1

    # hard filter: payment
    if payment:
        is_free = "free" in str(row["payment_ops"]).lower()

        if payment == "Direct pay":
            pass  # show everything, no payment filter

        elif payment == "Insurance":
            # insurance-accepting OR free
            accepts_insurance = "no insurance accepted" not in str(row["diagnosis_needed"]).lower()
            if not (accepts_insurance or is_free):
                return 0

        elif payment == "Free":
            if not is_free:
                return 0

        else:
            # any other specific payment type: match on payment_ops, but free always passes
            row_payments = data_chips(row["payment_ops"])
            if payment not in row_payments and not is_free:
                return 0

    # soft signal: areas add points for sorting (don't exclude)
    if areas:
        row_areas = data_chips(row["support_areas"])
        points += sum(1 for a in areas if a in row_areas)

    return points

# score every provider, keep only those with at least one match, take top 3
scored = df.copy()
scored["match_score"] = scored.apply(score_row, axis=1)
results = scored[scored["match_score"] > 0].sort_values(
    "match_score", ascending=False
).head(10)


CLAY = "#A8433A"
TEAL = "#3A7D6E"

st.header("Recommended Services")

if results.empty:
    st.write("No matches yet — try picking a few options above.")
else:
    rows_html = ""
    grouped = results.groupby("service_type", sort=False)
    for service_type, group in grouped:
        n = len(group)
        for i, (_, row) in enumerate(group.iterrows()):
            website = f'<a href="{row["website"]}" style="color:{TEAL};">Website</a>' if row.get("website") else ""
            email = f'<a href="mailto:{row["email_contact"]}" style="color:{TEAL};">Email</a>' if row.get("email_contact") else ""
            phone = row.get("phone", "")
            name = row.get("org", "")
            rows_html += "<tr>"
            if i == 0:
                rows_html += f'<td rowspan="{n}" style="color:{CLAY}; font-weight:600;">{service_type}</td>'
                rows_html += f'<td rowspan="{n}">{group.iloc[0]["description"]}</td>'
            rows_html += f"<td>{name}</td><td>{website}</td><td>{email}</td><td>{phone}</td>"
            rows_html += "</tr>"

    table_html = f"""
    <table border="1" style="border-collapse:collapse; width:100%;">
      <thead>
        <tr>
          <th>Service Type</th><th>Description</th><th>Name</th>
          <th>Website</th><th>Email</th><th>Phone</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
    """
    st.markdown(table_html, unsafe_allow_html=True)