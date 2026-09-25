"""
Tela do Simulador ao vivo (botão "Simulador" do site).

Depois do Start, acompanha os giros reais da mesa escolhida (consulta a fonte a cada ~10 s)
e simula as apostas com a tabela de recuperação do usuário. Nenhuma aposta real é feita.
O estado fica na sessão do navegador: fechar a aba encerra a simulação.
"""

from datetime import datetime, timezone
from html import escape

import streamlit as st

from analise import FUSO_BRASILIA, PADROES, formatar_limite
from coletor import buscar_ao_vivo
from simulador import PAGAMENTO, SimulacaoAoVivo, niveis_tabela, sequencia_da_tabela

ATUALIZAR_A_CADA_S = 10


def reais(v, sinal=False):
    texto = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if sinal:
        return ("+" if v > 0 else "−" if v < 0 else "") + f"R$ {texto}"
    return ("−" if v < 0 else "") + f"R$ {texto}"


CSS = """
<style>
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: .8rem; margin: .6rem 0 1.2rem; }
.tile { background: var(--fundo-card); border: 1px solid var(--borda); border-radius: 14px; padding: .9rem 1.1rem; }
.tile .rotulo { font-family: 'Sora', sans-serif; font-size: .68rem; font-weight: 600; letter-spacing: .14em; text-transform: uppercase; color: #71717a; }
.tile .valor { font-family: 'Sora', sans-serif; font-size: 1.45rem; font-weight: 700; color: #fafafa; margin-top: .25rem; font-variant-numeric: tabular-nums; }
.tile .detalhe { font-size: .8rem; color: var(--texto-2); margin-top: .15rem; }
.tile.destaque { border-color: rgba(242, 92, 0, .55); }
.stNumberInput label p { font-family: 'Sora', sans-serif; font-size: .72rem !important; font-weight: 600;
    letter-spacing: .14em; text-transform: uppercase; color: var(--texto-2); }
.stNumberInput input { background: rgba(22, 22, 26, .9) !important; }
.fichas { font-size: .95rem; color: var(--texto-2); margin: .2rem 0 .8rem; }
.fichas b { color: #fafafa; font-variant-numeric: tabular-nums; }
.painel { display: flex; flex-wrap: wrap; align-items: center; gap: .6rem 1.6rem; background: var(--fundo-card);
          border: 1px solid var(--borda); border-left: 3px solid var(--laranja); border-radius: 14px; padding: 1rem 1.2rem; margin-top: .4rem; }
.cronometro { font-family: 'Sora', sans-serif; font-size: 2.2rem; font-weight: 800; color: #fafafa; font-variant-numeric: tabular-nums; letter-spacing: .02em; }
.estado { font-size: .95rem; color: #d4d4d8; }
.estado small { display: block; color: var(--texto-2); font-size: .8rem; margin-top: .2rem; }
.ponto-vivo { display: inline-block; width: .6rem; height: .6rem; border-radius: 50%; background: #22c55e; margin-right: .45rem;
              box-shadow: 0 0 10px #22c55e; animation: pulsa 1.4s infinite; }
.ponto-parado { display: inline-block; width: .6rem; height: .6rem; border-radius: 50%; background: #71717a; margin-right: .45rem; }
@keyframes pulsa { 50% { opacity: .35; } }
.st-key-sim_start button { background: var(--degrade); border: none; color: #0b0b0d; font-family: 'Sora', sans-serif; font-weight: 700;
                           box-shadow: 0 8px 28px -8px rgba(255, 106, 0, .7); }
</style>
"""


@st.cache_data(ttl=ATUALIZAR_A_CADA_S - 2, show_spinner=False)
def giros_recentes(mesa):
    return buscar_ao_vivo(mesa)


def cronometro(segundos):
    s = int(segundos)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def pagina_simulador(por_mesa, limites):
    st.markdown(CSS, unsafe_allow_html=True)
    sessao = st.session_state.get("ao_vivo")
    rodando = bool(sessao and sessao["rodando"])

    c1, c2, c3 = st.columns(3)
    mesa = c1.selectbox("Roleta", sorted(por_mesa), key="sim_mesa", disabled=rodando)
    padrao = c2.selectbox("Padrão", list(PADROES), key="sim_padrao", disabled=rodando)
    categoria = c3.selectbox("Apostar em", list(PADROES[padrao]), key=f"sim_cat_{padrao}", disabled=rodando)

    limite = limites.get(mesa)
    max_niveis = niveis_tabela(padrao) - 1
    d1, d2, d3, d4 = st.columns(4)
    gatilho = d1.number_input("Gatilho", min_value=0, max_value=50, value=5, step=1, key="sim_gatilho", disabled=rodando,
                              help="Entra quando a categoria completar esse número de rodadas seguidas sem sair")
    ficha = d2.number_input("Ficha inicial (R$)", min_value=0.10, max_value=10000.0, disabled=rodando,
                            value=float(limite["min"]) if limite else 0.50, step=0.50, format="%.2f", key=f"sim_ficha_{mesa}")
    max_rec = d3.number_input("Máx. recuperações", min_value=0, max_value=max_niveis, value=min(3, max_niveis), step=1,
                              key=f"sim_rec_{padrao}", disabled=rodando,
                              help="Até qual nível da sua tabela de recuperação o robô vai")
    banca = d4.number_input("Banca inicial (R$)", min_value=1.0, max_value=1_000_000.0, value=100.0, step=10.0,
                            format="%.2f", key="sim_banca", disabled=rodando)

    fichas = sequencia_da_tabela(padrao, ficha, int(max_rec))
    risco = sum(fichas)
    st.markdown(f'<p class="fichas">Valor em risco por ciclo: <b>{reais(risco)}</b></p>', unsafe_allow_html=True)
    with st.expander("Ver todos os níveis do ciclo"):
        investido, linhas = 0.0, []
        for nivel, aposta in enumerate(fichas, start=1):
            investido += aposta
            ganho = aposta * (PAGAMENTO[padrao] + 1) - investido
            linhas.append(f"<tr><td class='c'>{nivel}</td><td class='c'>{reais(aposta)}</td>"
                          f"<td class='c'>{reais(investido)}</td><td class='c'>{reais(ganho, sinal=True)}</td></tr>")
        st.markdown('<div class="card ranking"><div class="rolagem"><table><tr><th class="c">Nível</th>'
                    '<th class="c">Aposta</th><th class="c">Investido</th><th class="c">Ganho se acertar</th></tr>'
                    + "".join(linhas) + "</table></div></div>", unsafe_allow_html=True)

    if limite and ficha < limite["min"]:
        st.warning(f"A ficha inicial está abaixo do mínimo desta mesa ({formatar_limite(limite)}).")
    if limite and fichas[-1] > limite["max"]:
        st.warning(f"A última recuperação ({reais(fichas[-1])}) passa do máximo desta mesa ({formatar_limite(limite)}).")
    if risco > banca:
        st.warning(f"Um ciclo completo arrisca {reais(risco)}, mais que a banca inicial ({reais(banca)}).")

    b1, b2, _ = st.columns([1, 1, 4])
    if not rodando:
        if b1.button("▶ Start", key="sim_start", use_container_width=True):
            try:
                anteriores = giros_recentes(mesa)
            except Exception as erro:
                st.error(f"Não foi possível ler a mesa agora ({erro}). Tente de novo em alguns segundos.")
                return
            sim = SimulacaoAoVivo(padrao, categoria, int(gatilho), fichas, banca,
                                  limite_max=limite["max"] if limite else None)
            sim.aquecer(anteriores)
            st.session_state.ao_vivo = {
                "sim": sim, "mesa": mesa, "inicio": datetime.now(timezone.utc), "fim": None, "rodando": True,
                "ultimo": anteriores[-1][0] if anteriores else None, "ultimo_giro": anteriores[-1] if anteriores else None,
                "erro": None,
            }
            st.rerun()
        if sessao and b2.button("Zerar", key="sim_zerar", use_container_width=True):
            del st.session_state.ao_vivo
            st.rerun()
    elif b1.button("■ Parar", key="sim_parar", use_container_width=True):
        sessao["rodando"] = False
        sessao["fim"] = datetime.now(timezone.utc)
        st.rerun()

    if st.session_state.get("ao_vivo"):
        painel_ao_vivo()
    else:
        st.info("Configure a estratégia e aperte **Start**. A simulação acompanha os giros reais da mesa a partir desse "
                "momento, sem fazer apostas de verdade. Mantenha esta aba aberta enquanto ela roda.")


@st.fragment(run_every=1)
def painel_ao_vivo():
    sessao = st.session_state.get("ao_vivo")
    if not sessao:
        return
    sim = sessao["sim"]

    if sessao["rodando"]:
        try:
            for horario, numero in giros_recentes(sessao["mesa"]):
                if sessao["ultimo"] is None or horario > sessao["ultimo"]:
                    sim.processar(horario, numero)
                    sessao["ultimo"], sessao["ultimo_giro"] = horario, (horario, numero)
            sessao["erro"] = None
        except Exception as erro:
            sessao["erro"] = str(erro)
        if sim.quebrou:
            sessao["rodando"], sessao["fim"] = False, datetime.now(timezone.utc)

    fim = sessao["fim"] or datetime.now(timezone.utc)
    decorrido = (fim - sessao["inicio"]).total_seconds()
    ponto = '<span class="ponto-vivo"></span>Jogando' if sessao["rodando"] else '<span class="ponto-parado"></span>Parado'
    ultimo = sessao["ultimo_giro"]
    detalhe = f"{escape(sessao['mesa'])} · {sim.giros_vistos} giros desde o Start"
    if ultimo:
        detalhe += f" · último: <b>{ultimo[1]}</b> às {ultimo[0].astimezone(FUSO_BRASILIA):%H:%M:%S}"
    if sessao.get("erro"):
        detalhe += " · ⚠ falha ao ler a mesa, tentando de novo"
    st.markdown(
        f'<div class="painel"><div class="cronometro">{cronometro(decorrido)}</div>'
        f'<div class="estado">{ponto} — {escape(sim.status)}<small>{detalhe}</small></div></div>',
        unsafe_allow_html=True,
    )

    r = sim.resumo
    lucro = sim.saldo - sim.banca
    ganhas = f"{r['vitorias']} ganha" + ("" if r["vitorias"] == 1 else "s")
    estouros = f"{r['estouros']} estouro" + ("" if r["estouros"] == 1 else "s")
    tiles = [
        ("Saldo inicial", reais(sim.banca), "banca no Start", False),
        ("Saldo final", reais(sim.saldo), f"{'lucro' if lucro > 0 else 'prejuízo' if lucro < 0 else 'resultado'}: "
                                          f"{reais(lucro, sinal=True)}", True),
        ("Entradas", str(r["entradas"]), f"{ganhas} · {estouros}", False),
        ("Máx. sem sair", str(sim.max_sem_sair), f"maior sequência sem {sim.categoria} desde o Start", False),
    ]
    st.markdown(
        '<div class="tiles">' + "".join(
            f'<div class="tile{" destaque" if d else ""}"><div class="rotulo">{escape(a)}</div>'
            f'<div class="valor">{escape(b)}</div><div class="detalhe">{escape(c)}</div></div>'
            for a, b, c, d in tiles
        ) + "</div>",
        unsafe_allow_html=True,
    )
