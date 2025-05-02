import streamlit as st
import pandas as pd
import os
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# 📁 Google Sheets via secrets
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

CREDENTIALS = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=SCOPE
)

SHEET_ID = "11svyug6tDpb8YfaI99RyALevzjSSLn1UshSwVQYlcNw"  # <-- Vervang dit met je echte Google Sheet ID
SHEET_NAME = "Logboek Afvalcontainers"

def voeg_toe_aan_logboek(data_dict):
    try:
        client = gspread.authorize(CREDENTIALS)
        sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
        sheet.append_row([
            data_dict["Location code"],
            data_dict["Content type"],
            data_dict["Fill level (%)"],
            data_dict["Datum"]
        ])
    except Exception as e:
        import traceback
        st.error("⚠️ Fout bij loggen naar Google Sheets:")
        st.exception(e)

# 📁 Bestandslocatie dataset
DATA_PATH = "huidige_dataset.csv"

# Laad eerder opgeslagen dataset als deze bestaat
if 'df1_filtered' not in st.session_state and os.path.exists(DATA_PATH):
    st.session_state['df1_filtered'] = pd.read_csv(DATA_PATH)

# Pagina setup
st.set_page_config(page_title="Afvalcontainerbeheer", layout="wide")
st.title("♻️ Afvalcontainerbeheer Dashboard")

rol = st.selectbox("👤 Kies je rol", ["Gebruiker", "Admin"])

# -------------------------- ADMIN UPLOAD --------------------------
if rol == "Admin":
    st.header("📤 Upload Excel-bestanden")

    file1 = st.file_uploader("Bestand van Abel", type=["xlsx"])
    file2 = st.file_uploader("Bestand van Pieterbas", type=["xlsx"])

    if file1 and file2:
        df1 = pd.read_excel(file1)
        df2 = pd.read_excel(file2)

        df1_filtered = df1[
            (df1['Operational state'] == 'In use') &
            (df1['Status'] == 'In use') &
            (df1['On hold'] == 'No')
        ].copy()

        df1_filtered['CombinatieTelling'] = df1_filtered.groupby(['Location code', 'Content type'])['Content type'].transform('count')
        df1_filtered['GemiddeldeVulgraad'] = df1_filtered.groupby(['Location code', 'Content type'])['Fill level (%)'].transform('mean')
        df1_filtered['OpRoute'] = df1_filtered['Container name'].isin(df2['Omschrijving'].values).map({True: 'Ja', False: 'Nee'})
        df1_filtered['Extra meegegeven'] = False

        st.session_state['df1_filtered'] = df1_filtered
        df1_filtered.to_csv(DATA_PATH, index=False)
        st.success("✅ Gegevens succesvol verwerkt en gedeeld met gebruikers.")

# -------------------------- GEBRUIKER BEKIJKT & BEWERKT --------------------------
if rol == "Gebruiker" and 'df1_filtered' in st.session_state:
    st.header("📋 Containeroverzicht")

    df = st.session_state['df1_filtered']

    # Filters
    col1, col2 = st.columns(2)
    with col1:
        loc_filter = st.selectbox("🔍 Filter op Location code", ["Alles"] + sorted(df['Location code'].unique()))
    with col2:
        content_filter = st.selectbox("🔍 Filter op Content type", ["Alles"] + sorted(df['Content type'].unique()))

    df_display = df.copy()
    if loc_filter != "Alles":
        df_display = df_display[df_display['Location code'] == loc_filter]
    if content_filter != "Alles":
        df_display = df_display[df_display['Content type'] == content_filter]

    # Alleen geselecteerde kolommen tonen
    zichtbaar = [
        "Container name",
        "Address",
        "City",
        "Location code",
        "Content type",
        "Fill level (%)",
        "CombinatieTelling",
        "GemiddeldeVulgraad",
        "OpRoute",
        "Extra meegegeven"
    ]

    st.subheader("✅ Pas 'Extra meegegeven' direct aan")

    # Kolommen definiëren
    disabled_matrix = {
        "Extra meegegeven": [
            waarde is True for waarde in df_display["Extra meegegeven"]
        ]
    }

    editable_df = st.data_editor(
        df_display[zichtbaar],
        use_container_width=True,
        num_rows="dynamic",
        key="editor",
        disabled=disabled_matrix
    )

    # Wijzigingen detecteren
    st.subheader("💾 Sla wijzigingen op")
    if st.button("✅ Wijzigingen toepassen en loggen"):
        gewijzigd = editable_df != df_display[zichtbaar]
        gewijzigde_rijen = gewijzigd.any(axis=1)

        wijzigingen_geteld = 0

        for index in editable_df[gewijzigde_rijen].index:
            nieuwe_waarde = editable_df.at[index, "Extra meegegeven"]
            oude_waarde = st.session_state['df1_filtered'].at[index, "Extra meegegeven"]

            if nieuwe_waarde != oude_waarde:
                st.session_state['df1_filtered'].at[index, "Extra meegegeven"] = nieuwe_waarde

                log_entry = {
                    'Location code': editable_df.at[index, 'Location code'],
                    'Content type': editable_df.at[index, 'Content type'],
                    'Fill level (%)': editable_df.at[index, 'Fill level (%)'],
                    'Datum': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }

                voeg_toe_aan_logboek(log_entry)
                wijzigingen_geteld += 1

        # Sla dataset op
        st.session_state['df1_filtered'].to_csv(DATA_PATH, index=False)

        st.success(f"✔️ {wijzigingen_geteld} wijziging(en) opgeslagen en gelogd.")

    # Opslaan centrale dataset
    st.session_state['df1_filtered'].to_csv(DATA_PATH, index=False)
#--