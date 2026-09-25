"""
Site de análise das roletas. Para rodar no PC:  python -m streamlit run app.py
"""

import base64
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

import streamlit as st

from analise import (FUSO_BRASILIA, PADROES, PERIODOS, analisar, carregar_giros, carregar_limites,
                     filtrar_periodo, formatar_limite)

ASSETS = Path(__file__).parent / "assets"

st.set_page_config(page_title="Guardian · Análise de Roletas", page_icon=str(ASSETS / "icone.png"), layout="wide")


def imagem_base64(nome):
    return base64.b64encode((ASSETS / nome).read_bytes()).decode()


LOGO = imagem_base64("logo.png")
SIMBOLO = imagem_base64("simbolo.png")

# ---------------------------------------------------------------- visual
# Cor do marcador de cada categoria (vermelho/preto mantêm a cor da mesa)
CORES_CATEGORIA = {
    "Vermelho": "#ef3b3b",
    "Preto": "#a1a1aa",
}
LARANJAS = ["#ff9a3c", "#ff6a00", "#ff3d00"]

CSS = """
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Sora:wght@500;600;700;800&display=swap" rel="stylesheet">
<style>
:root {
    --laranja: #ff6a00;
    --degrade: linear-gradient(135deg, #ffb347 0%, #ff6a00 55%, #ff3d00 100%);
    --fundo-card: rgba(22, 22, 26, .78);
    --borda: #26262c;
    --texto-2: #a1a1aa;
}
html, body, .stApp, p, li, label, input, button, div[data-baseweb="select"] {
    font-family: 'Inter', system-ui, sans-serif;
}
[data-testid="stIconMaterial"] { font-family: 'Material Symbols Rounded' !important; }
.stApp {
    background:
        radial-gradient(ellipse 60% 45% at 85% -5%, rgba(255, 106, 0, .22), transparent 70%),
        radial-gradient(ellipse 40% 35% at 0% 100%, rgba(255, 61, 0, .10), transparent 70%),
        linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px) 0 0 / 44px 44px,
        linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px) 0 0 / 44px 44px,
        #09090b;
}
#MainMenu, footer, header [data-testid="stToolbar"] { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 1.6rem; max-width: 1200px; }

/* Rótulos e campos */
.stSelectbox label p, .stTextInput label p {
    font-family: 'Sora', sans-serif; font-size: .72rem !important; font-weight: 600;
    letter-spacing: .14em; text-transform: uppercase; color: var(--texto-2);
}
div[data-baseweb="select"] > div, .stTextInput input {
    background: rgba(22, 22, 26, .9) !important; border-radius: 10px !important;
    border-color: var(--borda) !important;
}
div[data-baseweb="select"] > div:hover { border-color: var(--laranja) !important; }

/* Botões */
.stButton button, .stFormSubmitButton button {
    border-radius: 999px; font-family: 'Sora', sans-serif; font-weight: 600; letter-spacing: .02em;
}
.stFormSubmitButton button[kind="primaryFormSubmit"] {
    background: var(--degrade); border: none; color: #0b0b0d;
    box-shadow: 0 8px 28px -8px rgba(255, 106, 0, .7);
}
.stButton button[kind="secondary"] { background: transparent; border: 1px solid var(--borda); }
.stButton button[kind="secondary"]:hover { border-color: var(--laranja); color: var(--laranja); }

/* Cabeçalho */
.cabecalho { display: flex; align-items: center; gap: 1rem; margin-bottom: 1.6rem; }
.cabecalho img { height: 92px; filter: drop-shadow(0 0 18px rgba(255, 106, 0, .45)); }
.marca {
    font-family: 'Sora', sans-serif; font-size: .78rem; font-weight: 700; letter-spacing: .32em;
    text-transform: uppercase; background: var(--degrade); -webkit-background-clip: text; background-clip: text; color: transparent;
}
.titulo {
    font-family: 'Sora', sans-serif; font-size: clamp(1.5rem, 3.2vw, 2.3rem); font-weight: 800;
    text-transform: uppercase; letter-spacing: -.01em; line-height: 1.05; margin: .15rem 0 0; color: #fafafa;
}
.subtitulo { color: var(--texto-2); margin: .8rem 0 1.4rem; font-size: .95rem; }

/* Botões Análise | Simulador centralizados na página; Sair encostado à direita */
.st-key-modo, .st-key-sair { width: 100% !important; }
.st-key-modo [data-testid="stButtonGroup"] { width: 100%; display: flex; justify-content: center; }
.st-key-modo button { font-family: 'Sora', sans-serif; font-weight: 600; padding: .45rem 1.4rem; }
.st-key-sair .stButton { width: 100%; display: flex; justify-content: flex-end; }
.st-key-sair button { width: auto !important; padding: .45rem 1.6rem; }
/* Resumo */
.resumo {
    display: flex; flex-wrap: wrap; gap: .5rem 1.6rem; align-items: center;
    background: var(--fundo-card); border: 1px solid var(--borda); border-left: 3px solid var(--laranja);
    border-radius: 12px; padding: .8rem 1.1rem; margin: .6rem 0 1.4rem; font-size: .9rem; color: var(--texto-2);
    backdrop-filter: blur(8px);
}
.resumo b { color: #fafafa; font-weight: 600; }
.resumo .alerta { color: #fbbf24; }

/* Cartões */
.card {
    position: relative; background: var(--fundo-card); border: 1px solid var(--borda); border-radius: 16px;
    overflow: hidden; margin-bottom: 1rem; backdrop-filter: blur(8px); transition: border-color .2s, box-shadow .2s;
}
.card::before { content: ""; position: absolute; inset: 0 0 auto 0; height: 2px; background: var(--degrade); }
.card:hover { border-color: rgba(255, 106, 0, .55); box-shadow: 0 0 0 1px rgba(255, 106, 0, .15), 0 18px 40px -18px rgba(255, 106, 0, .45); }
.card-titulo {
    font-family: 'Sora', sans-serif; font-size: 1.05rem; font-weight: 700; letter-spacing: .02em;
    padding: 1rem 1.2rem .8rem; display: flex; align-items: center; gap: .65rem; color: #fafafa;
}
.card-titulo .ponto { width: .7rem; height: .7rem; border-radius: 50%; display: inline-block; box-shadow: 0 0 12px currentColor; }
.card table { width: 100%; border-collapse: collapse; font-size: .93rem; }
.card th {
    text-align: left; font-family: 'Sora', sans-serif; font-weight: 600; color: #71717a; font-size: .68rem;
    text-transform: uppercase; letter-spacing: .16em; padding: .3rem 1.2rem .5rem;
}
.card td { padding: .5rem 1.2rem; border-top: 1px solid #1f1f24; white-space: nowrap; }
.card th { white-space: nowrap; }
.card.compacto td, .card.compacto th { padding-left: .85rem; padding-right: .85rem; }
.card.compacto table { font-size: .88rem; }
.card tr:hover td { background: rgba(255, 106, 0, .06); }
.vezes { width: 46%; white-space: nowrap; }
.vezes .num { font-weight: 600; font-variant-numeric: tabular-nums; display: inline-block; min-width: 4.6rem; color: #fafafa; }
.barra { height: 6px; border-radius: 3px; display: inline-block; vertical-align: middle; background: var(--degrade); box-shadow: 0 0 10px rgba(255, 106, 0, .5); }
.rodadas { color: #d4d4d8; }
.vazio { padding: .4rem 1.2rem 1.2rem; color: var(--texto-2); font-size: .9rem; }

/* Ranking */
.secao { font-family: 'Sora', sans-serif; font-size: 1.25rem; font-weight: 700; text-transform: uppercase; margin: 1.6rem 0 .1rem; color: #fafafa; }
.secao span { color: var(--laranja); font-size: .85rem; font-weight: 600; text-transform: none; }
.secao-sub { color: var(--texto-2); font-size: .88rem; margin: 0 0 .8rem; }
.ranking .rolagem { overflow-x: auto; }
.ranking th.c, .ranking td.c { text-align: center; }
.ranking td { font-variant-numeric: tabular-nums; }
.ranking td.pos { font-family: 'Sora', sans-serif; font-weight: 700; color: var(--texto-2); width: 3rem; }
.ranking tr.lider td { background: rgba(255, 106, 0, .10); }
.ranking tr.lider td.pos { background: var(--degrade); -webkit-background-clip: text; background-clip: text; color: transparent; }
/* Login */
.login-logo { text-align: center; margin: 5vh 0 1.2rem; }
.login-logo img { width: min(220px, 60%); filter: drop-shadow(0 0 28px rgba(255, 106, 0, .45)); }
.login-texto { text-align: center; color: var(--texto-2); font-size: .92rem; margin-bottom: 1rem; }
[data-testid="stForm"] {
    background: var(--fundo-card); border: 1px solid var(--borda); border-radius: 16px; padding: 1.4rem;
    backdrop-filter: blur(8px);
}

/* Expansor */
[data-testid="stExpander"] details { background: var(--fundo-card); border: 1px solid var(--borda); border-radius: 12px; }
</style>
"""
# Linhas em branco encerram o bloco HTML no Markdown e fariam o CSS aparecer como texto
st.markdown("\n".join(linha for linha in CSS.splitlines() if linha.strip()), unsafe_allow_html=True)


# ---------------------------------------------------------------- login
def senha_confere(usuario, senha):
    try:
        cfg = st.secrets["login"]
        cfg["usuario"], cfg["sal"], cfg["senha_hash"]
    except (KeyError, FileNotFoundError):
        st.error("Login não configurado: cole o bloco [login] gerado por criar_senha.py nos Secrets do app.")
        st.stop()
    hash_digitado = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(cfg["sal"]), 200_000).hex()
    return hmac.compare_digest(usuario, cfg["usuario"]) and hmac.compare_digest(hash_digitado, cfg["senha_hash"])


if not st.session_state.get("logado"):
    _, meio, _ = st.columns([1, 1.2, 1])
    with meio:
        st.markdown(
            f'<div class="login-logo"><img src="data:image/png;base64,{LOGO}" alt="Guardian"></div>'
            '<p class="login-texto">Análise inteligente de roletas ao vivo</p>',
            unsafe_allow_html=True,
        )
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
    return carregar_giros(), carregar_limites()


por_mesa, limites = dados()

topo, centro, sair = st.columns([1, 1, 1], vertical_alignment="center")
with centro:
    modo = st.segmented_control("Modo", ["Análise", "Simulador"], default="Análise", key="modo",
                                label_visibility="collapsed") or "Análise"
topo.markdown(
    f'<div class="cabecalho"><img src="data:image/png;base64,{SIMBOLO}" alt="">'
    '<div><div class="marca">Guardian</div><p class="titulo">Análise de Roletas</p></div></div>',
    unsafe_allow_html=True,
)
if sair.button("Sair", key="sair"):
    st.session_state.logado = False
    st.rerun()
if modo == "Simulador":
    st.markdown('<p class="subtitulo">Simulação ao vivo: acompanha a mesa em tempo real a partir do Start — sem apostar dinheiro.</p>',
                unsafe_allow_html=True)

# Alerta de dados atrasados (coleta normal: a cada 5 min)
ultimo_giro = max(g[-1][0] for g in por_mesa.values())
atraso = datetime.now(timezone.utc) - ultimo_giro
if atraso > timedelta(minutes=75):
    horas = atraso.total_seconds() / 3600
    st.markdown(
        f'<div class="resumo" style="border-left-color:#fbbf24"><span class="alerta">⚠ Coleta atrasada: '
        f'o último giro registrado foi há {horas:.1f} h ({ultimo_giro.astimezone(FUSO_BRASILIA):%d/%m %H:%M}). '
        'Verifique o cron-job.org e a aba Actions do GitHub.</span></div>',
        unsafe_allow_html=True,
    )

if modo == "Simulador":
    from pagina_simulador import pagina_simulador
    pagina_simulador(por_mesa, limites)
    st.stop()

c1, c2, c3 = st.columns(3)
mesa = c1.selectbox("Roleta", sorted(por_mesa))
limite_mesa = limites.get(mesa)
padrao = c2.selectbox(
    "Padrão",
    list(PADROES),
    format_func=lambda p: f"{p}  ({formatar_limite(limite_mesa)})" if limite_mesa else p,
)
periodo = c3.selectbox("Período", list(PERIODOS), index=1)

# ---------------------------------------------------------------- ranking das mesas
def ranking_mesas(padrao, periodo):
    """Mesas ordenadas pela maior ausência registrada (recorde) do padrão, da menor para a maior."""
    linhas = []
    for nome_mesa, todos in por_mesa.items():
        giros_mesa = filtrar_periodo(todos, periodo)
        if not giros_mesa:
            continue
        res, _ = analisar(giros_mesa, padrao)
        recordes = {cat: (max(r["contagem"]) if r["contagem"] else None) for cat, r in res.items()}
        validos = [v for v in recordes.values() if v is not None]
        chave = (max(validos), sum(validos)) if validos else (float("inf"), float("inf"))
        linhas.append((chave, nome_mesa, recordes, len(giros_mesa)))
    linhas.sort(key=lambda x: x[0])
    return linhas


linhas_ranking = ranking_mesas(padrao, periodo)
if linhas_ranking:
    categorias = list(PADROES[padrao])
    cab = "".join(f"<th class='c'>{escape(c)}</th>" for c in categorias)
    corpo = []
    for pos, (_, nome_mesa, recordes, qtd) in enumerate(linhas_ranking, start=1):
        cels = "".join(f"<td class='c'>{'—' if recordes[c] is None else recordes[c]}</td>" for c in categorias)
        lim = limites.get(nome_mesa)
        destaque = " class='lider'" if pos == 1 else ""
        qtd_fmt = f"{qtd:,}".replace(",", ".")
        corpo.append(
            f"<tr{destaque}><td class='pos'>{pos}º</td><td>{escape(nome_mesa)}</td>{cels}"
            f"<td class='c'>{qtd_fmt}</td><td>{formatar_limite(lim) if lim else '—'}</td></tr>"
        )
    st.markdown(
        f'<p class="secao">Ranking das mesas <span>· {escape(padrao)} · {escape(periodo)}</span></p>'
        '<p class="secao-sub">Maior sequência sem sair de cada categoria. Ranking da melhor mesa para a pior no padrão e período selecionado.</p>'
        f'<div class="card ranking"><div class="rolagem"><table><tr><th>#</th><th>Mesa</th>{cab}'
        f'<th class="c">Rodadas</th><th>Limite</th></tr>{"".join(corpo)}</table></div></div>',
        unsafe_allow_html=True,
    )

with st.expander("Como ler esta análise"):
    st.markdown(
        """
- **Rodadas sem sair**: por quantas rodadas seguidas o padrão **não** apareceu. O **zero conta como "não saiu"** para todos os padrões.
- **Vezes**: quantas vezes aconteceu uma ausência exatamente desse tamanho no período escolhido.
- **Ranking das mesas**: compara todas as mesas no padrão e período escolhidos pelo **recorde** (maior sequência sem sair) de cada categoria. Fica em 1º a mesa cujo pior recorde é o menor; empates são desempatados pela soma dos recordes. Mesas com mais rodadas analisadas tendem a ter recordes maiores — confira a coluna *Rodadas*.
- A ausência que ainda está em andamento (o padrão ainda não voltou a sair) só entra na contagem quando termina.
- Cada rodada é independente: um padrão estar há muito tempo sem sair **não aumenta** a chance de ele sair na próxima.
"""
    )

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
    partes.append(f'<span class="alerta">⚠ {len(tamanhos) - 1} interrupção(ões) no período (pausa da mesa ou giro não registrado) — a contagem recomeça após cada uma</span>')
st.markdown(f'<div class="resumo">{"".join(partes)}</div>', unsafe_allow_html=True)


def cartao(nome, cor, contagem, compacto=False):
    classe = "card compacto" if compacto else "card"
    cabecalho = f'<div class="card-titulo"><span class="ponto" style="background:{cor};color:{cor}"></span>{escape(nome)}</div>'
    if not contagem:
        return f'<div class="{classe}">{cabecalho}<div class="vazio">Nenhuma ausência completa nesse período.</div></div>'
    maior_vezes = max(contagem.values())
    barra_max = 44 if compacto else 70
    linhas = []
    for rodadas in sorted(contagem):
        vezes = contagem[rodadas]
        largura = max(4, round(barra_max * vezes / maior_vezes))
        linhas.append(
            f'<tr><td class="vezes"><span class="num">{vezes} {"vez" if vezes == 1 else "vezes"}</span>'
            f'<span class="barra" style="width:{largura}px"></span></td>'
            f'<td class="rodadas">{rodadas} rodada{"s" if rodadas > 1 else ""} sem sair</td></tr>'
        )
    return (f'<div class="{classe}">{cabecalho}<table><tr><th>Vezes</th><th>Rodadas sem sair</th></tr>'
            f'{"".join(linhas)}</table></div>')


colunas = st.columns(len(resultado))
for i, (coluna, (nome, r)) in enumerate(zip(colunas, resultado.items())):
    cor = CORES_CATEGORIA.get(nome, LARANJAS[i % 3])
    coluna.markdown(cartao(nome, cor, r["contagem"], compacto=len(resultado) > 2), unsafe_allow_html=True)
