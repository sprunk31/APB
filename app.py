import streamlit as st
import pandas as pd
from datetime import datetime
import os

st.set_page_config(page_title="Afvalcontainerbeheer", layout="wide")
st.title("♻️ Afvalcontainerbeheer Dashboard")

# 📁 Bestandspaden
LOG_PATH = "logboek_persistent.csv"
DATA_PATH = "huidige_dataset.csv"

# 🔁 Logboek laden als het al bestaat
if os.path.exists(LOG_PATH):
    st.session_state['logboek'] = pd.read_csv(LOG_PATH).to_dict(orient="records")
else:
    st.session_state['logboek'] = []

# 🧠 Dataset laden uit CSV als deze eerder is opgeslagen
if 'df1_filtered' not in st.session_state and os.path.exists(DATA_PATH):
    st.session_state['df1_filtered'] = pd.read_csv(DATA_PATH)

# 1. Rolselectie
rol = st.selectbox("👤 Kies je rol", ["Gebruiker", "Admin"])

# 2. Admin: bestanden uploaden
if rol == "Admin":
    st.header("📤 Upload Excel-bestanden (alleen voor Admin)")

    file1 = st.file_uploader("Selecteer bestand van Abel", type=["xlsx"])
    file2 = st.file_uploader("Selecteer bestand van Pieterbas", type=["xlsx"])

    if file1 and file2:
        df1 = pd.read_excel(file1)
        df2 = pd.read_excel(file2)

        # Filterregels
        df1_filtered = df1[
            (df1['Operational state'] == 'In use') &
            (df1['Status'] == 'In use') &
            (df1['On hold'] == 'No')
        ].copy()

        # Kolommen toevoegen
        df1_filtered['CombinatieTelling'] = df1_filtered.groupby(['Location code', 'Content type'])['Content type'].transform('count')
        df1_filtered['GemiddeldeVulgraad'] = df1_filtered.groupby(['Location code', 'Content type'])['Fill level (%)'].transform('mean')
        df1_filtered['OpRoute'] = df1_filtered['Container name'].isin(df2['Omschrijving'].values).map({True: 'Ja', False: 'Nee'})

        # Voeg bewerkbare kolom toe
        df1_filtered['Extra meegegeven'] = False

        # Opslaan
        st.session_state['df1_filtered'] = df1_filtered
        df1_filtered.to_csv(DATA_PATH, index=False)
        st.success("✅ Nieuwe gegevens verwerkt en gedeeld met gebruikers.")

# 3. Gebruikersinterface
if rol == "Gebruiker" and 'df1_filtered' in st.session_state:
    st.header("📋 Containeroverzicht en bewerking")

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

    # Kolommen uitsluiten
    uitsluiten = ['Device Location', 'External group ID']
    zichtbaar = [col for col in df_display.columns if col not in uitsluiten]

    st.subheader("🖊️ Pas 'Extra meegegeven' direct aan in de tabel")

    # Toon interactieve editor
    editable_df = st.data_editor(
        df_display[zichtbaar],
        use_container_width=True,
        num_rows="dynamic",
        key="editor",
        disabled=[col for col in zichtbaar if col != "Extra meegegeven"]
    )

    # Wijzigingen detecteren
    gewijzigd = editable_df != df_display[zichtbaar]
    gewijzigde_rijen = gewijzigd.any(axis=1)

    for index in editable_df[gewijzigde_rijen].index:
        oude_waarde = df_display.at[index, "Extra meegegeven"]
        nieuwe_waarde = editable_df.at[index, "Extra meegegeven"]

        if oude_waarde != nieuwe_waarde:
            st.session_state['df1_filtered'].at[index, "Extra meegegeven"] = nieuwe_waarde

            log_entry = {
                'Location code': df_display.at[index, 'Location code'],
                'Content type': df_display.at[index, 'Content type'],
                'Fill level (%)': df_display.at[index, 'Fill level (%)'],
                'Datum': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            st.session_state['logboek'].append(log_entry)

    # Opslaan
    pd.DataFrame(st.session_state['logboek']).to_csv(LOG_PATH, index=False)
    st.session_state['df1_filtered'].to_csv(DATA_PATH, index=False)

# 4. Logboek tonen en downloaden
if st.session_state['logboek']:
    st.header("📝 Logboek Extra Toevoegingen")
    log_df = pd.DataFrame(st.session_state['logboek'])

    st.dataframe(log_df, use_container_width=True)

    csv = log_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download logboek als CSV",
        data=csv,
        file_name=f"logboek_extra_toevoegingen_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime='text/csv'
    )


#---