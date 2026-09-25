"""
Simulador de estratégia com recuperação, usando os giros reais coletados.

Regra simulada:
- Espera a categoria escolhida ficar X rodadas seguidas sem sair (gatilho) e aposta na próxima.
- Ganhou: o ciclo termina com lucro. Perdeu: a próxima aposta é a anterior x multiplicador,
  até o máximo de recuperações. Se perder todas, o ciclo "estoura".
- Depois de um estouro, só volta a entrar quando a categoria sair de novo e completar
  outro gatilho.
- O zero perde todas as apostas externas (cor, par/ímpar, alto/baixo, dúzia, coluna).
- Numa interrupção da coleta (giro faltando ou pausa), o ciclo em andamento é encerrado
  como "interrompido", porque não se sabe o que aconteceu no meio.
"""

from analise import PADROES, dividir_em_trechos

# Lucro por real apostado quando ganha
PAGAMENTO = {
    "Vermelho / Preto": 1,
    "Par / Ímpar": 1,
    "Baixo / Alto": 1,
    "Dúzias": 2,
    "Colunas": 2,
}
VANTAGEM_DA_CASA = 1 / 37  # roleta europeia: 2,7% de tudo o que é apostado


# Tabela de recuperação do usuário para dúzias e colunas (valores para ficha de R$ 0,50)
TABELA_DUZIAS_COLUNAS = [
    0.50, 1.00, 1.50, 2.50, 4.00, 6.00, 10.00, 15.00, 25.00, 40.00, 60.00, 90.00,
    140.00, 210.00, 320.00, 480.00, 725.00, 1090.00, 1635.00, 2455.00, 3685.00, 5530.00, 8300.00, 12450.00,
]
NIVEIS_TABELA_SIMPLES = 16  # tamanho da tabela do usuário para cor, par/ímpar e alto/baixo


def niveis_tabela(padrao):
    return len(TABELA_DUZIAS_COLUNAS) if PAGAMENTO[padrao] == 2 else NIVEIS_TABELA_SIMPLES


def sequencia_de_fichas(ficha, multiplicador, max_recuperacoes):
    fichas = [round(ficha, 2)]
    for _ in range(max_recuperacoes):
        fichas.append(round(fichas[-1] * multiplicador, 2))
    return fichas


def sequencia_da_tabela(padrao, ficha, max_recuperacoes):
    """
    Tabela de recuperação do usuário:
    - Apostas 1:1 (cor, par/ímpar, alto/baixo): próxima = 2 x anterior + ficha
      (0,50 → 1,50 → 3,50 → 7,50 ...), cada nível ganha uma ficha a mais que o anterior.
    - Dúzias e colunas: sequência fixa da planilha, proporcional à ficha inicial.
    """
    niveis = min(max_recuperacoes + 1, niveis_tabela(padrao))
    if PAGAMENTO[padrao] == 2:
        escala = ficha / TABELA_DUZIAS_COLUNAS[0]
        return [round(v * escala, 2) for v in TABELA_DUZIAS_COLUNAS[:niveis]]
    fichas = [round(ficha, 2)]
    while len(fichas) < niveis:
        fichas.append(round(2 * fichas[-1] + ficha, 2))
    return fichas


def simular(giros, padrao, categoria, gatilho, fichas, banca, limite_max=None):
    """fichas: valor de cada aposta do ciclo (1ª entrada + recuperações)."""
    saiu = PADROES[padrao][categoria]
    pagamento = PAGAMENTO[padrao]
    max_recuperacoes = len(fichas) - 1

    saldo = banca
    evolucao = [(giros[0][0], saldo)] if giros else []
    ciclos = []
    total_apostado = 0.0
    quebrou = False

    for trecho in dividir_em_trechos(giros):
        sem_sair = None  # desconhecido no início do trecho
        aguardar_saida = False
        ciclo = None  # {"inicio", "nivel", "lucro", "maior_aposta"}

        for horario, numero in trecho:
            acertou = saiu(numero)

            if ciclo is not None:
                aposta = fichas[ciclo["nivel"]]
                total_apostado += aposta
                ciclo["maior_aposta"] = aposta
                if acertou:
                    ganho = aposta * pagamento
                    saldo += ganho
                    ciclo["lucro"] += ganho
                    ciclos.append({**ciclo, "fim": horario, "resultado": "Ganhou"})
                    ciclo = None
                else:
                    saldo -= aposta
                    ciclo["lucro"] -= aposta
                    proximo = ciclo["nivel"] + 1
                    if proximo > max_recuperacoes:
                        ciclos.append({**ciclo, "fim": horario, "resultado": "Estourou"})
                        ciclo = None
                        aguardar_saida = True
                    elif limite_max is not None and fichas[proximo] > limite_max:
                        ciclos.append({**ciclo, "fim": horario, "resultado": "Limite da mesa"})
                        ciclo = None
                        aguardar_saida = True
                    else:
                        ciclo["nivel"] = proximo
                evolucao.append((horario, round(saldo, 2)))

            # atualiza a contagem de rodadas sem sair
            if acertou:
                sem_sair = 0
                aguardar_saida = False
            elif sem_sair is not None:
                sem_sair += 1

            # próxima aposta: continua o ciclo ou entra pelo gatilho
            # gatilho 0 = aposta direta: entra em todo giro em que não houver ciclo aberto
            if ciclo is None and (gatilho == 0 or (not aguardar_saida and sem_sair == gatilho)):
                ciclo = {"inicio": horario, "nivel": 0, "lucro": 0.0, "maior_aposta": 0.0}

            if ciclo is not None and fichas[ciclo["nivel"]] > saldo + 1e-9:
                ciclos.append({**ciclo, "fim": horario, "resultado": "Banca insuficiente"})
                quebrou = True
                break

        if quebrou:
            break
        if ciclo is not None and ciclo["maior_aposta"] > 0:
            ciclos.append({**ciclo, "fim": trecho[-1][0], "resultado": "Interrompido"})

    # maior queda do saldo em relação ao pico anterior
    pico, maior_queda = banca, 0.0
    for _, s in evolucao:
        pico = max(pico, s)
        maior_queda = max(maior_queda, pico - s)

    resultados = [c["resultado"] for c in ciclos]
    return {
        "saldo_final": round(saldo, 2),
        "lucro": round(saldo - banca, 2),
        "evolucao": evolucao,
        "ciclos": ciclos,
        "entradas": len(ciclos),
        "vitorias": resultados.count("Ganhou"),
        "estouros": resultados.count("Estourou") + resultados.count("Limite da mesa"),
        "total_apostado": round(total_apostado, 2),
        "maior_queda": round(maior_queda, 2),
        "menor_saldo": round(min((s for _, s in evolucao), default=banca), 2),
        "quebrou": quebrou,
        "esperado": round(-total_apostado * VANTAGEM_DA_CASA, 2),
        "fichas": fichas,
    }


# Todas as categorias apostáveis: rótulo -> padrão a que pertence
CATEGORIAS = {cat: padrao for padrao, cats in PADROES.items() for cat in cats}


class _Robo:
    """Uma categoria apostada (ex.: "Par"), com gatilho, ciclo e recuperação próprios."""

    def __init__(self, categoria, fichas, gatilho):
        self.categoria = categoria
        self.gatilho = gatilho
        self.padrao = CATEGORIAS[categoria]
        self.saiu = PADROES[self.padrao][categoria]
        self.fichas = fichas
        self.sem_sair = None
        self.aguardar_saida = False
        self.ciclo = None  # {"inicio", "nivel", "lucro"}
        self.max_sem_sair = 0
        self.entradas = self.vitorias = self.estouros = 0

    @property
    def aposta_atual(self):
        return self.fichas[self.ciclo["nivel"]] if self.ciclo else 0.0


class SimulacaoAoVivo:
    """
    Simula um ou mais robôs (um por categoria escolhida) giro a giro, conforme os giros chegam ao vivo,
    todos usando o mesmo caixa. Guardada no session_state do site enquanto a página estiver aberta.
    """

    INTERVALO_MAXIMO_S = 180  # sem giro novo por mais que isso = pausa da mesa: ciclos em andamento são encerrados

    def __init__(self, categorias, gatilhos, fichas_por_padrao, banca, limite_max=None):
        """gatilhos: um número para todos, ou {categoria: número}."""
        if not isinstance(gatilhos, dict):
            gatilhos = {c: gatilhos for c in categorias}
        self.robos = [_Robo(c, fichas_por_padrao[CATEGORIAS[c]], gatilhos[c]) for c in categorias]
        self.banca, self.limite_max = banca, limite_max
        self.saldo = banca
        self.historico = []  # uma linha por aposta resolvida
        self.ultimo_horario = None
        self.giros_vistos = 0
        self.quebrou = False

    # ---------------------------------------------------------------- giros
    def aquecer(self, giros):
        """Usa giros anteriores ao Start só para saber há quantas rodadas cada categoria está sem sair."""
        for horario, numero in giros:
            pausa = self.ultimo_horario and (horario - self.ultimo_horario).total_seconds() > self.INTERVALO_MAXIMO_S
            for robo in self.robos:
                if pausa:
                    robo.sem_sair = None
                robo.sem_sair = 0 if robo.saiu(numero) else (None if robo.sem_sair is None else robo.sem_sair + 1)
            self.ultimo_horario = horario
        self._preparar_apostas(self.ultimo_horario)

    def processar(self, horario, numero):
        if self.quebrou:
            return
        if self.ultimo_horario and (horario - self.ultimo_horario).total_seconds() > self.INTERVALO_MAXIMO_S:
            for robo in self.robos:
                if robo.ciclo:
                    self._registrar(horario, None, robo, 0.0, 0.0, "Interrompido (pausa da mesa)")
                robo.ciclo, robo.sem_sair, robo.aguardar_saida = None, None, False
        self.ultimo_horario = horario
        self.giros_vistos += 1

        for robo in self.robos:
            acertou = robo.saiu(numero)
            if robo.ciclo is not None:
                nivel = robo.ciclo["nivel"]
                aposta = robo.fichas[nivel]
                if acertou:
                    ganho = aposta * PAGAMENTO[robo.padrao]
                    self.saldo += ganho
                    robo.ciclo["lucro"] += ganho
                    robo.vitorias += 1
                    self._registrar(horario, numero, robo, aposta, ganho, "Ganhou", nivel)
                    robo.ciclo = None
                else:
                    self.saldo -= aposta
                    robo.ciclo["lucro"] -= aposta
                    proximo = nivel + 1
                    if proximo >= len(robo.fichas):
                        robo.estouros += 1
                        self._registrar(horario, numero, robo, aposta, -aposta, "Perdeu — estourou", nivel)
                        robo.ciclo, robo.aguardar_saida = None, True
                    elif self.limite_max is not None and robo.fichas[proximo] > self.limite_max:
                        robo.estouros += 1
                        self._registrar(horario, numero, robo, aposta, -aposta, "Perdeu — limite da mesa", nivel)
                        robo.ciclo, robo.aguardar_saida = None, True
                    else:
                        self._registrar(horario, numero, robo, aposta, -aposta, "Perdeu", nivel)
                        robo.ciclo["nivel"] = proximo
            if acertou:
                robo.sem_sair, robo.aguardar_saida = 0, False
            elif robo.sem_sair is not None:
                robo.sem_sair += 1
                robo.max_sem_sair = max(robo.max_sem_sair, robo.sem_sair)

        self._preparar_apostas(horario)

    def _preparar_apostas(self, horario):
        for robo in self.robos:
            # gatilho 0 = aposta direta: entra em todo giro em que não houver ciclo aberto
            if robo.ciclo is None and (robo.gatilho == 0 or (not robo.aguardar_saida and robo.sem_sair == robo.gatilho)):
                robo.ciclo = {"inicio": horario, "nivel": 0, "lucro": 0.0}
                robo.entradas += 1
        total = sum(r.aposta_atual for r in self.robos)
        if total > self.saldo + 1e-9:
            self.quebrou = True
            for robo in self.robos:
                robo.ciclo = None

    def _registrar(self, horario, numero, robo, aposta, resultado, texto, nivel=None):
        self.historico.append({
            "horario": horario, "numero": numero, "categoria": robo.categoria, "aposta": aposta,
            "nivel": nivel, "resultado": texto, "lucro": round(resultado, 2), "caixa": round(self.saldo, 2),
        })

    # ---------------------------------------------------------------- situação
    def status(self, robo):
        if self.quebrou:
            return "banca insuficiente — parado"
        if robo.ciclo is not None:
            nivel = robo.ciclo["nivel"]
            return f"apostando {robo.aposta_atual:.2f}".replace(".", ",") + (" (entrada)" if nivel == 0 else f" (recuperação {nivel})")
        if robo.gatilho == 0:
            return "aposta direta — entra no próximo giro"
        if robo.sem_sair is None:
            return "aguardando sair para começar a contar"
        if robo.aguardar_saida:
            return "estourou — aguardando sair de novo"
        return f"{robo.sem_sair} sem sair — faltam {robo.gatilho - robo.sem_sair} para entrar"

    @property
    def resumo(self):
        return {
            "entradas": sum(r.entradas for r in self.robos),
            "vitorias": sum(r.vitorias for r in self.robos),
            "estouros": sum(r.estouros for r in self.robos),
        }
