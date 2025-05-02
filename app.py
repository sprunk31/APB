import streamlit as st
import pandas as pd
import os
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz

# Tijdzone instellen
amsterdam = pytz.timezone("Europe/Amsterdam")

# Google Sheets via secrets
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDENTIALS = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=SCOPE
)
SHEET_ID = "11svyug6tDpb8YfaI99RyALevzjSSLn1UshSwVQYlcNw"
SHEET_NAME = "Logboek Afvalcontainers"

def voeg_toe_aan_logboek(data_dict):
    try:
        client = gspread.authorize(CREDENTIALS)
        sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
        sheet.append_row([
            data_dict["Locatiecode"],
            data_dict["Inhoudstype"],
            data_dict["Vulgraad"],
            data_dict["Actie"],
            data_dict["Datum"]
        ])
    except Exception as e:
        st.error("⚠️ Fout bij loggen naar Google Sheets:")
        st.exception(e)

# Dataset pad
DATA_PATH = "huidige_dataset.csv"

# Laad eerdere dataset
if 'df1_filtered' not in st.session_state and os.path.exists(DATA_PATH):
    st.session_state['df1_filtered'] = pd.read_csv(DATA_PATH)

# UI
st.set_page_config(page_title="Afvalcontainerbeheer", layout="wide")
st.title("♻️ Afvalcontainerbeheer Dashboard")

rol = st.selectbox("👤 Kies je rol", ["Gebruiker", "Admin"])

# -------------------------- ADMIN --------------------------
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
        df1_filtered['Verwijderen'] = False

        st.session_state['df1_filtered'] = df1_filtered
        df1_filtered.to_csv(DATA_PATH, index=False)
        st.success("✅ Gegevens verwerkt en gedeeld.")

# -------------------------- GEBRUIKER --------------------------
if rol == "Gebruiker" and 'df1_filtered' in st.session_state:
    df = st.session_state['df1_filtered']
    zichtbaar = [
        "Container name", "Address", "City", "Location code", "Content type",
        "Fill level (%)", "CombinatieTelling", "GemiddeldeVulgraad",
        "OpRoute", "Extra meegegeven", "Verwijderen"
    ]

    # Splits op basis van status
    nog_bewerkbaar = df[df["Extra meegegeven"] == False]
    al_gelogd = df[df["Extra meegegeven"] == True]

    # Bewerken
    st.subheader("✏️ Bewerkbare rijen")
    editable_df = st.data_editor(
        nog_bewerkbaar[zichtbaar],
        use_container_width=True,
        num_rows="dynamic",
        key="editor",
        column_config={
            "Location code": st.column_config.TextColumn("Location code", filter=True),
            "Content type": st.column_config.TextColumn("Content type", filter=True),
            "Fill level (%)": st.column_config.NumberColumn("Fill level (%)", filter=True),
        },
        disabled=[col for col in zichtbaar if col not in ["Extra meegegeven", "Verwijderen"]]
    )

    # Opslaan
    st.subheader("💾 Sla wijzigingen op")
    if st.button("✅ Wijzigingen toepassen en loggen"):
        gewijzigd = editable_df != nog_bewerkbaar[zichtbaar]
        gewijzigde_rijen = gewijzigd.any(axis=1)
        verwijderde_rijen = editable_df[editable_df["Verwijderen"] == True]

        wijzigingen_geteld = 0
        verwijderingen_geteld = 0

        for index in editable_df[gewijzigde_rijen].index:
            nieuwe_waarde = editable_df.at[index, "Extra meegegeven"]
            oude_waarde = st.session_state['df1_filtered'].at[index, "Extra meegegeven"]

            if nieuwe_waarde != oude_waarde:
                st.session_state['df1_filtered'].at[index, "Extra meegegeven"] = nieuwe_waarde

                log_entry = {
                    "Locatiecode": editable_df.at[index, 'Location code'],
                    "Inhoudstype": editable_df.at[index, 'Content type'],
                    "Vulgraad": editable_df.at[index, 'Fill level (%)'],
                    "Actie": "Extra meegegeven aangevinkt",
                    "Datum": datetime.now(amsterdam).strftime("%Y-%m-%d %H:%M:%S")
                }
                voeg_toe_aan_logboek(log_entry)
                wijzigingen_geteld += 1

        # Verwijderen
        for index in verwijderde_rijen.index:
            st.session_state['df1_filtered'].drop(index, inplace=True)
            log_entry = {
                "Locatiecode": verwijderde_rijen.at[index, 'Location code'],
                "Inhoudstype": verwijderde_rijen.at[index, 'Content type'],
                "Vulgraad": verwijderde_rijen.at[index, 'Fill level (%)'],
                "Actie": "Record verwijderd",
                "Datum": datetime.now(amsterdam).strftime("%Y-%m-%d %H:%M:%S")
            }
            voeg_toe_aan_logboek(log_entry)
            verwijderingen_geteld += 1

        st.session_state['df1_filtered'].to_csv(DATA_PATH, index=False)
        st.success(f"✔️ {wijzigingen_geteld} wijziging(en) en {verwijderingen_geteld} verwijdering(en) verwerkt.")

    # Alleen-lezen
    st.subheader("🔒 Reeds gelogde rijen")
    st.dataframe(al_gelogd[zichtbaar[:-1]], use_container_width=True)


#--