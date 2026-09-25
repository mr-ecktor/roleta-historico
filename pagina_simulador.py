"""
Tela do Simulador ao vivo (botão "Simulador" do site).

Depois do Start, acompanha os giros reais da mesa escolhida (consulta a fonte a cada ~10 s)
e simula as apostas com a tabela de recuperação do usuário, em um ou mais padrões ao mesmo tempo
(todos usando o mesmo caixa). Nenhuma aposta real é feita.
O estado fica na sessão do navegador: fechar a aba encerra a simulação.
"""

from datetime import datetime, timezone
from html import escape

import streamlit as st

from analise import FUSO_BRASILIA, VERMELHOS, formatar_limite
from coletor import buscar_ao_vivo
from simulador import CATEGORIAS, PAGAMENTO, SimulacaoAoVivo, niveis_tabela, sequencia_da_tabela

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
.stNumberInput label p, .stMultiSelect label p { font-family: 'Sora', sans-serif; font-size: .72rem !important; font-weight: 600;
    letter-spacing: .14em; text-transform: uppercase; color: var(--texto-2); }
.stNumberInput input { background: rgba(22, 22, 26, .9) !important; }
.stMultiSelect span[data-baseweb="tag"] { background: rgba(255, 106, 0, .18) !important; border: 1px solid rgba(255, 106, 0, .5); color: #fafafa; }
.fichas { font-size: .95rem; color: var(--texto-2); margin: .2rem 0 .8rem; }
.fichas b { color: #fafafa; font-variant-numeric: tabular-nums; }
.painel { display: flex; flex-wrap: wrap; align-items: center; gap: .6rem 1.6rem; background: var(--fundo-card);
          border: 1px solid var(--borda); border-left: 3px solid var(--laranja); border-radius: 14px; padding: 1rem 1.2rem; margin-top: .4rem; }
.cronometro { font-family: 'Sora', sans-serif; font-size: 2.2rem; font-weight: 800; color: #fafafa; font-variant-numeric: tabular-nums; letter-spacing: .02em; }
.estado { font-size: .95rem; color: #d4d4d8; }
.estado small { display: block; color: var(--texto-2); font-size: .8rem; margin-top: .2rem; }
.robo { font-size: .92rem; color: #d4d4d8; margin-top: .35rem; }
.robo b { color: #fafafa; }
.ponto-vivo { display: inline-block; width: .6rem; height: .6rem; border-radius: 50%; background: #22c55e; margin-right: .45rem;
              box-shadow: 0 0 10px #22c55e; animation: pulsa 1.4s infinite; }
.ponto-parado { display: inline-block; width: .6rem; height: .6rem; border-radius: 50%; background: #71717a; margin-right: .45rem; }
@keyframes pulsa { 50% { opacity: .35; } }
.num { display: inline-block; min-width: 1.9rem; text-align: center; padding: .1rem .35rem; border-radius: 6px;
       font-weight: 700; font-variant-numeric: tabular-nums; color: #fafafa; }
.num.verm { background: #b91c1c; }
.num.preto { background: #27272a; border: 1px solid #3f3f46; }
.num.zero { background: #15803d; }
.historico td.ganhou { color: #4ade80; }
.historico td.perdeu { color: #f87171; }
.st-key-sim_start button {
    background: var(--degrade) !important; border: none !important; color: #0b0b0d !important; opacity: 1 !important;
    font-family: 'Sora', sans-serif; font-weight: 700; letter-spacing: .02em;
    box-shadow: 0 8px 28px -8px rgba(255, 106, 0, .7);
}
.st-key-sim_start button p { color: #0b0b0d !important; font-weight: 700; }
.st-key-sim_start button:hover { filter: brightness(1.08); box-shadow: 0 10px 32px -6px rgba(255, 106, 0, .85); }
.aviso-start { display: flex; align-items: center; gap: .8rem; background: var(--fundo-card); border: 1px solid var(--borda);
               border-left: 3px solid var(--laranja); border-radius: 12px; padding: .85rem 1.1rem; color: #d4d4d8; font-size: .92rem; margin-top: .6rem; }
.aviso-start b { color: var(--laranja); }
.aviso-start .icone { font-size: 1.2rem; color: var(--laranja); }
.aviso-start.alerta { border-left-color: #fbbf24; }
.aviso-start.alerta .icone { color: #fbbf24; }
</style>
"""


@st.cache_data(ttl=ATUALIZAR_A_CADA_S - 2, show_spinner=False)
def giros_recentes(mesa):
    return buscar_ao_vivo(mesa)


def cronometro(segundos):
    s = int(segundos)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def aviso(html):
    st.markdown(f'<div class="aviso-start"><span class="icone">◉</span><div>{html}</div></div>', unsafe_allow_html=True)


def alerta(texto):
    """Aviso em âmbar no estilo do site (st.warning trataria "R$ ... R$" como fórmula matemática)."""
    st.markdown(f'<div class="aviso-start alerta"><span class="icone">⚠</span><div>{escape(texto)}</div></div>',
                unsafe_allow_html=True)


def cor_numero(n):
    if n is None:
        return "—"
    classe = "zero" if n == 0 else "verm" if n in VERMELHOS else "preto"
    return f'<span class="num {classe}">{n}</span>'


def tabela_niveis(fichas, padrao):
    investido, linhas = 0.0, []
    for nivel, aposta in enumerate(fichas, start=1):
        investido += aposta
        ganho = aposta * (PAGAMENTO[padrao] + 1) - investido
        linhas.append(f"<tr><td class='c'>{nivel}</td><td class='c'>{reais(aposta)}</td>"
                      f"<td class='c'>{reais(investido)}</td><td class='c'>{reais(ganho, sinal=True)}</td></tr>")
    return ('<div class="card ranking"><div class="rolagem"><table><tr><th class="c">Nível</th>'
            '<th class="c">Aposta</th><th class="c">Investido</th><th class="c">Ganho se acertar</th></tr>'
            + "".join(linhas) + "</table></div></div>")


def pagina_simulador(por_mesa, limites):
    st.markdown(CSS, unsafe_allow_html=True)
    sessao = st.session_state.get("ao_vivo")
    rodando = bool(sessao and sessao["rodando"])

    c1, c2 = st.columns([1, 2])
    mesa = c1.selectbox("Roleta", sorted(por_mesa), key="sim_mesa", disabled=rodando)
    categorias = c2.multiselect(
        "Apostar em", list(CATEGORIAS), default=["Vermelho"], key="sim_categorias", disabled=rodando,
        placeholder="Escolha um ou mais padrões",
        help="Pode escolher vários ao mesmo tempo (ex.: Par + Vermelho + Alto). Cada um tem seu próprio gatilho "
             "e recuperação, e todos usam o mesmo caixa.",
    )
    padroes_usados = list(dict.fromkeys(CATEGORIAS[c] for c in categorias))

    limite = limites.get(mesa)
    max_niveis = min((niveis_tabela(p) for p in padroes_usados), default=niveis_tabela("Vermelho / Preto")) - 1
    d1, d2, d3, d4 = st.columns(4)
    gatilho = d1.number_input("Gatilho", min_value=0, max_value=50, value=5, step=1, key="sim_gatilho", disabled=rodando,
                              help="Cada padrão entra quando completar esse número de rodadas seguidas sem sair. 0 = aposta direta: aposta desde o Start e continua apostando, mesmo depois de ganhar ou estourar.")
    ficha = d2.number_input("Ficha inicial (R$)", min_value=0.10, max_value=10000.0, disabled=rodando,
                            value=float(limite["min"]) if limite else 0.50, step=0.50, format="%.2f", key=f"sim_ficha_{mesa}")
    max_rec = d3.number_input("Máx. recuperações", min_value=0, max_value=max_niveis, value=min(3, max_niveis), step=1,
                              key="sim_rec", disabled=rodando,
                              help="Até qual nível da sua tabela de recuperação cada padrão vai")
    banca = d4.number_input("Banca inicial (R$)", min_value=1.0, max_value=1_000_000.0, value=100.0, step=10.0,
                            format="%.2f", key="sim_banca", disabled=rodando)

    if not categorias:
        aviso("Escolha pelo menos um padrão em <b>Apostar em</b>.")
        return

    fichas_por_padrao = {p: sequencia_da_tabela(p, ficha, int(max_rec)) for p in padroes_usados}
    risco_cada = {c: sum(fichas_por_padrao[CATEGORIAS[c]]) for c in categorias}
    risco_total = sum(risco_cada.values())
    texto_risco = f"Valor em risco por ciclo: <b>{reais(risco_total)}</b>"
    if len(categorias) > 1:
        texto_risco += " — se todos estiverem em ciclo ao mesmo tempo (" + " + ".join(
            f"{escape(c)} {reais(v)}" for c, v in risco_cada.items()) + ")"
    st.markdown(f'<p class="fichas">{texto_risco}</p>', unsafe_allow_html=True)

    with st.expander("Ver todos os níveis do ciclo"):
        tipos = {}  # uma tabela por tipo de aposta (1:1 ou dúzia/coluna)
        for p in padroes_usados:
            tipos.setdefault(PAGAMENTO[p], p)
        for pagamento, p in sorted(tipos.items()):
            if len(tipos) > 1:
                st.markdown("**Dúzias e Colunas**" if pagamento == 2 else "**Cor, Par/Ímpar e Alto/Baixo**")
            st.markdown(tabela_niveis(fichas_por_padrao[p], p), unsafe_allow_html=True)

    maior_ficha = max(f[-1] for f in fichas_por_padrao.values())
    if limite and ficha < limite["min"]:
        alerta(f"A ficha inicial está abaixo do mínimo desta mesa ({formatar_limite(limite)}).")
    if limite and maior_ficha > limite["max"]:
        alerta(f"A última recuperação ({reais(maior_ficha)}) passa do máximo desta mesa ({formatar_limite(limite)}).")
    if risco_total > banca:
        alerta(f"Os ciclos completos somam {reais(risco_total)}, mais que a banca inicial ({reais(banca)}).")

    b1, b2, _ = st.columns([1, 1, 4])
    if not rodando:
        if b1.button("▶ Start", key="sim_start", use_container_width=True):
            try:
                anteriores = giros_recentes(mesa)
            except Exception as erro:
                st.error(f"Não foi possível ler a mesa agora ({erro}). Tente de novo em alguns segundos.")
                return
            sim = SimulacaoAoVivo(categorias, int(gatilho), fichas_por_padrao, banca,
                                  limite_max=limite["max"] if limite else None)
            sim.aquecer([(t, n) for t, n, _ in anteriores])
            st.session_state.ao_vivo = {
                "sim": sim, "mesa": mesa, "inicio": datetime.now(timezone.utc), "fim": None, "rodando": True,
                "vistos": {i for _, _, i in anteriores},  # ids dos giros já considerados
                "ultimo_giro": anteriores[-1][:2] if anteriores else None, "erro": None,
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
        aviso("Configure a estratégia e aperte <b>Start</b>. A simulação acompanha os giros reais da mesa a partir desse "
              "momento, sem fazer apostas de verdade. Mantenha esta aba aberta enquanto ela roda.")


@st.fragment(run_every=1)
def painel_ao_vivo():
    sessao = st.session_state.get("ao_vivo")
    if not sessao:
        return
    sim = sessao["sim"]

    if sessao["rodando"]:
        try:
            for horario, numero, id_giro in giros_recentes(sessao["mesa"]):
                if id_giro not in sessao["vistos"]:
                    sessao["vistos"].add(id_giro)
                    sim.processar(horario, numero)
                    sessao["ultimo_giro"] = (horario, numero)
            sessao["erro"] = None
        except Exception as erro:
            sessao["erro"] = str(erro)
        if sim.quebrou:
            sessao["rodando"], sessao["fim"] = False, datetime.now(timezone.utc)

    # Painel: cronômetro + situação de cada padrão
    fim = sessao["fim"] or datetime.now(timezone.utc)
    decorrido = (fim - sessao["inicio"]).total_seconds()
    ponto = '<span class="ponto-vivo"></span>Jogando' if sessao["rodando"] else '<span class="ponto-parado"></span>Parado'
    ultimo = sessao["ultimo_giro"]
    detalhe = f"{escape(sessao['mesa'])} · {sim.giros_vistos} giros desde o Start"
    if ultimo:
        detalhe += f" · último: {cor_numero(ultimo[1])} às {ultimo[0].astimezone(FUSO_BRASILIA):%H:%M:%S}"
    if sessao.get("erro"):
        detalhe += " · ⚠ falha ao ler a mesa, tentando de novo"
    robos = "".join(f'<div class="robo"><b>{escape(r.categoria)}</b> — {escape(sim.status(r))}</div>' for r in sim.robos)
    st.markdown(
        f'<div class="painel"><div class="cronometro">{cronometro(decorrido)}</div>'
        f'<div class="estado">{ponto}<small>{detalhe}</small>{robos}</div></div>',
        unsafe_allow_html=True,
    )

    # Blocos de resumo
    r = sim.resumo
    lucro = sim.saldo - sim.banca
    total_ganho = sum(h["lucro"] for h in sim.historico if h["resultado"] == "Ganhou")
    ganhas = f"ganhou {reais(total_ganho)}"
    estouros = f"{r['estouros']} estouro" + ("" if r["estouros"] == 1 else "s")
    maior = max(sim.robos, key=lambda x: x.max_sem_sair)
    detalhe_max = (" · ".join(f"{x.categoria} {x.max_sem_sair}" for x in sim.robos) if len(sim.robos) > 1
                   else f"maior sequência sem {maior.categoria} desde o Start")
    tiles = [
        ("Saldo inicial", reais(sim.banca), "banca no Start", False),
        ("Saldo final", reais(sim.saldo), f"{'lucro' if lucro > 0 else 'prejuízo' if lucro < 0 else 'resultado'}: "
                                          f"{reais(lucro, sinal=True)}", True),
        ("Entradas", str(r["entradas"]), f"{ganhas} · {estouros}", False),
        ("Máx. sem sair", str(maior.max_sem_sair), detalhe_max, False),
    ]
    st.markdown(
        '<div class="tiles">' + "".join(
            f'<div class="tile{" destaque" if d else ""}"><div class="rotulo">{escape(a)}</div>'
            f'<div class="valor">{escape(b)}</div><div class="detalhe">{escape(c)}</div></div>'
            for a, b, c, d in tiles
        ) + "</div>",
        unsafe_allow_html=True,
    )

    # Histórico ao vivo: uma linha por aposta resolvida, mais recentes primeiro
    st.markdown('<p class="secao">Histórico ao vivo <span>· mais recentes primeiro</span></p>', unsafe_allow_html=True)
    if not sim.historico:
        aviso("Nenhuma aposta resolvida ainda. Elas aparecem aqui assim que um gatilho for atingido e o próximo giro sair.")
        return
    linhas = []
    for h in reversed(sim.historico[-200:]):
        nivel = "—" if h["nivel"] is None else ("Entrada" if h["nivel"] == 0 else f"Recuperação {h['nivel']}")
        classe = "ganhou" if h["lucro"] > 0 else "perdeu" if h["lucro"] < 0 else ""
        linhas.append(
            f"<tr><td>{h['horario'].astimezone(FUSO_BRASILIA):%H:%M:%S}</td><td class='c'>{cor_numero(h['numero'])}</td>"
            f"<td>{escape(h['categoria'])}</td><td class='c'>{reais(h['aposta']) if h['aposta'] else '—'}</td>"
            f"<td>{nivel}</td><td class='{classe}'>{escape(h['resultado'])}</td>"
            f"<td class='c {classe}'>{reais(h['lucro'], sinal=True)}</td><td class='c'><b>{reais(h['caixa'])}</b></td></tr>"
        )
    st.markdown(
        '<div class="card ranking historico"><div class="rolagem"><table><tr><th>Horário</th><th class="c">Número</th>'
        '<th>Aposta em</th><th class="c">Valor</th><th>Nível</th><th>Resultado</th><th class="c">Lucro</th>'
        '<th class="c">Caixa</th></tr>' + "".join(linhas) + "</table></div></div>",
        unsafe_allow_html=True,
    )
