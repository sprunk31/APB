import streamlit as st
import pandas as pd
from datetime import datetime
import os

st.set_page_config(page_title="Afvalcontainerbeheer", layout="wide")
st.title("♻️ Afvalcontainerbeheer Dashboard")

# 🔁 Logboekbestand
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
        df1_filtered['OpRoute'] = df1_filtered['Container name'].isin(df2['Omschrijving'].values).map({True: 'Ja', False: 'Nee'})

        # Hernoem en initialiseer Extra meegegeven
        df1_filtered['Extra meegegeven'] = False

        st.session_state['df1_filtered'] = df1_filtered
        st.success("✅ Gegevens verwerkt en opgeslagen voor gebruikers.")

# 3. Voor gebruikers: data bekijken en bewerken
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

    st.subheader("📄 Actuele gegevens")

    # Kolommen uitsluiten uit weergave
    kolommen_uitgesloten = ['Device Location', 'External group ID']
    kolommen_weergeven = [col for col in df_display.columns if col not in kolommen_uitgesloten]

    # Toon tabel
    st.dataframe(df_display[kolommen_weergeven], use_container_width=True)

    st.subheader("✅ Extra meegegeven aanpassen (checkbox)")

    for index, row in df_display.iterrows():
        nieuwe_waarde = st.checkbox(
            f"{row['Location code']} - {row['Content type']} - {row['Fill level (%)']}%",
            value=row['Extra meegegeven'],
            key=f"checkbox_{index}"
        )

        if nieuwe_waarde != row['Extra meegegeven']:
            st.session_state['df1_filtered'].at[index, 'Extra meegegeven'] = nieuwe_waarde

            log_entry = {
                'Location code': row['Location code'],
                'Content type': row['Content type'],
                'Fill level (%)': row['Fill level (%)'],
                'Datum': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            st.session_state['logboek'].append(log_entry)
            pd.DataFrame(st.session_state['logboek']).to_csv(LOG_PATH, index=False)
            st.success(f"✔️ Wijziging opgeslagen en gelogd: {log_entry['Location code']}")

# 4. Logboek downloaden
if st.session_state['logboek']:
    st.header("📝 Logboek Extra Toevoegingen (permanent opgeslagen)")
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