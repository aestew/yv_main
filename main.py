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
col_logo, col_title = st.columns([1, 6], vertical_alignment="center")
with col_logo:
    st.image("olive_tree.png", width=110)
with col_title:
    st.title("Find Your Village")
    st.caption("Build a support system to help your child thrive")
    st.info(
        "This tool helps you explore support options and is not medical, legal, "
        "or eligibility advice. Please verify details directly with each provider.",
        icon=":material/info:",
    )
st.markdown("""
<style>
[data-testid="stExpander"] summary p {
    font-size: 1.25rem;
    font-weight: 600;
    color: #B08968;
}
</style>
""", unsafe_allow_html=True)

st.write("")

with st.expander("Tell us about your situation", expanded=True):
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        who = st.pills(
            "Who are you looking for support for?",
            options_from("who_needs_help"),
            selection_mode="multi",
        )
    with col2:
        age = st.pills(
            "How old is your child?",
            options_from("age_range"),
            selection_mode="single",
        )
    with col3:
        areas_display = st.pills(
            "What are you looking for help with?",
            [short_label(o) for o in options_from("support_areas")],
            selection_mode="multi",
        )
        areas = [full_label(a) for a in areas_display]
    with col4:
        where = st.pills(
            "Where do you need support?",
            options_from("where_support"),
            selection_mode="multi",
        )

with st.expander("Specify Payment Preferences", expanded=False):
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
    for service_type, group in results.groupby("service_type", sort=False):
        with st.expander(service_type):
            st.write(group.iloc[0]["description"])
            st.divider()
            for _, row in group.iterrows():
                c1, c2, c3, c4 = st.columns([3, 1, 2, 2])
                with c1:
                    if row.get("website"):
                        st.markdown(f"**[{row['org']}]({row['website']})**")
                    else:
                        st.markdown(f"**{row['org']}**")
                with c2:
                    if row.get("email_contact"):
                        st.markdown(f"[Email](mailto:{row['email_contact']})")
                with c3:
                    if row.get("phone"):
                        st.markdown(str(row["phone"]))
                with c4:
                    if row.get("payment_ops"):
                        st.markdown(str(row["payment_ops"]))
st.write("")  # spacer
with st.expander("Disclaimer"):
    st.write(
        "Find Your Village is an informational tool to help you explore support "
        "options. It is not medical, legal, or eligibility advice, and it does not "
        "guarantee services or determine whether your child qualifies for any program. "
        "Official decisions come from your school district, Regional Center, or the "
        "individual provider.\n\n"
        "This tool does not provide medical advice and is not a substitute for care "
        "from a qualified professional. Always consult a physician or other qualified "
        "provider before making medical decisions for your child. If you are "
        "experiencing a medical emergency, call 911 immediately.\n\n"
        "Listings are provided for convenience and may change; please verify details "
        "directly with each organization."
    )