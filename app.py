import streamlit as st
import pandas as pd
import os
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from geopy.distance import geodesic
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium

# 📁 Google Sheets via secrets
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

# 📁 Dataset pad
DATA_PATH = "huidige_dataset.csv"

# 📥 Laad bestaande data
if 'df1_filtered' not in st.session_state and os.path.exists(DATA_PATH):
    st.session_state['df1_filtered'] = pd.read_csv(DATA_PATH)

# 🎨 Pagina setup
st.set_page_config(page_title="Afvalcontainerbeheer", layout="wide")
st.title("♻️ Afvalcontainerbeheer Dashboard")

# 🔀 Navigatie
tabs = st.radio("📌 Kies een tabblad", ["Dashboard", "Kaart"], horizontal=True)

# -------------------------- DASHBOARD --------------------------
if tabs == "Dashboard":

    rol = st.selectbox("👤 Kies je rol", ["Gebruiker", "Admin"])

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
            st.success("✅ Gegevens succesvol verwerkt en gedeeld.")

    elif rol == "Gebruiker" and 'df1_filtered' in st.session_state:
        st.header("📋 Containeroverzicht")

        df = st.session_state['df1_filtered']

        # Filters als knoppen/switch
        st.subheader("🎛️ Filters")

        content_types = sorted(df["Content type"].unique())
        active_type = st.session_state.get("active_content_type", content_types[0])

        cols = st.columns(len(content_types))
        for i, ctype in enumerate(content_types):
            if cols[i].button(ctype):
                st.session_state["active_content_type"] = ctype
                st.rerun()

        selected_type = st.session_state.get("active_content_type", content_types[0])
        df_display = df[df["Content type"] == selected_type]

        op_route_ja = st.toggle("Toon alleen containers **op route**", value=True)
        df_display = df_display[df_display["OpRoute"] == ("Ja" if op_route_ja else "Nee")]

        df_display = df_display.sort_values(by="Fill level (%)", ascending=False)

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

        bewerkbare_rijen = df_display[df_display["Extra meegegeven"] == False]

        st.subheader("✏️ Bewerkbare rijen (AgGrid)")
        gb = GridOptionsBuilder.from_dataframe(bewerkbare_rijen[zichtbaar])
        gb.configure_default_column(editable=False, sortable=True, filter=True)
        gb.configure_column("Extra meegegeven", editable=True)
        grid_options = gb.build()

        grid_response = AgGrid(
            bewerkbare_rijen[zichtbaar],
            gridOptions=grid_options,
            update_mode=GridUpdateMode.VALUE_CHANGED,
            height=500,
            allow_unsafe_jscode=True,
            reload_data=False
        )

        updated_df = grid_response["data"]

        if st.button("✅ Wijzigingen toepassen en loggen"):
            wijzigingen_geteld = 0

            for _, row in updated_df.iterrows():
                mask = (st.session_state['df1_filtered']['Container name'] == row["Container name"])
                oude_waarde = st.session_state['df1_filtered'].loc[mask, "Extra meegegeven"].values[0]
                nieuwe_waarde = row["Extra meegegeven"]

                if nieuwe_waarde != oude_waarde:
                    st.session_state['df1_filtered'].loc[mask, "Extra meegegeven"] = nieuwe_waarde

                    log_entry = {
                        "Container name": row["Container name"],
                        "Address": row["Address"],
                        "City": row["City"],
                        "Location code": row["Location code"],
                        "Content type": row["Content type"],
                        "Fill level (%)": row["Fill level (%)"],
                        "Datum": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }

                    voeg_toe_aan_logboek(log_entry)
                    wijzigingen_geteld += 1

            st.session_state['df1_filtered'].to_csv(DATA_PATH, index=False)
            st.success(f"✔️ {wijzigingen_geteld} wijziging(en) opgeslagen en gelogd.")
            st.rerun()

        st.subheader("🔒 Reeds gelogde rijen")
        reeds_gelogd = df_display[df_display["Extra meegegeven"] == True]
        st.dataframe(reeds_gelogd[zichtbaar], use_container_width=True)

# -------------------------- KAART --------------------------
elif tabs == "Kaart" and 'df1_filtered' in st.session_state:
    st.header("🗺️ Heatmap per locatie en content type")

    df_map = st.session_state['df1_filtered'].copy()
    df_map[["lat", "lon"]] = df_map["Container location"].str.split(",", expand=True).astype(float)

    st.subheader("1️⃣ Kies een content type (fractie)")
    content_types = sorted(df_map["Content type"].unique())
    col_ctypes = st.columns(len(content_types))
    selected_type = st.session_state.get("kaart_type", content_types[0])

    for i, ct in enumerate(content_types):
        if col_ctypes[i].button(ct):
            st.session_state["kaart_type"] = ct
            st.rerun()

    df_filtered = df_map[df_map["Content type"] == selected_type]

    st.subheader("2️⃣ Kies een container")
    container_names = df_filtered["Container name"].unique()
    selected_container = st.selectbox("Selecteer container", container_names)

    center_row = df_filtered[df_filtered["Container name"] == selected_container].iloc[0]
    center_coord = (center_row["lat"], center_row["lon"])

    def binnen_250m(row):
        from geopy.distance import geodesic
        return geodesic((row["lat"], row["lon"]), center_coord).meters <= 250

    df_filtered["binnen_250m"] = df_filtered.apply(binnen_250m, axis=1)
    df_nabij = df_filtered[df_filtered["binnen_250m"] == True]

    st.subheader("3️⃣ Kaartweergave")
    import folium
    from folium.plugins import HeatMap
    from streamlit_folium import st_folium

    m = folium.Map(location=center_coord, zoom_start=16)

    # 🔁 Gemiddelde vulgraad per locatie (Container location + fractie)
    df_gemiddeld = (
        df_nabij.groupby(["Container location", "Content type"])
        ["Fill level (%)"].mean()
        .reset_index()
    )
    df_gemiddeld[["lat", "lon"]] = df_gemiddeld["Container location"].str.split(",", expand=True).astype(float)

    heat_data = [
        [row["lat"], row["lon"], row["Fill level (%)"]] for _, row in df_gemiddeld.iterrows()
    ]
    HeatMap(heat_data, radius=15, min_opacity=0.4, max_val=100).add_to(m)

    for _, row in df_nabij.iterrows():
        tooltip = (
            f"📦 {row['Container name']}<br>"
            f"📍 Locatie: {row['Location code']}<br>"
            f"📊 Vulgraad: {row['Fill level (%)']}%"
        )
        folium.Marker(
            location=(row["lat"], row["lon"]),
            icon=folium.Icon(color="blue", icon="info-sign"),
            tooltip=tooltip
        ).add_to(m)

    # 🔴 Marker voor geselecteerde container
    folium.Marker(
        location=center_coord,
        popup=f"Geselecteerd: {selected_container}",
        icon=folium.Icon(color="red", icon="star")
    ).add_to(m)

    # 📘 Legenda
    legend_html = """
    <div style="
        position: fixed;
        bottom: 50px;
        left: 50px;
        width: 200px;
        height: 130px;
        background-color: white;
        border:2px solid grey;
        z-index:9999;
        font-size:14px;
        padding: 10px;
    ">
    <b>Legenda vulgraad (%)</b><br>
    <i style="background: #00f; width: 12px; height: 12px; display: inline-block"></i> Laag (0–30%)<br>
    <i style="background: #0ff; width: 12px; height: 12px; display: inline-block"></i> Matig (30–60%)<br>
    <i style="background: #ff0; width: 12px; height: 12px; display: inline-block"></i> Hoog (60–90%)<br>
    <i style="background: #f00; width: 12px; height: 12px; display: inline-block"></i> Kritiek (90–100%)<br>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    st_folium(m, width=1000, height=600)
