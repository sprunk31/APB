# Verbeterde versie volgt hieronder. Dit script bevat:
# - Een strakke lay-out
# - Nettere filtercomponenten
# - Responsive dataweergave
# - Gestroomlijnde navigatie en legenda

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

# --- Configuratie ---
st.set_page_config(page_title="Afvalcontainerbeheer", layout="wide")
st.title("♻️ Afvalcontainerbeheer Dashboard")

# --- Google Sheets authenticatie ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDENTIALS = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPE)
SHEET_ID = "11svyug6tDpb8YfaI99RyALevzjSSLn1UshSwVQYlcNw"
SHEET_NAME = "Logboek Afvalcontainers"
DATA_PATH = "huidige_dataset.csv"

# --- Logboek toevoegen ---
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

# --- Data laden ---
if 'df1_filtered' not in st.session_state and os.path.exists(DATA_PATH):
    st.session_state['df1_filtered'] = pd.read_csv(DATA_PATH)

# --- Navigatie ---
tabs = st.radio("", ["📊 Dashboard", "🗺️ Kaartweergave"], horizontal=True)

# ---------------------- DASHBOARD ----------------------
if tabs == "📊 Dashboard":
    with st.container():
        with st.columns([2, 8])[0]:
            rol = st.selectbox("👤 Kies je rol:", ["Gebruiker", "Upload"], label_visibility="collapsed")

        if rol == "Upload":
            st.subheader("📤 Upload Excel-bestanden")
            file1 = st.file_uploader("Bestand van Abel", type=["xlsx"])
            file2 = st.file_uploader("Bestand van Pieterbas", type=["xlsx"])

            if file1 and file2:
                df1 = pd.read_excel(file1)
                df2 = pd.read_excel(file2)

                df1_filtered = df1[(df1['Operational state'] == 'In use') &
                                   (df1['Status'] == 'In use') &
                                   (df1['On hold'] == 'No')].copy()

                df1_filtered["Content type"] = df1_filtered["Content type"].apply(
                    lambda x: "Glas" if "glass" in str(x).lower() else x)

                df1_filtered['CombinatieTelling'] = df1_filtered.groupby(['Location code', 'Content type'])['Content type'].transform('count')
                df1_filtered['GemiddeldeVulgraad'] = df1_filtered.groupby(['Location code', 'Content type'])['Fill level (%)'].transform('mean')
                df1_filtered['OpRoute'] = df1_filtered['Container name'].isin(df2['Omschrijving'].values).map({True: 'Ja', False: 'Nee'})
                df1_filtered['Extra meegegeven'] = False

                st.session_state['df1_filtered'] = df1_filtered
                df1_filtered.to_csv(DATA_PATH, index=False)
                st.success("✅ Gegevens succesvol verwerkt en gedeeld.")

        elif rol == "Gebruiker" and 'df1_filtered' in st.session_state:
            df = st.session_state['df1_filtered']

            # Filterblok
            st.markdown("### 🔍 Filters")
            filter_col1, filter_col2 = st.columns([2, 8])
            with filter_col1:
                content_types = sorted(df["Content type"].unique())
                selected_type = st.selectbox("Content type:", content_types, index=0, label_visibility="visible")
            with filter_col2:
                op_route_ja = st.toggle("📍 Alleen op route", value=False)

            df_display = df[df["Content type"] == selected_type]
            df_display = df_display[df_display["OpRoute"] == ("Ja" if op_route_ja else "Nee")]
            df_display = df_display.sort_values(by="GemiddeldeVulgraad", ascending=False)

            zichtbaar = ["Container name", "Address", "City", "Location code", "Content type", "Fill level (%)", "CombinatieTelling", "GemiddeldeVulgraad", "OpRoute", "Extra meegegeven"]
            bewerkbare_rijen = df_display[df_display["Extra meegegeven"] == False]

            st.markdown("### ✏️ Bewerkbare rijen")
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
                        voeg_toe_aan_logboek({**row, "Datum": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                        wijzigingen += 1

                st.session_state['df1_filtered'].to_csv(DATA_PATH, index=False)
                st.success(f"✔️ {wijzigingen} wijziging(en) opgeslagen en gelogd.")
                st.rerun()

            st.markdown("### 🔒 Reeds gelogde rijen")
            reeds_gelogd = df_display[df_display["Extra meegegeven"] == True]
            st.dataframe(reeds_gelogd[zichtbaar], use_container_width=True)

# ---------------------- KAART ----------------------
elif tabs == "🗺️ Kaartweergave" and 'df1_filtered' in st.session_state:
    df_map = st.session_state['df1_filtered'].copy()
    df_map[["lat", "lon"]] = df_map["Container location"].str.split(",", expand=True).astype(float)

    st.subheader("1️⃣ Kies content type")
    content_types = sorted(df_map["Content type"].unique())
    col1, col2 = st.columns([1, 1])
    with col1:
        with st.columns([2, 8])[0]:
            selected_type = st.selectbox("Fractie:", content_types, index=0)
    df_filtered = df_map[df_map["Content type"] == selected_type]

    st.subheader("2️⃣ Kies container")
    df_filtered["container_selectie"] = df_filtered["Container name"] + " (" + df_filtered["Fill level (%)"].astype(str) + "%)"
    container_names = df_filtered["container_selectie"].tolist()
    with st.columns([2, 8])[0]:
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
