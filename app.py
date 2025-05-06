import streamlit as st
import pandas as pd
import os
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
import branca
from geopy.distance import geodesic

# 🎨 Custom styling
st.set_page_config(page_title="Afvalcontainerbeheer", layout="wide")
st.markdown("""
<style>
.block-container {
    padding-top: 1rem;
    padding-bottom: 1rem;
}
.stSelectbox > div, .stRadio > div {
    max-width: 250px;
}
</style>
""", unsafe_allow_html=True)

st.title("♻️ Afvalcontainerbeheer Dashboard")

# 📁 Google Sheets setup
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDENTIALS = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPE)
SHEET_ID = "11svyug6tDpb8YfaI99RyALevzjSSLn1UshSwVQYlcNw"
SHEET_NAME = "Logboek Afvalcontainers"
DATA_PATH = "huidige_dataset.csv"

def voeg_toe_aan_logboek(data_dict):
    try:
        client = gspread.authorize(CREDENTIALS)
        sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
        sheet.append_row([
            data_dict["Container name"],
            data_dict["Address"],
            data_dict["City"],
            data_dict["Location code"],
            data_dict["Content type"],
            data_dict["Fill level (%)"],
            data_dict["Datum"]
        ])
    except Exception as e:
        st.error("⚠️ Fout bij loggen naar Google Sheets:")
        st.exception(e)

# 📥 Data laden
if 'df1_filtered' not in st.session_state and os.path.exists(DATA_PATH):
    st.session_state['df1_filtered'] = pd.read_csv(DATA_PATH)

# 🔀 Navigatie
tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "🗺️ Kaartweergave", "📋 Route-status"])

# -------------------- DASHBOARD --------------------
with tab1:
    col_role = st.columns([2, 8])[0]
    with col_role:
        rol = st.selectbox("👤 Kies je rol:", ["Upload", "Gebruiker Delft", "Gebruiker Den Haag"], label_visibility="collapsed")

    if rol == "Upload":
        st.subheader("📤 Upload Excel-bestanden")
        file1 = st.file_uploader("Bestand van Abel", type=["xlsx"])
        file2 = st.file_uploader("Bestand van Pieterbas", type=["xlsx"])

        if file1 and file2:
            df1 = pd.read_excel(file1)
            df2 = pd.read_excel(file2)
            st.session_state['file2'] = df2  # Voeg toe om file2 in session_state op te slaan

            df1_filtered = df1[
                (df1['Operational state'] == 'In use') &
                (df1['Status'] == 'In use') &
                (df1['On hold'] == 'No')
            ].copy()

            df1_filtered["Content type"] = df1_filtered["Content type"].apply(
                lambda x: "Glas" if "glass" in str(x).lower() else x
            )

            df1_filtered['CombinatieTelling'] = df1_filtered.groupby(['Location code', 'Content type'])['Content type'].transform('count')
            df1_filtered['GemiddeldeVulgraad'] = df1_filtered.groupby(['Location code', 'Content type'])['Fill level (%)'].transform('mean')
            df1_filtered['OpRoute'] = df1_filtered['Container name'].isin(df2['Omschrijving'].values).map({True: 'Ja', False: 'Nee'})
            df1_filtered['Extra meegegeven'] = False

            st.session_state['df1_filtered'] = df1_filtered
            df1_filtered.to_csv(DATA_PATH, index=False)
            st.success("✅ Gegevens succesvol verwerkt en gedeeld.")


    elif rol.startswith("Gebruiker") and 'df1_filtered' in st.session_state:

        df = st.session_state['df1_filtered']

        try:
            client = gspread.authorize(CREDENTIALS)
            sheet_totaal = client.open_by_key(SHEET_ID).worksheet("Logboek totaal")
            sheet_containers = client.open_by_key(SHEET_ID).worksheet("Logboek Afvalcontainers")
            vandaag = datetime.now().strftime("%Y-%m-%d")
            datum_met_tijd = vandaag
            aantal_vol = int((df['Fill level (%)'] >= 80).sum())

            # Alle rijen uit Logboek totaal ophalen
            totaal_rows = sheet_totaal.get_all_values()
            totaal_header = totaal_rows[0]
            bestaande_rijen = totaal_rows[1:]

            # Zoek juiste kolomindex voor Delft of Den Haag
            kolom_delft = totaal_header.index("Aantal bakken toegevoegd Delft")
            kolom_denhaag = totaal_header.index("Aantal bakken toegevoegd Den Haag")

            # Zoek rijnummer van vandaag
            rijnummer_vandaag = None
            for idx, rij in enumerate(bestaande_rijen, start=2):  # start=2 vanwege header
                if rij[0][:10] == vandaag:
                    rijnummer_vandaag = idx
                    break

            # Tel aantal gelogde containers in Logboek Afvalcontainers
            container_rows = sheet_containers.get_all_values()
            container_header = container_rows[0]
            datum_index = container_header.index("Datum")
            aantal_gelogde_containers = sum(
                1 for rij in container_rows[1:] if rij[datum_index][:10] == vandaag
            )
            # Stel rijnwaarde op basis van bestaande of nieuwe rij
            if rijnummer_vandaag:
                bestaande_waarden = sheet_totaal.row_values(rijnummer_vandaag)
                while len(bestaande_waarden) < len(totaal_header):
                    bestaande_waarden.append("")  # vul aan tot volledige breedte
                bestaande_waarden[1] = str(aantal_vol)  # kolom B: Aantal volle bakken in Abel
                if "Delft" in rol:
                    bestaande_waarden[kolom_delft] = str(aantal_gelogde_containers)

                elif "Den Haag" in rol:
                    bestaande_waarden[kolom_denhaag] = str(aantal_gelogde_containers)
                sheet_totaal.update(f"A{rijnummer_vandaag}:{chr(65 + len(totaal_header) - 1)}{rijnummer_vandaag}",
                                    [bestaande_waarden])
                st.toast("🔄 Logboek totaal bijgewerkt voor vandaag.")

            else:
                nieuwe_rij = [""] * len(totaal_header)
                nieuwe_rij[0] = datum_met_tijd
                nieuwe_rij[1] = str(aantal_vol)

                if "Delft" in rol:
                    nieuwe_rij[kolom_delft] = str(aantal_gelogde_containers)

                elif "Den Haag" in rol:
                    nieuwe_rij[kolom_denhaag] = str(aantal_gelogde_containers)
                sheet_totaal.append_row(nieuwe_rij)
                st.toast("📅 Dagelijkse log toegevoegd aan 'Logboek totaal'")

        except Exception as e:
            st.error("❌ Fout bij loggen of bijwerken van 'Logboek totaal'")
            st.exception(e)

        # 🎯 KPI's
        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("📦 Containers", len(df))
        kpi2.metric("🔴 >80% gevuld", (df['Fill level (%)'] >= 80).sum())
        kpi3.metric("🚚 Op route", df['OpRoute'].value_counts().get('Ja', 0))

        # 🔍 Filters
        with st.expander("🔎 Filters", expanded=True):
            filter_col1, filter_col2 = st.columns(2)
            with filter_col1:
                content_types = sorted(df["Content type"].unique())
                selected_type = st.selectbox("Content type", content_types)
            with filter_col2:
                op_route_ja = st.toggle("📍 Alleen op route", value=False)

        df_display = df[df["Content type"] == selected_type]
        df_display = df_display[df_display["OpRoute"] == ("Ja" if op_route_ja else "Nee")]
        df_display = df_display.sort_values(by="GemiddeldeVulgraad", ascending=False)

        zichtbaar = ["Container name", "Address", "City", "Location code", "Content type", "Fill level (%)", "CombinatieTelling", "GemiddeldeVulgraad", "OpRoute", "Extra meegegeven"]
        bewerkbare_rijen = df_display[df_display["Extra meegegeven"] == False]

        st.markdown("### ✏️ Bewerkbare containers")
        gb = GridOptionsBuilder.from_dataframe(bewerkbare_rijen[zichtbaar])
        gb.configure_default_column(editable=False, sortable=True, filter=True, resizable=True)
        gb.configure_column("Extra meegegeven", editable=True)

        grid_response = AgGrid(
            bewerkbare_rijen[zichtbaar],
            gridOptions=gb.build(),
            update_mode=GridUpdateMode.VALUE_CHANGED,
            height=500,
            allow_unsafe_jscode=True
        )

        updated_df = grid_response["data"]
        if st.button("✅ Wijzigingen toepassen en loggen"):
            wijzigingen = 0
            for _, row in updated_df.iterrows():
                mask = (st.session_state['df1_filtered']['Container name'] == row["Container name"])
                oude_waarde = st.session_state['df1_filtered'].loc[mask, "Extra meegegeven"].values[0]
                nieuwe_waarde = row["Extra meegegeven"]
                if nieuwe_waarde != oude_waarde:
                    st.session_state['df1_filtered'].loc[mask, "Extra meegegeven"] = nieuwe_waarde
                    voeg_toe_aan_logboek({**row, "Datum": datetime.now().strftime("%Y-%m-%d")})
                    wijzigingen += 1
            st.session_state['df1_filtered'].to_csv(DATA_PATH, index=False)
            st.toast(f"✔️ {wijzigingen} wijziging(en) opgeslagen en gelogd.")
            st.rerun()

        st.markdown("### 🔒 Reeds gelogde containers")
        reeds_gelogd = df_display[df_display["Extra meegegeven"] == True]
        st.dataframe(reeds_gelogd[zichtbaar], use_container_width=True)

# -------------------- KAART --------------------
with tab2:
    if 'df1_filtered' in st.session_state:
        df_map = st.session_state['df1_filtered'].copy()
        df_map[["lat", "lon"]] = df_map["Container location"].str.split(",", expand=True).astype(float)

        st.markdown("### 1️⃣ Kies content type")
        content_types = sorted(df_map["Content type"].unique())
        selected_type = st.selectbox("Fractie:", content_types, index=0)
        df_filtered = df_map[df_map["Content type"] == selected_type]

        st.markdown("### 2️⃣ Kies container")
        df_filtered["container_selectie"] = df_filtered["Container name"] + " (" + df_filtered["Fill level (%)"].astype(str) + "%)"
        container_names = df_filtered["container_selectie"].tolist()
        selected_container_name = st.selectbox("Container (met vulgraad):", container_names)
        selected_container = selected_container_name.split(" (")[0]

        center_row = df_filtered[df_filtered["Container name"] == selected_container].iloc[0]
        center_coord = (center_row["lat"], center_row["lon"])
        df_filtered["binnen_250m"] = df_filtered.apply(lambda r: geodesic((r["lat"], r["lon"]), center_coord).meters <= 250, axis=1)
        df_nabij = df_filtered[df_filtered["binnen_250m"] == True]

        m = folium.Map(location=center_coord, zoom_start=16)
        df_gemiddeld = df_nabij.groupby(["Container location", "Content type"])["Fill level (%)"].mean().reset_index()
        df_gemiddeld[["lat", "lon"]] = df_gemiddeld["Container location"].str.split(",", expand=True).astype(float)

        heat_data = [[row["lat"], row["lon"], row["Fill level (%)"]] for _, row in df_gemiddeld.iterrows()]
        HeatMap(heat_data, radius=15, min_opacity=0.4, max_val=100).add_to(m)

        for _, row in df_nabij.iterrows():
            folium.CircleMarker(
                location=(row["lat"], row["lon"]),
                radius=5,
                color="blue",
                fill=True,
                fill_color="blue",
                fill_opacity=0.8,
                tooltip=folium.Tooltip(
                    f"""
                    📦 <b>{row['Container name']}</b><br>
                    📍 Locatie: {row['Location code']}<br>
                    📊 Vulgraad: {row['Fill level (%)']}%
                    """,
                    sticky=True
                )
            ).add_to(m)

        folium.Marker(
            location=center_coord,
            popup=f"Geselecteerd: {selected_container}",
            icon=folium.Icon(color="red", icon="star")
        ).add_to(m)

        legend = branca.element.MacroElement()
        legend._template = branca.element.Template("""
        {% macro html(this, kwargs) %}
        <div style="position: fixed; bottom: 50px; left: 50px; width: 210px; height: 150px;
            background-color: white; border:2px solid grey; z-index:9999; font-size:14px; padding: 10px;">
            <b>Legenda vulgraad (%)</b><br>
            <div style="margin-top:8px;">
                <span style="background:#0000ff;width:12px;height:12px;display:inline-block;"></span> 0–30%<br>
                <span style="background:#00ffff;width:12px;height:12px;display:inline-block;"></span> 30–60%<br>
                <span style="background:#ffff00;width:12px;height:12px;display:inline-block;"></span> 60–90%<br>
                <span style="background:#ff0000;width:12px;height:12px;display:inline-block;"></span> 90–100%<br>
            </div>
        </div>
        {% endmacro %}
        """)
        m.get_root().add_child(legend)
        st_folium(m, width=1000, height=600)

# -------------------- ROUTE STATUS --------------------
with tab3:
    if 'file2' not in st.session_state:
        st.warning("❗ Upload eerst 'Bestand van Pieterbas' via tabblad Dashboard.")
    else:
        df_routes = st.session_state['file2']
        unieke_routes = sorted(df_routes["Route Omschriving"].dropna().unique())

        st.markdown("### 🛣️ Route status doorgeven")
        route = st.selectbox("Kies een route", unieke_routes)

        status_opties = ["Actueel", "Gedeeltelijk niet gereden door:", "Volledig niet gereden door:"]
        gekozen_status = st.selectbox("Status", status_opties)

        reden = ""
        if "niet gereden" in gekozen_status:
            reden = st.text_input("📌 Geef de reden op")

        if st.button("✅ Bevestig status"):
            try:
                client = gspread.authorize(CREDENTIALS)
                sheet = client.open_by_key(SHEET_ID).worksheet("Logboek route")
                records = sheet.get_all_records()

                if gekozen_status == "Actueel":
                    # Zoek het laatst gelogde record van deze route met afwijking
                    for i in reversed(range(len(records))):
                        record = records[i]
                        if record["Route"] == route and record["Status"] in [
                            "Gedeeltelijk niet gereden door", "Volledig niet gereden door"
                        ]:
                            sheet.delete_rows(i + 2)  # +2 omdat header op rij 1 staat
                            st.success(f"✅ Vorige afwijking van '{route}' is verwijderd uit het logboek.")
                            break
                    else:
                        st.info("ℹ️ Geen afwijking gevonden voor deze route om te verwijderen.")
                else:
                    if reden.strip() == "":
                        st.warning("⚠️ Vul een reden in voordat je logt.")
                    else:
                        sheet.append_row([
                            route,
                            gekozen_status.replace(":", ""),
                            reden,
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        ])
                        st.success("📝 Nieuwe afwijking succesvol gelogd.")
            except Exception as e:
                st.error("❌ Fout bij communiceren met Google Sheets.")
                st.exception(e)
##