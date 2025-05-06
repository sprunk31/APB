import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
import branca
from geopy.distance import geodesic
from streamlit_autorefresh import st_autorefresh

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
st_autorefresh(interval=10_000, key="datarefresh")

# 1) Google Sheets setup
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDENTIALS = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPE)
SHEET_ID = "11svyug6tDpb8YfaI99RyALevzjSSLn1UshSwVQYlcNw"

# Namen van de tabbladen
CACHE_SHEET      = "Dagelijkse cache"
TOTAL_SHEET      = "Logboek totaal"
CONTAINERS_SHEET = "Logboek Afvalcontainers"
ROUTE_SHEET      = "Logboek route"

# 2) Worksheet helper
def get_sheet(name):
    client = gspread.authorize(CREDENTIALS)
    return client.open_by_key(SHEET_ID).worksheet(name)

# 3) Laad de cache uit Google Sheets (en cache in Streamlit)
@st.cache_data(ttl=300)
def load_cache():
    try:
        ws = get_sheet(CACHE_SHEET)
        records = ws.get_all_records()
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        vandaag = datetime.now().strftime("%Y-%m-%d")
        # Alleen behouden als de cache van vandaag is
        if str(df.loc[0, "Datum"])[:10] != vandaag:
            return pd.DataFrame()
        return df.drop(columns=["Datum"])
    except Exception:
        return pd.DataFrame()

# 4) Schrijf de cache terug naar Google Sheets
def write_cache(df: pd.DataFrame):
    ws = get_sheet(CACHE_SHEET)
    ws.clear()
    vandaag = datetime.now().strftime("%Y-%m-%d")

    # Zet alles om naar string, zodat JSON veilig is
    df_str = df.astype(str)
    header = ["Datum"] + df_str.columns.tolist()

    # Bouw de rijen: voor iedere DataFrame-rij een lijst met strings
    rows = [[vandaag] + row for row in df_str.values.tolist()]

    # append_rows met alleen zuivere Python‐strings
    ws.append_rows([header] + rows, value_input_option="RAW")

    # Cache clear
    st.cache_data.clear()


# 5) Log het dagtotaal éénmalig in 'Logboek totaal'
def log_daily_totals(df: pd.DataFrame):
    ws = get_sheet(TOTAL_SHEET)
    today = datetime.now().strftime("%Y-%m-%d")
    rows = ws.get_all_records()
    if not any(r["Datum"][:10] == today for r in rows):
        aantal_vol = int((df['Fill level (%)'] >= 80).sum())
        ws.append_row([today, aantal_vol, 0])

# 6) Laad of initialiseert de cache
df1_filtered = load_cache()

# 7) Streamlit tabs
tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "🗺️ Kaartweergave", "📋 Route-status"])

with tab1:
    col = st.columns([2, 8])[0]
    with col:
        rol = st.selectbox("👤 Kies je rol:", ["Gebruiker", "Upload"], label_visibility="collapsed")

    if rol == "Upload":
        st.subheader("📤 Upload Excel-bestanden")
        file1 = st.file_uploader("Bestand van Abel", type=["xlsx"])
        file2 = st.file_uploader("Bestand van Pieterbas", type=["xlsx"])
        if file1 and file2:
            df_raw  = pd.read_excel(file1)
            df2     = pd.read_excel(file2)
            st.session_state['file2'] = df2

            # Filter en enrich
            df1_filtered = df_raw.query(
                "`Operational state` == 'In use' and Status == 'In use' and `On hold` == 'No'"
            ).copy()
            df1_filtered["Content type"] = df1_filtered["Content type"]\
                .apply(lambda x: "Glas" if "glass" in str(x).lower() else x)
            df1_filtered['CombinatieTelling'] = df1_filtered.groupby(
                ['Location code','Content type']
            )['Content type'].transform('count')
            df1_filtered['GemiddeldeVulgraad'] = df1_filtered.groupby(
                ['Location code','Content type']
            )['Fill level (%)'].transform('mean')
            df1_filtered['OpRoute'] = df1_filtered['Container name']\
                .isin(df2['Omschrijving']).map({True:'Ja', False:'Nee'})
            df1_filtered['Extra meegegeven'] = False

            # Schrijf gecachede data en log dagelijks totaal
            write_cache(df1_filtered)
            log_daily_totals(df1_filtered)
            st.success("✅ Cache bijgewerkt en dagtotaal gelogd.")

    elif rol == "Gebruiker" and not df1_filtered.empty:
        df = df1_filtered

        # KPI's
        k1, k2, k3 = st.columns(3)
        k1.metric("📦 Containers", len(df))
        k2.metric("🔴 >80% vulgraad", int((df['Fill level (%)'] >= 80).sum()))
        k3.metric("🚚 Op route", df['OpRoute'].eq('Ja').sum())

        # Filters
        with st.expander("🔎 Filters", expanded=True):
            c1, c2 = st.columns(2)
            with c1:
                types    = sorted(df["Content type"].unique())
                sel_type = st.selectbox("Content type", types)
            with c2:
                sel_route = st.checkbox("📍 Alleen op route", value=False)

        disp = df[df["Content type"] == sel_type]
        if sel_route:
            disp = disp[disp["OpRoute"] == 'Ja']
        disp = disp.sort_values("GemiddeldeVulgraad", ascending=False)

        # Alleen de kolommen die je wilt tonen
        cols = [
            "Container name", "Address", "City", "Location code", "Content type",
            "Fill level (%)", "CombinatieTelling", "GemiddeldeVulgraad", "OpRoute", "Extra meegegeven"
        ]

        # Maak een lege DataFrame voor het geval de kolom ontbreekt of er geen True‐waarden zijn
        if "Extra meegegeven" in disp.columns:
            done = disp.loc[disp["Extra meegegeven"] == True, cols]
        else:
            done = pd.DataFrame(columns=cols)

        st.dataframe(done, use_container_width=True)

        editable = disp[disp["Extra meegegeven"] == False]

        st.markdown("### ✏️ Bewerkbare containers")
        gb = GridOptionsBuilder.from_dataframe(editable[cols])
        gb.configure_default_column(editable=False, sortable=True, filter=True, resizable=True)
        gb.configure_column("Extra meegegeven", editable=True)
        grid = AgGrid(
            editable[cols],
            gridOptions=gb.build(),
            update_mode=GridUpdateMode.VALUE_CHANGED,
            height=400,
            allow_unsafe_jscode=True
        )
        updates = grid["data"]

        if st.button("✅ Wijzigingen toepassen en loggen"):
            # Voorbereiding update Logboek totaal
            ws_tot   = get_sheet(TOTAL_SHEET)
            tot_rows = ws_tot.get_all_records()
            today    = datetime.now().strftime("%Y-%m-%d")
            idx      = next((i for i,r in enumerate(tot_rows) if r["Datum"][:10] == today), None)
            extra    = int(tot_rows[idx]["Aantal extra bakken"]) if idx is not None else 0

            wijzigingen = 0
            ws_cache = get_sheet(CACHE_SHEET)

            for r in updates:
                mask = df["Container name"] == r["Container name"]
                old  = df.loc[mask, "Extra meegegeven"].iat[0]
                new  = r["Extra meegegeven"]
                if new and not old:
                    extra += 1
                    if idx is not None:
                        ws_tot.update_cell(idx+2, 3, extra)
                    # Update de cache-sheet
                    row_idx = df.index[mask][0] + 2  # header + 1-based
                    col_idx = df.columns.get_loc("Extra meegegeven") + 1
                    ws_cache.update_cell(row_idx, col_idx, True)
                    wijzigingen += 1

            # Cache clear en herlaad
            st.cache_data.clear()
            df1_filtered = load_cache()
            st.toast(f"✔️ {wijzigingen} wijziging(en) opgeslagen en gelogd.")
            st.experimental_rerun()

        st.markdown("### 🔒 Reeds gelogde containers")
        done = disp[disp["Extra meegegeven"]]
        st.dataframe(done[cols], use_container_width=True)

        # Update OpRoute → “Extra meegegeven” voor containers gelogd vandaag
        ws_cont = get_sheet(CONTAINERS_SHEET)
        recs    = ws_cont.get_all_records()
        today   = datetime.now().strftime("%Y-%m-%d")
        done_names = {r["Container name"] for r in recs if r["Datum"][:10] == today}
        df1_filtered.loc[
            df1_filtered["Container name"].isin(done_names),
            "OpRoute"
        ] = "Extra meegegeven"
        write_cache(df1_filtered)

with tab2:
    if not df1_filtered.empty:
        df_map = df1_filtered.copy()
        df_map[["lat", "lon"]] = df_map["Container location"].str.split(",", expand=True).astype(float)

        st.markdown("### 1️⃣ Kies content type")
        types = sorted(df_map["Content type"].unique())
        sel   = st.selectbox("Fractie:", types)
        filt  = df_map[df_map["Content type"] == sel]
        filt["select"] = filt["Container name"] + " (" + filt["Fill level (%)"].astype(str) + "%)"
        sel_name = st.selectbox("Container (met vulgraad):", filt["select"])
        cname    = sel_name.split(" (")[0]
        center   = tuple(filt.loc[filt["Container name"] == cname, ["lat", "lon"]].iloc[0])
        filt["nabij"] = filt.apply(lambda r: geodesic((r.lat, r.lon), center).meters <= 250, axis=1)
        nearby       = filt[filt["nabij"]]

        m = folium.Map(location=center, zoom_start=16)
        avg = nearby.groupby(["Container location", "Content type"])["Fill level (%)"].mean().reset_index()
        avg[["lat", "lon"]] = avg["Container location"].str.split(",", expand=True).astype(float)
        HeatMap(
            [[r.lat, r.lon, r["Fill level (%)"]] for _, r in avg.iterrows()],
            radius=15, min_opacity=0.4
        ).add_to(m)

        for _, r in nearby.iterrows():
            folium.CircleMarker(
                location=(r.lat, r.lon),
                radius=5,
                fill=True,
                fill_opacity=0.8,
                tooltip=(
                    f"📦 <b>{r['Container name']}</b><br>"
                    f"📍 {r['Location code']}<br>"
                    f"📊 {r['Fill level (%)']}%"
                )
            ).add_to(m)

        folium.Marker(
            location=center,
            popup=f"Geselecteerd: {cname}",
            icon=folium.Icon(color="red", icon="star")
        ).add_to(m)

        # Legenda
        legend = branca.element.MacroElement()
        legend._template = branca.element.Template("""
        {% macro html(this,kwargs) %}
        <div style="position:fixed;bottom:50px;left:50px;
                    width:210px;height:150px;background:white;
                    border:2px solid grey;z-index:9999;font-size:14px;padding:10px;">
          <b>Legenda vulgraad (%)</b><br>
          <span style="background:#0000ff;width:12px;height:12px;display:inline-block;"></span> 0–30%<br>
          <span style="background:#00ffff;width:12px;height:12px;display:inline-block;"></span> 30–60%<br>
          <span style="background:#ffff00;width:12px;height:12px;display:inline-block;"></span> 60–90%<br>
          <span style="background:#ff0000;width:12px;height:12px;display:inline-block;"></span> 90–100%<br>
        </div>
        {% endmacro %}
        """)
        m.get_root().add_child(legend)

        st_folium(m, width=1000, height=600)

with tab3:
    st.header("📋 Status per route")
    if 'file2' not in st.session_state:
        st.warning("❗ Upload eerst 'Bestand van Pieterbas'")
    else:
        dfr = st.session_state['file2']
        routes = sorted(dfr["Route Omschrijving"].dropna().unique())
        sel_route = st.selectbox("1️⃣ Kies een route", routes)
        opts = ["Actueel", "Gedeeltelijk niet gereden door:", "Volledig niet gereden door:"]
        stat = st.selectbox("2️⃣ Status", opts)
        reason = st.text_input("3️⃣ Reden", "") if "niet gereden" in stat else ""
        if st.button("✅ Bevestig status"):
            try:
                wsr = get_sheet(ROUTE_SHEET)
                recs = wsr.get_all_records()
                today = datetime.now().strftime("%Y-%m-%d")
                if stat == "Actueel":
                    # verwijder afwijking van vandaag
                    for i, rc in enumerate(recs[::-1]):
                        if (rc["Route"] == sel_route
                            and rc["Status"] != "Actueel"
                            and rc["Datum"][:10] == today):
                            wsr.delete_rows(len(recs) - i + 1)
                            st.success("🗑️ Verwijderd")
                            break
                else:
                    if not reason.strip():
                        st.warning("⚠️ Geef reden op")
                    else:
                        wsr.append_row([
                            sel_route,
                            stat.replace(":", ""),
                            reason,
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        ])
                        st.success("📝 Gelogd")
            except Exception as e:
                st.error("❌ Fout met Google Sheets")
                st.exception(e)
