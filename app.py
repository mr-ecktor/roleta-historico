"""
Site de análise das roletas. Para rodar no PC:  python -m streamlit run app.py
"""

import hashlib
import hmac
from html import escape

import streamlit as st

from analise import FUSO_BRASILIA, PADROES, PERIODOS, analisar, carregar_giros, filtrar_periodo

st.set_page_config(page_title="Histórico de Roletas", page_icon="🎡", layout="wide")

# ---------------------------------------------------------------- visual
CORES_CATEGORIA = {
    "Vermelho": "#e0393e",
    "Preto": "#9aa3a0",
    "Par": "#4f9dde",
    "Ímpar": "#b57be0",
    "Baixo (1-18)": "#3fbf8f",
    "Alto (19-36)": "#f08a3c",
}
CORES_TRIO = ["#d4af37", "#3fbf8f", "#4f9dde"]  # dúzias e colunas

st.markdown(
    """
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Outfit:wght@500;600;700&display=swap" rel="stylesheet">
<style>
html, body, [class*="st-"], .stMarkdown, .stSelectbox, .stTextInput, button {
    font-family: 'Inter', system-ui, sans-serif;
}
h1, h2, h3, .titulo, .card-titulo { font-family: 'Outfit', 'Inter', sans-serif !important; }
#MainMenu, footer, header [data-testid="stToolbar"] { visibility: hidden; }
.block-container { padding-top: 2rem; max-width: 1200px; }

.titulo { font-size: 2.1rem; font-weight: 700; letter-spacing: -0.02em; margin: 0; }
.titulo span { color: #d4af37; }
.subtitulo { color: #93a39a; margin: .2rem 0 1.4rem; font-size: .95rem; }

.resumo {
    display: flex; flex-wrap: wrap; gap: .6rem 1.4rem; align-items: center;
    background: #17221d; border: 1px solid #243229; border-radius: 12px;
    padding: .8rem 1.1rem; margin: .6rem 0 1.4rem; font-size: .92rem; color: #b9c6be;
}
.resumo b { color: #e9efe9; font-weight: 600; }
.resumo .alerta { color: #f0b43c; }

.card {
    background: #17221d; border: 1px solid #243229; border-radius: 14px;
    overflow: hidden; margin-bottom: 1rem;
}
.card-titulo {
    font-size: 1.15rem; font-weight: 600; padding: .85rem 1.1rem;
    border-bottom: 1px solid #243229; display: flex; align-items: center; gap: .6rem;
}
.card-titulo .ponto { width: .8rem; height: .8rem; border-radius: 50%; display: inline-block; }
.card table { width: 100%; border-collapse: collapse; font-size: .95rem; }
.card th {
    text-align: left; font-weight: 500; color: #93a39a; font-size: .78rem;
    text-transform: uppercase; letter-spacing: .06em; padding: .6rem 1.1rem .4rem;
}
.card td { padding: .45rem 1.1rem; border-top: 1px solid #1f2c25; }
.card tr:hover td { background: #1c2a23; }
.vezes { width: 42%; }
.vezes .num { font-weight: 600; font-variant-numeric: tabular-nums; display: inline-block; min-width: 4.2rem; }
.barra { height: 6px; border-radius: 3px; display: inline-block; vertical-align: middle; opacity: .85; }
.rodadas { color: #d5ddd8; }
.vazio { padding: 1rem 1.1rem; color: #93a39a; font-size: .9rem; }

.login-box { max-width: 380px; margin: 8vh auto 0; }
</style>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------- login
def senha_confere(usuario, senha):
    cfg = st.secrets["login"]
    hash_digitado = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(cfg["sal"]), 200_000).hex()
    return hmac.compare_digest(usuario, cfg["usuario"]) and hmac.compare_digest(hash_digitado, cfg["senha_hash"])


if not st.session_state.get("logado"):
    _, meio, _ = st.columns([1, 1.3, 1])
    with meio:
        st.markdown('<div style="height:8vh"></div><p class="titulo">🎡 Histórico de <span>Roletas</span></p>'
                    '<p class="subtitulo">Entre para acessar as análises</p>', unsafe_allow_html=True)
        with st.form("login"):
            usuario = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar", type="primary", use_container_width=True):
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

topo, sair = st.columns([6, 1], vertical_alignment="center")
topo.markdown('<p class="titulo">🎡 Histórico de <span>Roletas</span></p>'
              '<p class="subtitulo">Quantas vezes cada padrão ficou X rodadas seguidas sem sair</p>',
              unsafe_allow_html=True)
if sair.button("Sair", use_container_width=True):
    st.session_state.logado = False
    st.rerun()

c1, c2, c3 = st.columns(3)
mesa = c1.selectbox("Roleta", sorted(por_mesa))
padrao = c2.selectbox("Padrão", list(PADROES))
periodo = c3.selectbox("Período", list(PERIODOS), index=1)

giros = filtrar_periodo(por_mesa[mesa], periodo)
if not giros:
    st.warning("Nenhuma rodada registrada nesse período.")
    st.stop()

primeiro = giros[0][0].astimezone(FUSO_BRASILIA)
ultimo = giros[-1][0].astimezone(FUSO_BRASILIA)
resultado, tamanhos = analisar(giros, padrao)

partes = [
    f"<span><b>{len(giros):,}</b> rodadas analisadas</span>".replace(",", "."),
    f"<span>De <b>{primeiro:%d/%m %H:%M}</b> até <b>{ultimo:%d/%m %H:%M}</b> (Brasília)</span>",
]
if len(tamanhos) > 1:
    partes.append(f'<span class="alerta">⚠ {len(tamanhos) - 1} falha(s) de coleta — a contagem recomeça após cada uma</span>')
st.markdown(f'<div class="resumo">{"".join(partes)}</div>', unsafe_allow_html=True)


def cartao(nome, cor, contagem):
    cabecalho = f'<div class="card-titulo"><span class="ponto" style="background:{cor}"></span>{escape(nome)}</div>'
    if not contagem:
        return f'<div class="card">{cabecalho}<div class="vazio">Nenhuma ausência completa nesse período.</div></div>'
    maior_vezes = max(contagem.values())
    linhas = []
    for rodadas in sorted(contagem):
        vezes = contagem[rodadas]
        largura = max(4, round(70 * vezes / maior_vezes))
        linhas.append(
            f'<tr><td class="vezes"><span class="num">{vezes} {"vez" if vezes == 1 else "vezes"}</span>'
            f'<span class="barra" style="width:{largura}px;background:{cor}"></span></td>'
            f'<td class="rodadas">{rodadas} rodada{"s" if rodadas > 1 else ""} sem sair</td></tr>'
        )
    return (f'<div class="card">{cabecalho}<table><tr><th>Vezes</th><th>Rodadas sem sair</th></tr>'
            f'{"".join(linhas)}</table></div>')


colunas = st.columns(len(resultado))
for i, (coluna, (nome, r)) in enumerate(zip(colunas, resultado.items())):
    cor = CORES_CATEGORIA.get(nome, CORES_TRIO[i % 3])
    coluna.markdown(cartao(nome, cor, r["contagem"]), unsafe_allow_html=True)

with st.expander("Como ler esta análise"):
    st.markdown(
        """
- **Rodadas sem sair**: por quantas rodadas seguidas o padrão **não** apareceu. O **zero conta como "não saiu"** para todos os padrões.
- **Vezes**: quantas vezes aconteceu uma ausência exatamente desse tamanho no período escolhido.
- A ausência que ainda está em andamento (o padrão ainda não voltou a sair) só entra na contagem quando termina.
- Cada rodada é independente: um padrão estar há muito tempo sem sair **não aumenta** a chance de ele sair na próxima.
"""
    )
