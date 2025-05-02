import streamlit as st
import pandas as pd
from datetime import datetime
import os

st.set_page_config(page_title="Afvalcontainerbeheer", layout="wide")
st.title("♻️ Afvalcontainerbeheer Dashboard")

# 🔁 Laad bestaand logboek als het al bestaat
LOG_PATH = "logboek_persistent.csv"
if os.path.exists(LOG_PATH):
    st.session_state['logboek'] = pd.read_csv(LOG_PATH).to_dict(orient="records")
else:
    st.session_state['logboek'] = []

# 1. Gebruikersrol
rol = st.selectbox("👤 Kies je rol", ["Gebruiker", "Admin"])

# 2. Admin uploadt bestanden
if rol == "Admin":
    st.header("📤 Upload Excel-bestanden (alleen voor Admin)")

    file1 = st.file_uploader("Selecteer bestand van Abel", type=["xlsx"])
    file2 = st.file_uploader("Selecteer bestand van Pieterbas", type=["xlsx"])

    if file1 and file2:
        df1 = pd.read_excel(file1)
        df2 = pd.read_excel(file2)

        # Filter regels
        df1_filtered = df1[
            (df1['Operational state'] == 'In use') &
            (df1['Status'] == 'In use') &
            (df1['On hold'] == 'No')
        ].copy()

        # Toevoegen van kolommen
        df1_filtered['CombinatieTelling'] = df1_filtered.groupby(['Location code', 'Content type'])['Content type'].transform('count')
        df1_filtered['GemiddeldeVulgraad'] = df1_filtered.groupby(['Location code', 'Content type'])['Fill level (%)'].transform('mean')
        df1_filtered['KomtVoorInDf2'] = df1_filtered['Container name'].isin(df2['Omschrijving'].values).map({True: 'Ja', False: 'Nee'})

        # Zorg dat Oprout kolom aanwezig is
        if 'Oprout' not in df1_filtered.columns:
            df1_filtered['Oprout'] = False

        # Opslaan in session_state
        st.session_state['df1_filtered'] = df1_filtered
        st.success("✅ Gegevens verwerkt en opgeslagen voor gebruikers.")

# 3. Voor gebruikers: data inzien en aanpassen
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

    # Rijen met Oprout == False
    df_false = df_display[df_display['Oprout'] == False]

    st.subheader("🛠️ Oprout aanpassen voor geselecteerde rijen")
    selected = st.multiselect("Selecteer rijen (index) om als 'Extra toegevoegd' te markeren", df_false.index.tolist())

    if selected:
        for i in selected:
            df_display.at[i, 'Oprout'] = "Extra toegevoegd"
            st.session_state['df1_filtered'].at[i, 'Oprout'] = "Extra toegevoegd"

            log_entry = {
                'Location code': df_display.at[i, 'Location code'],
                'Content type': df_display.at[i, 'Content type'],
                'Fill level (%)': df_display.at[i, 'Fill level (%)'],
                'Datum': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            st.session_state['logboek'].append(log_entry)

        # ⏺️ Schrijf log direct weg naar CSV
        pd.DataFrame(st.session_state['logboek']).to_csv(LOG_PATH, index=False)
        st.success(f"✅ {len(selected)} rijen gemarkeerd en gelogd.")

    st.subheader("📄 Actuele gegevens")
    st.dataframe(df_display, use_container_width=True)

# 4. Logboek downloaden
if st.session_state['logboek']:
    st.header("📝 Logboek Extra Toevoegingen (permanent opgeslagen)")
    log_df = pd.DataFrame(st.session_state['logboek'])

    st.dataframe(log_df, use_container_width=True)

    # Downloadknop
    csv = log_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download logboek als CSV",
        data=csv,
        file_name=f"logboek_extra_toevoegingen_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime='text/csv'
    )
#---