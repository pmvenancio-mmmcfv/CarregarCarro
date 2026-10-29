import streamlit as st
import requests
from datetime import datetime, timezone, timedelta

st.set_page_config(
    page_title="Ohmigo Android App",
    page_icon="⚡",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .block-container { padding-top: 1rem; padding-bottom: 2rem; max-width: 480px; }
    .winner-card {
        background: linear-gradient(135deg, #064e3b 0%, #022c22 100%);
        border: 2px solid #10b981; border-radius: 16px; padding: 16px; margin-bottom: 12px;
    }
    .normal-card {
        background: #1e293b; border: 1px solid #334155;
        border-radius: 14px; padding: 14px; margin-bottom: 10px;
    }
    .price-big { font-size: 1.65rem; font-weight: 800; color: #34d399; line-height: 1.1; }
    .price-norm { font-size: 1.35rem; font-weight: 700; color: #f8fafc; line-height: 1.1; }
    .sub-text { font-size: 0.78rem; color: #94a3b8; }
    .badge-win {
        background: #10b981; color: #022c22; font-weight: 800;
        font-size: 0.7rem; padding: 2px 8px; border-radius: 6px; text-transform: uppercase;
    }
</style>
""", unsafe_allow_html=True)

CEME_API_BASE = "https://ceme.ocarroeletrico.com"
BATTERY_CAPACITY_KWH = 19.7  # Bateria útil (Caddy eHybrid)
LOSS_FACTOR = 1.05
IVA = 1.23

OPC_PROFILES = {
    "⚡ Atlante (AC <= 22 kW - Ex: Lumiar / Lisboa)": {"kwh": 0.146, "min": 0.000, "act": 0.00, "power": 11.0, "direct_vat": 0.39},
    "⚡ Atlante (DC Rápido 40-50 kW)": {"kwh": 0.235, "min": 0.000, "act": 0.00, "power": 38.0, "direct_vat": 0.44},
    "🟢 EDP Comercial OPC (AC Rua 22 kW)": {"kwh": 0.129, "min": 0.000, "act": 0.00, "power": 11.0, "direct_vat": 0.42},
    "🟠 Galp / Mobiletric (AC 22 kW)": {"kwh": 0.115, "min": 0.012, "act": 0.00, "power": 11.0, "direct_vat": 0.43},
    "🔵 KLC / Power Dot (Supermercados AC 22 kW)": {"kwh": 0.135, "min": 0.010, "act": 0.00, "power": 11.0, "direct_vat": 0.45},
    "🛒 Continente Plug&Charge (AC 11 kW)": {"kwh": 0.000, "min": 0.072, "act": 0.00, "power": 11.0, "direct_vat": 0.39},
}

@st.cache_data(ttl=3600)
def get_oce_session_token():
    try:
        r = requests.post(f"{CEME_API_BASE}/v1/session", timeout=6)
        if r.status_code == 200:
            data = r.json()
            return data.get("token") or data.get("data", {}).get("token")
    except Exception:
        pass
    return None

def build_15min_slices(total_kwh: float, duration_min: int):
    steps = max(1, int((duration_min + 14) // 15))
    kwh_slice = round(total_kwh / steps, 4)
    now = datetime.now(timezone.utc)
    aligned = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    slices = []
    for i in range(steps):
        t = aligned + timedelta(minutes=15 * i)
        val = round(total_kwh - kwh_slice * (steps - 1), 4) if i == steps - 1 else kwh_slice
        slices.append({"at": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "kwh": max(0.01, val)})
    return slices

def fetch_ceme_simulation(kwh: float, duration_min: int):
    token = get_oce_session_token()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    payload = {
        "region": "CONT",
        "useSpot": True,
        "profile": build_15min_slices(kwh, duration_min),
        "detail": False
    }
    try:
        r = requests.post(f"{CEME_API_BASE}/v1/simulate", json=payload, headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json(), True
    except Exception:
        pass
    return None, False

st.markdown("### ⚡ Ohmigo & CEME Decider")
st.caption("Escolhe o posto, ajusta a bateria e vê qual o cartão mais barato.")

selected_label = st.selectbox("📍 1. Onde vais carregar?", list(OPC_PROFILES.keys()))
profile_opc = OPC_PROFILES[selected_label]

st.markdown("##### 🔋 2. Estado da Bateria")
soc_range = st.slider("Percentagem Inicial ➔ Alvo (%)", 0, 100, (15, 100), step=5)
soc_init, soc_target = soc_range
delta_soc = max(5, soc_target - soc_init) / 100.0

col1, col2 = st.columns(2)
with col1:
    power_kw = st.selectbox("Potência no Carro", [11.0, 7.4, 3.7, 38.0], index=0, format_func=lambda x: f"{x} kW {'DC' if x>22 else 'AC'}")
with col2:
    kwh_needed = round(BATTERY_CAPACITY_KWH * delta_soc * LOSS_FACTOR, 1)
    duration_min = int(round((kwh_needed / power_kw) * 60))
    st.metric("Energia / Tempo", f"{kwh_needed} kWh", f"~{duration_min} min")

with st.expander("🔧 Ver / Ajustar Tarifas do Posto (OPC s/ IVA)"):
    c1, c2, c3 = st.columns(3)
    opc_kwh = c1.number_input("OPC €/kWh", value=float(profile_opc["kwh"]), step=0.01, format="%.3f")
    opc_min = c2.number_input("OPC €/min", value=float(profile_opc["min"]), step=0.005, format="%.3f")
    opc_act = c3.number_input("Ativação €", value=float(profile_opc["act"]), step=0.05, format="%.2f")
    direct_vat = st.number_input("Preço App Direta Ad-Hoc (c/ IVA €/kWh)", value=float(profile_opc["direct_vat"]), step=0.01)

opc_total_vat = ((kwh_needed * opc_kwh) + (duration_min * opc_min) + opc_act) * IVA

sim_data, is_live_api = fetch_ceme_simulation(kwh_needed, duration_min)

results = []
if is_live_api and sim_data and "data" in sim_data:
    omie_spot = sim_data.get("omieRef", 0.0)
    st.success(f"🟢 OMIE Spot Quarto-Hora: **{omie_spot:.3f} €/kWh**")
    for item in sim_data["data"][:10]:
        ceme_vat = float(item.get("totalEur") or item.get("parts", {}).get("totalEur") or 0.0)
        total = ceme_vat + opc_total_vat
        results.append({
            "name": f"{item.get('cemeName', '')} — {item.get('name', '')}".strip(" —"),
            "total": total,
            "unit": total / kwh_needed,
            "detail": f"CEME+TAR: {ceme_vat:.2f} € | Posto OPC: {opc_total_vat:.2f} €"
        })
else:
    hour_now = datetime.now().hour
    is_vazio = (hour_now >= 22 or hour_now < 8)
    st.info(f"⚡ Simulação Regulamentar ({'Vazio' : 'Fora de Vazio'})")
    fallback_cemes = [
        ("Iberlectra (Indexado OMIE + TAR)", 0.195, 0.125, 0.11),
        ("Luzigás (Indexado OMIE + TAR)", 0.198, 0.128, 0.00),
        ("Goldenergy / ACP Electric", 0.215, 0.145, 0.00),
        ("EDP Comercial Mobilidade", 0.228, 0.158, 0.00),
        ("Galp Electric", 0.242, 0.169, 0.00),
    ]
    for name, fv, vz, act in fallback_cemes:
        rate = vz if is_vazio else fv
        ceme_vat = ((kwh_needed * (rate + 0.001)) + act) * IVA
        total = ceme_vat + opc_total_vat
        results.append({
            "name": name,
            "total": total,
            "unit": total / kwh_needed,
            "detail": f"CEME: {ceme_vat:.2f} € | OPC: {opc_total_vat:.2f} €"
        })

if direct_vat > 0:
    total_direct = kwh_needed * direct_vat
    results.append({
        "name": "📱 App Direta do Posto (Sem CEME / Ad-Hoc)",
        "total": total_direct,
        "unit": direct_vat,
        "detail": f"Tarifa fixa direta c/ IVA: {direct_vat:.2f} €/kWh"
    })

results.sort(key=lambda x: x["total"])
best_price = results[0]["total"]

st.markdown("##### 🏆 3. Qual Cartão / App Usar Agora:")

for idx, r in enumerate(results):
    diff = r["total"] - best_price
    cost_100km = r["unit"] * 16.5
    if idx == 0:
        st.markdown(f"""
        <div class="winner-card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <span class="badge-win">✓ Usar Este Cartão</span>
                    <div style="font-weight:800; font-size:1.05rem; color:#ffffff; margin-top:6px;">{r['name']}</div>
                    <div class="sub-text">{r['detail']}</div>
                </div>
                <div style="text-align:right;">
                    <div class="price-big">{r['total']:.2f} €</div>
                    <div class="sub-text">{r['unit']:.3f} €/kWh</div>
                </div>
            </div>
            <div style="margin-top:10px; padding-top:8px; border-top:1px solid rgba(255,255,255,0.12); display:flex; justify-content:space-between; font-size:0.78rem; color:#d1fae5;">
                <span>Custo 100 km: <b>{cost_100km:.2f} €</b></span>
                <span><b>Mais Económico</b></span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="normal-card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <div style="font-weight:700; font-size:0.95rem; color:#f1f5f9;">#{idx+1} {r['name']}</div>
                    <div class="sub-text">{r['detail']}</div>
                </div>
                <div style="text-align:right;">
                    <div class="price-norm">{r['total']:.2f} €</div>
                    <div class="sub-text" style="color:#f87171;">+{diff:.2f} € ({r['unit']:.3f} €/kWh)</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
