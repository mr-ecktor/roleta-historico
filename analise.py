"""
Motor de análise: conta por quantas rodadas seguidas cada padrão ficou SEM SAIR.

Regras:
- O zero conta como "não saiu" para todos os padrões.
- Só entram na contagem ausências completas (que terminaram quando o padrão voltou a sair).
  A ausência ainda em andamento é informada à parte.
- Se houver uma falha na coleta (intervalo grande entre duas rodadas), a contagem
  recomeça, para não emendar rodadas que não foram registradas.
"""

import csv
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from coletor import ARQUIVO_LIMITES, MESAS_ATIVAS

# Nomes usados nos CSVs antigos -> nome atual
NOMES_ANTIGOS = {"Auto Roulette": "Auto Roulette (Evolution)"}

# Limites de aposta das mesas Evolution (não há fonte pública; valores do painel "Limites" do cassino).
# Formato: "Nome da mesa": {"min": 0.5, "max": 25000, "moeda": "BRL"}
LIMITES_MANUAIS = {}

PASTA_DADOS = Path(__file__).parent / "dados"
FUSO_BRASILIA = timezone(timedelta(hours=-3))
INTERVALO_MAXIMO = timedelta(minutes=10)  # acima disso consideramos falha na coleta

VERMELHOS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}

PADROES = {
    "Vermelho / Preto": {
        "Vermelho": lambda n: n in VERMELHOS,
        "Preto": lambda n: n != 0 and n not in VERMELHOS,
    },
    "Par / Ímpar": {
        "Par": lambda n: n != 0 and n % 2 == 0,
        "Ímpar": lambda n: n % 2 == 1,
    },
    "Baixo / Alto": {
        "Baixo (1-18)": lambda n: 1 <= n <= 18,
        "Alto (19-36)": lambda n: n >= 19,
    },
    "Dúzias": {
        "1ª dúzia (1-12)": lambda n: 1 <= n <= 12,
        "2ª dúzia (13-24)": lambda n: 13 <= n <= 24,
        "3ª dúzia (25-36)": lambda n: n >= 25,
    },
    "Colunas": {
        "1ª coluna": lambda n: n != 0 and n % 3 == 1,
        "2ª coluna": lambda n: n != 0 and n % 3 == 2,
        "3ª coluna": lambda n: n != 0 and n % 3 == 0,
    },
}

PERIODOS = {
    "Última 1 hora": timedelta(hours=1),
    "Último 1 dia": timedelta(days=1),
    "Últimos 15 dias": timedelta(days=15),
    "Último 1 mês": timedelta(days=30),
    "Tudo": None,
}


def carregar_giros(pasta=PASTA_DADOS):
    """Lê todos os CSVs e devolve {mesa: [(horario_utc, numero), ...]} em ordem cronológica.
    Só inclui as mesas que o coletor ainda monitora."""
    mesas_ativas = set(MESAS_ATIVAS)
    por_mesa = {}
    vistos = set()
    for arquivo in sorted(Path(pasta).rglob("*.csv")):
        with open(arquivo, newline="", encoding="utf-8") as f:
            for linha in csv.DictReader(f):
                mesa = NOMES_ANTIGOS.get(linha["mesa"], linha["mesa"])
                if mesa not in mesas_ativas or linha["id"] in vistos:
                    continue
                vistos.add(linha["id"])
                horario = datetime.fromisoformat(linha["finalizado_utc"].replace("Z", "+00:00"))
                por_mesa.setdefault(mesa, []).append((horario, int(linha["numero"])))
    for giros in por_mesa.values():
        giros.sort()
    return por_mesa


def carregar_limites():
    """{mesa: {"min", "max", "moeda"}} — automáticos (Pragmatic) + manuais (Evolution)."""
    limites = {}
    if ARQUIVO_LIMITES.exists():
        limites = json.loads(ARQUIVO_LIMITES.read_text(encoding="utf-8"))
    return {**limites, **LIMITES_MANUAIS}


def formatar_limite(lim):
    """Ex.: {"min": 0.5, "max": 25000} -> "R$ 0,50 – 25.000"."""
    def reais(v):
        texto = f"{v:,.2f}" if v % 1 else f"{v:,.0f}"
        return texto.replace(",", "X").replace(".", ",").replace("X", ".")
    simbolo = "R$ " if lim.get("moeda", "BRL") == "BRL" else f'{lim["moeda"]} '
    return f'{simbolo}{reais(lim["min"])} – {reais(lim["max"])}'


def filtrar_periodo(giros, periodo, agora=None):
    duracao = PERIODOS[periodo]
    if duracao is None:
        return giros
    agora = agora or datetime.now(timezone.utc)
    inicio = agora - duracao
    return [g for g in giros if g[0] >= inicio]


def dividir_em_trechos(giros):
    """Separa os giros em trechos contínuos (sem falhas de coleta)."""
    trechos, atual = [], []
    for g in giros:
        if atual and g[0] - atual[-1][0] > INTERVALO_MAXIMO:
            trechos.append(atual)
            atual = []
        atual.append(g)
    if atual:
        trechos.append(atual)
    return trechos


def esperado(tamanhos_trechos, p, k, ou_mais=False):
    """
    Quantas ausências de exatamente k rodadas (ou k ou mais) a matemática prevê.
    Uma ausência completa de j rodadas = saiu, j rodadas sem sair, saiu de novo:
    probabilidade p * (1-p)^j * p, em (n - j - 1) posições possíveis de cada trecho.
    """
    q = 1 - p
    total = 0.0
    for n in tamanhos_trechos:
        limite = n - 2 if ou_mais else k
        for j in range(k, limite + 1):
            if n - j - 1 > 0:
                total += (n - j - 1) * p * p * q ** j
    return total


def analisar(giros, padrao):
    """
    Devolve, para cada categoria do padrão:
      - contagem: Counter {tamanho_da_ausencia: vezes}
      - atual: rodadas sem sair no momento (ausência em andamento, se o último trecho chega até o fim)
      - probabilidade: chance de sair em cada rodada
    """
    categorias = PADROES[padrao]
    trechos = dividir_em_trechos(giros)
    tamanhos = [len(t) for t in trechos]
    resultado = {}
    for nome, saiu in categorias.items():
        contagem = Counter()
        atual = None
        for trecho in trechos:
            sem_sair = None  # None = ainda não vimos o padrão sair neste trecho (início desconhecido)
            for _, numero in trecho:
                if saiu(numero):
                    if sem_sair:  # ausência completa (> 0 rodadas)
                        contagem[sem_sair] += 1
                    sem_sair = 0
                elif sem_sair is not None:
                    sem_sair += 1
            atual = sem_sair
        probabilidade = sum(1 for n in range(37) if saiu(n)) / 37
        resultado[nome] = {
            "contagem": contagem,
            "atual": atual,
            "probabilidade": probabilidade,
        }
    return resultado, tamanhos


def tabela(resultado_categoria, tamanhos):
    """Linhas: (rodadas sem sair, exatamente, esperado exatamente, X ou mais, esperado X ou mais)."""
    contagem = resultado_categoria["contagem"]
    p = resultado_categoria["probabilidade"]
    if not contagem:
        return []
    maior = max(contagem)
    linhas = []
    acumulado = 0
    ou_mais = {}
    for k in range(maior, 0, -1):
        acumulado += contagem.get(k, 0)
        ou_mais[k] = acumulado
    for k in range(1, maior + 1):
        linhas.append((
            k,
            contagem.get(k, 0),
            esperado(tamanhos, p, k),
            ou_mais[k],
            esperado(tamanhos, p, k, ou_mais=True),
        ))
    return linhas


if __name__ == "__main__":
    # Teste rápido pelo terminal
    dados = carregar_giros()
    mesa = "Lightning Roulette"
    giros = filtrar_periodo(dados[mesa], "Tudo")
    res, tamanhos = analisar(giros, "Vermelho / Preto")
    print(f"{mesa}: {len(giros)} giros em {len(tamanhos)} trecho(s)\n")
    for nome, r in res.items():
        print(f"{nome} sem sair (agora: {r['atual']} rodadas)")
        print(f"  {'Rodadas':>7} | {'Exato':>5} {'Esper.':>6} | {'X+':>4} {'Esper.':>6}")
        for k, exato, esp, mais, esp_mais in tabela(r, tamanhos):
            print(f"  {k:>7} | {exato:>5} {esp:>6.1f} | {mais:>4} {esp_mais:>6.1f}")
        print()
