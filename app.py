"""
Site de análise das roletas. Para rodar no PC:  python -m streamlit run app.py
"""

import hashlib
import hmac
from datetime import timezone

import pandas as pd
import streamlit as st

from analise import FUSO_BRASILIA, PADROES, PERIODOS, analisar, carregar_giros, filtrar_periodo, tabela

st.set_page_config(page_title="Histórico de Roletas", page_icon="🎡", layout="wide")


# ---------------------------------------------------------------- login
def senha_confere(usuario, senha):
    cfg = st.secrets["login"]
    hash_digitado = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(cfg["sal"]), 200_000).hex()
    return hmac.compare_digest(usuario, cfg["usuario"]) and hmac.compare_digest(hash_digitado, cfg["senha_hash"])


if not st.session_state.get("logado"):
    st.title("🎡 Histórico de Roletas")
    with st.form("login"):
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar", type="primary"):
            if senha_confere(usuario, senha):
                st.session_state.logado = True
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos.")
    st.stop()


# ---------------------------------------------------------------- dados
@st.cache_data(ttl=300, show_spinner="Carregando dados...")
def dados():
    return carregar_giros()


por_mesa = dados()

topo, sair = st.columns([6, 1])
topo.title("🎡 Histórico de Roletas")
if sair.button("Sair"):
    st.session_state.logado = False
    st.rerun()

c1, c2, c3 = st.columns(3)
mesa = c1.selectbox("1. Roleta", sorted(por_mesa))
padrao = c2.selectbox("2. Padrão", list(PADROES))
periodo = c3.selectbox("3. Período", list(PERIODOS), index=1)

giros = filtrar_periodo(por_mesa[mesa], periodo)
if not giros:
    st.warning("Nenhuma rodada registrada nesse período.")
    st.stop()

ultimo = por_mesa[mesa][-1][0].astimezone(FUSO_BRASILIA)
primeiro = giros[0][0].astimezone(FUSO_BRASILIA)
resultado, tamanhos = analisar(giros, padrao)

resumo = f"**{len(giros):,} rodadas** analisadas".replace(",", ".")
resumo += f", de {primeiro:%d/%m %H:%M} até {ultimo:%d/%m %H:%M} (horário de Brasília)."
if len(tamanhos) > 1:
    resumo += f" ⚠️ {len(tamanhos) - 1} falha(s) de coleta no período — a contagem recomeça após cada uma."
st.caption(resumo)

# Situação atual de cada categoria
metricas = st.columns(len(resultado))
for coluna, (nome, r) in zip(metricas, resultado.items()):
    atual = r["atual"]
    coluna.metric(f"{nome} — agora", "—" if atual is None else f"{atual} sem sair")

st.divider()

# Tabela de cada categoria
for aba, (nome, r) in zip(st.tabs(list(resultado)), resultado.items()):
    with aba:
        linhas = tabela(r, tamanhos)
        if not linhas:
            st.info("Ainda não há ausências completas para mostrar nesse período.")
            continue
        df = pd.DataFrame(linhas, columns=[
            "Rodadas sem sair", "Vezes (exato)", "Esperado (exato)", "Vezes (X ou mais)", "Esperado (X ou mais)",
        ])
        df["Rodadas sem sair"] = df["Rodadas sem sair"].map(lambda k: f"{k} rodada{'s' if k > 1 else ''} seguida{'s' if k > 1 else ''}")
        st.dataframe(
            df,
            hide_index=True,
            use_container_width=True,
            height=min(38 * (len(df) + 1), 800),
            column_config={
                "Esperado (exato)": st.column_config.NumberColumn(format="%.1f"),
                "Esperado (X ou mais)": st.column_config.NumberColumn(format="%.1f"),
            },
        )

with st.expander("Como ler esta análise"):
    st.markdown(
        """
- **Rodadas sem sair**: por quantas rodadas seguidas o padrão **não** apareceu. O **zero conta como "não saiu"** para todos os padrões.
- **Vezes (exato)**: quantas ausências tiveram exatamente esse tamanho.
- **Vezes (X ou mais)**: quantas ausências chegaram **pelo menos** a esse tamanho.
- **Esperado**: quantas vezes isso deveria acontecer só pela probabilidade, no mesmo número de rodadas.
  Se *Vezes* e *Esperado* estão próximos, a roleta está se comportando como uma roleta justa.
- **Agora**: há quantas rodadas o padrão está sem sair neste momento (essa ausência ainda não entra na tabela).
- Cada rodada é independente: um padrão estar há muito tempo sem sair **não aumenta** a chance de ele sair na próxima.
"""
    )
