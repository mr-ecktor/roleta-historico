"""Tela do Simulador (botão "Simulador" do site)."""

from html import escape

import altair as alt
import pandas as pd
import streamlit as st

from analise import FUSO_BRASILIA, PADROES, PERIODOS, filtrar_periodo, formatar_limite
from simulador import (PAGAMENTO, VANTAGEM_DA_CASA, niveis_tabela, sequencia_da_tabela,
                       sequencia_de_fichas, simular)

COR_LINHA = "#f25c00"  # laranja da marca ajustado para a faixa de luminosidade do modo escuro (validado)
COR_REFERENCIA = "#71717a"
# Rótulo do eixo em reais no formato brasileiro (1.234,50)
EIXO_REAIS = "'R$ ' + replace(replace(replace(format(datum.value, ',.2f'), ',', '#'), '.', ','), '#', '.')"


def reais(v, sinal=False):
    texto = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if sinal:
        return ("+" if v > 0 else "−" if v < 0 else "") + f"R$ {texto}"
    return ("−" if v < 0 else "") + f"R$ {texto}"


CSS = """
<style>
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: .8rem; margin: .4rem 0 1.2rem; }
.tile { background: var(--fundo-card); border: 1px solid var(--borda); border-radius: 14px; padding: .9rem 1.1rem; }
.tile .rotulo { font-family: 'Sora', sans-serif; font-size: .68rem; font-weight: 600; letter-spacing: .14em; text-transform: uppercase; color: #71717a; }
.tile .valor { font-family: 'Sora', sans-serif; font-size: 1.45rem; font-weight: 700; color: #fafafa; margin-top: .25rem; font-variant-numeric: tabular-nums; }
.tile .detalhe { font-size: .8rem; color: var(--texto-2); margin-top: .15rem; }
.tile.destaque { border-color: rgba(242, 92, 0, .55); }
.stNumberInput label p { font-family: 'Sora', sans-serif; font-size: .72rem !important; font-weight: 600;
    letter-spacing: .14em; text-transform: uppercase; color: var(--texto-2); }
.stNumberInput input { background: rgba(22, 22, 26, .9) !important; }
.fichas { font-size: .9rem; color: var(--texto-2); margin: -.2rem 0 1rem; }
.fichas b { color: #fafafa; font-variant-numeric: tabular-nums; }
.nota { background: var(--fundo-card); border: 1px solid var(--borda); border-left: 3px solid #71717a;
        border-radius: 12px; padding: .8rem 1.1rem; font-size: .88rem; color: var(--texto-2); margin: 1rem 0; }
.nota b { color: #fafafa; }
</style>
"""


def grafico_saldo(evolucao, banca):
    df = pd.DataFrame(
        [(t.astimezone(FUSO_BRASILIA).replace(tzinfo=None), s) for t, s in evolucao],
        columns=["Horário", "Saldo"],
    )
    base = alt.Chart(df).encode(
        x=alt.X("Horário:T", title=None, axis=alt.Axis(format="%d/%m %H:%M", labelColor="#a1a1aa", grid=False,
                                                        domainColor="#3f3f46", tickColor="#3f3f46")),
    )
    linha = base.mark_line(color=COR_LINHA, strokeWidth=2, interpolate="step-after").encode(
        y=alt.Y("Saldo:Q", title=None, scale=alt.Scale(zero=False),
                axis=alt.Axis(labelColor="#a1a1aa", gridColor="#26262c", domain=False, ticks=False,
                              labelExpr=EIXO_REAIS)),
    )
    referencia = alt.Chart(pd.DataFrame({"Saldo": [banca]})).mark_rule(
        color=COR_REFERENCIA, strokeDash=[4, 4], strokeWidth=1,
    ).encode(y="Saldo:Q")
    # crosshair + dica ao passar o mouse
    perto = alt.selection_point(nearest=True, on="pointerover", fields=["Horário"], empty=False)
    alvo = base.mark_point(opacity=0, size=400).encode(y="Saldo:Q").add_params(perto)
    ponto = base.mark_point(color=COR_LINHA, filled=True, size=70, stroke="#09090b", strokeWidth=2).encode(
        y="Saldo:Q",
        opacity=alt.condition(perto, alt.value(1), alt.value(0)),
        tooltip=[alt.Tooltip("Horário:T", format="%d/%m %H:%M:%S"), alt.Tooltip("Saldo:Q", format=",.2f", title="Saldo (R$)")],
    )
    regua = base.mark_rule(color="#52525b", strokeWidth=1).encode(
        opacity=alt.condition(perto, alt.value(1), alt.value(0)),
    )
    return (
        alt.layer(referencia, linha, regua, alvo, ponto)
        .properties(height=320, background="transparent")
        .configure_view(stroke=None)
    )


def pagina_simulador(por_mesa, limites):
    st.markdown(CSS, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    mesa = c1.selectbox("Roleta", sorted(por_mesa), key="sim_mesa")
    padrao = c2.selectbox("Padrão", list(PADROES), key="sim_padrao")
    categoria = c3.selectbox("Apostar em", list(PADROES[padrao]), key=f"sim_cat_{padrao}")
    periodo = c4.selectbox("Período", list(PERIODOS), index=1, key="sim_periodo")

    limite = limites.get(mesa)
    tres_opcoes = len(PADROES[padrao]) == 3
    d1, d2, d3, d4, d5, d6 = st.columns(6)
    gatilho = d1.number_input("Gatilho (sem sair)", help="Entra quando a categoria completar esse número de rodadas seguidas sem sair", min_value=0, max_value=50, value=5, step=1, key="sim_gatilho")
    ficha = d2.number_input("Ficha inicial (R$)", min_value=0.10, max_value=10000.0,
                            value=float(limite["min"]) if limite else 0.50, step=0.50, format="%.2f", key=f"sim_ficha_{mesa}")
    tipo = d3.selectbox("Recuperação", ["Minha tabela", "Multiplicador"], key="sim_tipo")
    usa_tabela = tipo == "Minha tabela"
    multiplicador = d4.number_input("Multiplicador", min_value=1.0, max_value=5.0, disabled=usa_tabela,
                                    value=1.5 if tres_opcoes else 2.0, step=0.1, format="%.1f", key=f"sim_mult_{padrao}")
    max_permitido = niveis_tabela(padrao) - 1 if usa_tabela else 15
    max_rec = d5.number_input("Máx. recuperações", min_value=0, max_value=max_permitido,
                              value=min(3, max_permitido), step=1, key=f"sim_rec_{padrao}_{tipo}")
    banca = d6.number_input("Banca inicial (R$)", min_value=1.0, max_value=1_000_000.0, value=100.0, step=10.0,
                            format="%.2f", key="sim_banca")

    if usa_tabela:
        fichas = sequencia_da_tabela(padrao, ficha, int(max_rec))
    else:
        fichas = sequencia_de_fichas(ficha, multiplicador, int(max_rec))
    risco = sum(fichas)
    mostrar = fichas if len(fichas) <= 8 else fichas[:6] + [None] + fichas[-1:]
    st.markdown(
        '<p class="fichas">Fichas do ciclo: <b>' + " → ".join("…" if f is None else reais(f) for f in mostrar) + "</b>"
        f" · em risco por ciclo: <b>{reais(risco)}</b>"
        f" · ganho se acertar na 1ª: <b>{reais(fichas[0] * PAGAMENTO[padrao])}</b></p>",
        unsafe_allow_html=True,
    )
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

    giros = filtrar_periodo(por_mesa[mesa], periodo)
    if len(giros) < 2:
        st.info("Poucas rodadas registradas nesse período para simular.")
        return

    r = simular(giros, padrao, categoria, int(gatilho), fichas, banca,
                limite_max=limite["max"] if limite else None)

    rotulo_resultado = "Lucro" if r["lucro"] > 0 else "Prejuízo" if r["lucro"] < 0 else "Resultado"
    taxa = f"{100 * r['vitorias'] / r['entradas']:.1f}% de acerto".replace(".", ",") if r["entradas"] else "nenhuma entrada"
    estouros = f"{r['estouros']} estouro" + ("" if r["estouros"] == 1 else "s")
    ganhas = f"{r['vitorias']} ganha" + ("" if r["vitorias"] == 1 else "s")
    tiles = [
        ("Saldo final", reais(r["saldo_final"]), "banca quebrou" if r["quebrou"] else f"banca inicial {reais(banca)}", True),
        (rotulo_resultado, reais(r["lucro"], sinal=True), f"esperado pela matemática: {reais(r['esperado'], sinal=True)}", False),
        ("Entradas", str(r["entradas"]), f"{ganhas} · {estouros} · {taxa}", False),
        ("Maior queda", reais(-r["maior_queda"]) if r["maior_queda"] else reais(0), f"menor saldo: {reais(r['menor_saldo'])}", False),
        ("Total apostado", reais(r["total_apostado"]), f"{len(giros):,} rodadas no período".replace(",", "."), False),
    ]
    st.markdown(
        '<div class="tiles">' + "".join(
            f'<div class="tile{" destaque" if d else ""}"><div class="rotulo">{escape(a)}</div>'
            f'<div class="valor">{escape(b)}</div><div class="detalhe">{escape(c)}</div></div>'
            for a, b, c, d in tiles
        ) + "</div>",
        unsafe_allow_html=True,
    )

    if len(r["evolucao"]) > 1:
        st.markdown('<p class="secao">Saldo ao longo do tempo <span>· linha tracejada = banca inicial</span></p>',
                    unsafe_allow_html=True)
        st.altair_chart(grafico_saldo(r["evolucao"], banca), use_container_width=True)

    st.markdown(
        f'<div class="nota">Pela matemática, cada aposta perde em média <b>{f"{VANTAGEM_DA_CASA:.1%}".replace(".", ",")}</b> do valor apostado — '
        f'para os <b>{reais(r["total_apostado"])}</b> apostados aqui, o esperado seria <b>{reais(r["esperado"], sinal=True)}</b>. '
        'A recuperação não muda isso: troca muitos ganhos pequenos por perdas grandes ocasionais. '
        'Um resultado positivo num período curto é sorte da amostra, não vantagem — teste em vários dias e mesas.</div>',
        unsafe_allow_html=True,
    )

    if r["ciclos"]:
        linhas = []
        for c in reversed(r["ciclos"][-40:]):
            gales = c["nivel"]
            linhas.append(
                f"<tr><td>{c['inicio'].astimezone(FUSO_BRASILIA):%d/%m %H:%M:%S}</td>"
                f"<td class='c'>{gales}</td><td>{escape(c['resultado'])}</td>"
                f"<td class='c'>{escape(reais(c['maior_aposta']))}</td>"
                f"<td class='c'>{escape(reais(c['lucro'], sinal=True))}</td></tr>"
            )
        st.markdown(
            '<p class="secao">Últimas entradas <span>· mais recentes primeiro</span></p>'
            '<div class="card ranking"><div class="rolagem"><table><tr><th>Início</th><th class="c">Recuperações</th>'
            '<th>Resultado</th><th class="c">Maior aposta</th><th class="c">Lucro do ciclo</th></tr>'
            + "".join(linhas) + "</table></div></div>",
            unsafe_allow_html=True,
        )
