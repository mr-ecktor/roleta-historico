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
            if ciclo is None and not aguardar_saida and sem_sair == gatilho:
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


class SimulacaoAoVivo:
    """
    Mesma regra de `simular`, mas processando giro a giro, conforme os giros chegam ao vivo.
    Guardada no session_state do site enquanto a página estiver aberta.
    """

    INTERVALO_MAXIMO_S = 180  # sem giro novo por mais que isso = pausa da mesa: ciclo em andamento é encerrado

    def __init__(self, padrao, categoria, gatilho, fichas, banca, limite_max=None):
        self.padrao, self.categoria, self.gatilho = padrao, categoria, gatilho
        self.fichas, self.banca, self.limite_max = fichas, banca, limite_max
        self.saldo = banca
        self.sem_sair = None
        self.aguardar_saida = False
        self.ciclo = None
        self.ciclos = []
        self.max_sem_sair = 0
        self.ultimo_horario = None
        self.giros_vistos = 0
        self.quebrou = False

    def _saiu(self, numero):
        return PADROES[self.padrao][self.categoria](numero)

    def aquecer(self, giros):
        """Usa giros anteriores ao Start só para saber há quantas rodadas a categoria está sem sair."""
        for horario, numero in giros:
            if self.ultimo_horario and (horario - self.ultimo_horario).total_seconds() > self.INTERVALO_MAXIMO_S:
                self.sem_sair = None
            self.sem_sair = 0 if self._saiu(numero) else (None if self.sem_sair is None else self.sem_sair + 1)
            self.ultimo_horario = horario
        self._talvez_entrar(horario if giros else None)

    def processar(self, horario, numero):
        if self.quebrou:
            return
        if self.ultimo_horario and (horario - self.ultimo_horario).total_seconds() > self.INTERVALO_MAXIMO_S:
            if self.ciclo and self.ciclo["maior_aposta"] > 0:
                self.ciclos.append({**self.ciclo, "fim": horario, "resultado": "Interrompido"})
            self.ciclo, self.sem_sair, self.aguardar_saida = None, None, False
        self.ultimo_horario = horario
        self.giros_vistos += 1
        acertou = self._saiu(numero)

        if self.ciclo is not None:
            aposta = self.fichas[self.ciclo["nivel"]]
            self.ciclo["maior_aposta"] = aposta
            if acertou:
                ganho = aposta * PAGAMENTO[self.padrao]
                self.saldo += ganho
                self.ciclo["lucro"] += ganho
                self.ciclos.append({**self.ciclo, "fim": horario, "resultado": "Ganhou"})
                self.ciclo = None
            else:
                self.saldo -= aposta
                self.ciclo["lucro"] -= aposta
                proximo = self.ciclo["nivel"] + 1
                if proximo >= len(self.fichas):
                    self.ciclos.append({**self.ciclo, "fim": horario, "resultado": "Estourou"})
                    self.ciclo, self.aguardar_saida = None, True
                elif self.limite_max is not None and self.fichas[proximo] > self.limite_max:
                    self.ciclos.append({**self.ciclo, "fim": horario, "resultado": "Limite da mesa"})
                    self.ciclo, self.aguardar_saida = None, True
                else:
                    self.ciclo["nivel"] = proximo

        if acertou:
            self.sem_sair, self.aguardar_saida = 0, False
        elif self.sem_sair is not None:
            self.sem_sair += 1
            self.max_sem_sair = max(self.max_sem_sair, self.sem_sair)

        self._talvez_entrar(horario)

    def _talvez_entrar(self, horario):
        if self.ciclo is None and not self.aguardar_saida and self.sem_sair == self.gatilho:
            self.ciclo = {"inicio": horario, "nivel": 0, "lucro": 0.0, "maior_aposta": 0.0}
        if self.ciclo is not None and self.fichas[self.ciclo["nivel"]] > self.saldo + 1e-9:
            self.ciclos.append({**self.ciclo, "fim": horario, "resultado": "Banca insuficiente"})
            self.ciclo, self.quebrou = None, True

    @property
    def status(self):
        if self.quebrou:
            return "Banca insuficiente para a próxima aposta — simulação parada"
        if self.ciclo is not None:
            nivel = self.ciclo["nivel"]
            return (f"Apostando {self.fichas[nivel]:.2f} em {self.categoria} "
                    + ("(entrada)" if nivel == 0 else f"(recuperação {nivel})"))
        if self.sem_sair is None:
            return f"Aguardando {self.categoria} sair para começar a contar"
        if self.aguardar_saida:
            return f"Ciclo estourado — aguardando {self.categoria} sair de novo"
        falta = self.gatilho - self.sem_sair
        return f"{self.categoria} está há {self.sem_sair} sem sair — faltam {falta} para entrar"

    @property
    def resumo(self):
        resultados = [c["resultado"] for c in self.ciclos]
        return {
            "entradas": len(self.ciclos) + (1 if self.ciclo and self.ciclo["maior_aposta"] > 0 else 0),
            "vitorias": resultados.count("Ganhou"),
            "estouros": resultados.count("Estourou") + resultados.count("Limite da mesa"),
        }
