"""
Coletor de resultados de roletas ao vivo (Evolution e Pragmatic Play).

- Evolution: busca as últimas ~500 rodadas de cada mesa no CasinoScores, e no TipMiner
  (últimas 200) as mesas que o CasinoScores não acompanha.
- Pragmatic Play: lê o canal público de lobby da Pragmatic (últimos 20 resultados
  e limites de aposta de cada mesa). Como são só ~10 min de histórico,
  a coleta precisa rodar a cada 5 minutos.

As rodadas novas são gravadas em arquivos CSV diários: dados/AAAA/AAAA-MM-DD.csv
(dia no horário de Brasília). Rodadas já gravadas são ignoradas pelo ID único.
Os limites de aposta das mesas Pragmatic ficam em dados/limites.json.
"""

import asyncio
import csv
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Evolution via CasinoScores: "nome na API do CasinoScores": "nome amigável"
MESAS_EVOLUTION = {
    "autoroulette": "Auto Roulette (Evolution)",  # o TipMiner não acompanha esta mesa
    # Immersive passou para o TipMiner: o CasinoScores perdia ~7% dos giros dela
    # Removidas: Fireball (fonte com pouco histórico); Gold Vault, Red Door, Lightning e XXXtreme Lightning (a pedido)
}

# Evolution via TipMiner (mesas que o CasinoScores não acompanha): "id público (pid)": "nome amigável"
MESAS_TIPMINER = {
    "dfa678e4-4452-4723-a97d-f3703302d5cc": "Immersive Roulette",
    "b79aa4ce-82f0-4590-9bfd-efd3b7367c8a": "Auto-Roulette VIP",
    "d5ac92b3-d28e-4a3d-8117-9695a24c0053": "Roleta Ao Vivo",
}

# Pragmatic Play: "id da mesa no lobby": "nome amigável"
MESAS_PRAGMATIC = {
    "210": "Auto Mega Roulette (Pragmatic)",
    "225": "Auto Roulette (Pragmatic)",
    "226": "Speed Auto Roulette (Pragmatic)",
}

MESAS_ATIVAS = list(MESAS_EVOLUTION.values()) + list(MESAS_TIPMINER.values()) + list(MESAS_PRAGMATIC.values())

URL_EVOLUTION = (
    "https://api.casinoscores.com/svc-evolution-game-events/api/{mesa}"
    "?page=0&size={tamanho}&sort=data.settledAt,desc&duration=24"
)
URL_TIPMINER = "https://api.core.public.tipminer.com/v1/roulette/rounds/{pid}/history?limit={tamanho}"
URL_PRAGMATIC = "wss://dga.pragmaticplaylive.net/ws"
CASSINO_PRAGMATIC = "ppcdk00000005349"  # identificador público de lobby usado para leitura

PASTA_DADOS = Path(__file__).parent / "dados"
ARQUIVO_LIMITES = PASTA_DADOS / "limites.json"
FUSO_BRASILIA = timezone(timedelta(hours=-3))  # Brasil não tem horário de verão desde 2019
LIMITE_SEM_GIROS = timedelta(hours=2)  # mesa sem giros novos por mais tempo que isso gera alerta

COLUNAS = [
    "id", "mesa", "numero", "cor", "paridade",
    "horario_brasilia", "iniciado_utc", "finalizado_utc", "numeros_sorte",
]
VERMELHOS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}


def linha(id_, mesa, numero, finalizado, iniciado_utc="", sorte=""):
    return {
        "id": id_,
        "mesa": mesa,
        "numero": numero,
        "cor": "Verde" if numero == 0 else ("Vermelho" if numero in VERMELHOS else "Preto"),
        "paridade": "" if numero == 0 else ("Par" if numero % 2 == 0 else "Impar"),
        "horario_brasilia": finalizado.astimezone(FUSO_BRASILIA).strftime("%Y-%m-%d %H:%M:%S"),
        "iniciado_utc": iniciado_utc,
        "finalizado_utc": finalizado.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "numeros_sorte": sorte,
    }


# ---------------------------------------------------------------- Evolution
def coletar_evolution(mesa, nome, tamanho=500):
    req = urllib.request.Request(URL_EVOLUTION.format(mesa=mesa, tamanho=tamanho), headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        itens = json.load(resp)
    rodadas = []
    for item in itens:
        try:
            d = item["data"]
            numero = d["result"]["outcome"]["number"]
            if d["status"] != "Resolved" or numero is None:
                continue
            sorte = " ".join(f'{n["number"]}x{n["roundedMultiplier"]}' for n in d["result"].get("luckyNumbersList") or [])
            finalizado = datetime.fromisoformat(d["settledAt"].replace("Z", "+00:00"))
            rodadas.append(linha(item["id"], nome, int(numero), finalizado, d.get("startedAt", ""), sorte))
        except (KeyError, TypeError, ValueError):
            continue
    return rodadas


# ---------------------------------------------------------------- TipMiner (Evolution)
def coletar_tipminer(pid, nome, tamanho=200):
    req = urllib.request.Request(URL_TIPMINER.format(pid=pid, tamanho=tamanho), headers={
        "User-Agent": "Mozilla/5.0", "Origin": "https://www.tipminer.com", "Referer": "https://www.tipminer.com/",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        itens = json.load(resp)
    rodadas = []
    for item in itens:
        try:
            finalizado = datetime.fromisoformat(item["instant"].replace("Z", "+00:00"))
            rodadas.append(linha(f'tm-{item["uuid"]}', nome, int(item["result"]), finalizado))
        except (KeyError, TypeError, ValueError):
            continue
    return rodadas


# ---------------------------------------------------------------- Pragmatic
async def _ler_lobby_pragmatic():
    import websockets  # só o coletor precisa desta biblioteca

    mesas = {}
    async with websockets.connect(URL_PRAGMATIC, open_timeout=30, max_size=None) as ws:
        await ws.send(json.dumps({
            "type": "subscribe", "isDeltaEnabled": True, "casinoId": CASSINO_PRAGMATIC,
            "key": list(MESAS_PRAGMATIC), "currency": "BRL",
        }))
        prazo = time.monotonic() + 30
        while time.monotonic() < prazo and len(mesas) < len(MESAS_PRAGMATIC):
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 10))
            except asyncio.TimeoutError:
                break
            if isinstance(msg, dict) and msg.get("tableId") in MESAS_PRAGMATIC and msg.get("last20Results"):
                mesas[msg["tableId"]] = msg
    return mesas


def coletar_pragmatic():
    """Devolve ({nome: [rodadas]}, {nome: limites})."""
    dados = asyncio.run(_ler_lobby_pragmatic())
    rodadas, limites = {}, {}
    for mesa_id, nome in MESAS_PRAGMATIC.items():
        msg = dados.get(mesa_id)
        if not msg:
            continue
        lista = []
        for r in msg["last20Results"]:
            try:
                finalizado = datetime.strptime(r["time"], "%b %d, %Y %I:%M:%S %p").replace(tzinfo=timezone.utc)
                sorte = " ".join(f"{n}x{m}" for n, m in (r.get("slots") or {}).items())
                lista.append(linha(f'pp-{r["gameId"]}', nome, int(r["result"]), finalizado, sorte=sorte))
            except (KeyError, TypeError, ValueError):
                continue
        rodadas[nome] = lista
        lim = msg.get("tableLimits") or {}
        if lim.get("minBet") is not None and lim.get("maxBet") is not None:
            limites[nome] = {"min": lim["minBet"], "max": lim["maxBet"], "moeda": msg.get("currency", "BRL")}
    return rodadas, limites


def buscar_ao_vivo(nome):
    """
    Últimos giros de uma mesa direto da fonte (para o simulador ao vivo): [(horario_utc, numero, id)].
    O id identifica o giro com segurança: a Pragmatic às vezes corrige o horário de um giro já publicado.
    """
    for mesa, n in MESAS_EVOLUTION.items():
        if n == nome:
            rodadas = coletar_evolution(mesa, nome, tamanho=40)
            break
    else:
        for pid, n in MESAS_TIPMINER.items():
            if n == nome:
                rodadas = coletar_tipminer(pid, nome, tamanho=40)
                break
        else:
            rodadas = coletar_pragmatic()[0].get(nome, [])
    return sorted(
        (datetime.fromisoformat(r["finalizado_utc"].replace("Z", "+00:00")), int(r["numero"]), r["id"]) for r in rodadas
    )


# ---------------------------------------------------------------- gravação
def arquivo_do_dia(horario_brasilia):
    dia = horario_brasilia[:10]
    return PASTA_DADOS / dia[:4] / f"{dia}.csv"


def ids_existentes(arquivo):
    if not arquivo.exists():
        return set()
    with open(arquivo, newline="", encoding="utf-8") as f:
        return {linha["id"] for linha in csv.DictReader(f)}


def gravar(novas):
    por_arquivo = {}
    for r in novas:
        por_arquivo.setdefault(arquivo_do_dia(r["horario_brasilia"]), []).append(r)
    total = 0
    for arquivo, rodadas in por_arquivo.items():
        existentes = ids_existentes(arquivo)
        ineditas = [r for r in rodadas if r["id"] not in existentes]
        if not ineditas:
            continue
        ineditas.sort(key=lambda r: r["finalizado_utc"])
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        novo_arquivo = not arquivo.exists()
        with open(arquivo, "a", newline="", encoding="utf-8") as f:
            escritor = csv.DictWriter(f, fieldnames=COLUNAS)
            if novo_arquivo:
                escritor.writeheader()
            escritor.writerows(ineditas)
        total += len(ineditas)
        print(f"  -> {arquivo.name}: +{len(ineditas)} rodadas")
    return total


def gravar_limites(limites):
    """Atualiza dados/limites.json só se algo mudou (evita alterações a cada coleta)."""
    atual = {}
    if ARQUIVO_LIMITES.exists():
        atual = json.loads(ARQUIVO_LIMITES.read_text(encoding="utf-8"))
    novo = {**atual, **limites}
    if novo != atual:
        ARQUIVO_LIMITES.parent.mkdir(parents=True, exist_ok=True)
        ARQUIVO_LIMITES.write_text(json.dumps(novo, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        print("Limites de aposta atualizados.")


def main():
    agora = datetime.now(timezone.utc)
    por_mesa, problemas = {}, []

    com_erro = set()  # mesas cujo erro já foi registrado

    for mesa, nome in MESAS_EVOLUTION.items():
        try:
            por_mesa[nome] = coletar_evolution(mesa, nome)
        except Exception as erro:
            problemas.append(f"{nome}: erro ao consultar o CasinoScores ({erro})")
            com_erro.add(nome)
        time.sleep(1)  # pausa curta para não sobrecarregar o site

    for pid, nome in MESAS_TIPMINER.items():
        try:
            por_mesa[nome] = coletar_tipminer(pid, nome)
        except Exception as erro:
            problemas.append(f"{nome}: erro ao consultar o TipMiner ({erro})")
            com_erro.add(nome)
        time.sleep(1)

    try:
        rodadas_pp, limites = coletar_pragmatic()
        por_mesa.update(rodadas_pp)
        gravar_limites(limites)
    except Exception as erro:
        problemas.append(f"Pragmatic Play: erro ao consultar o lobby ({erro})")
        com_erro.update(MESAS_PRAGMATIC.values())

    novas = []
    for nome in MESAS_ATIVAS:
        rodadas = por_mesa.get(nome)
        if rodadas is None:
            if nome not in com_erro:
                problemas.append(f"{nome}: mesa não respondeu")
            continue
        print(f"{nome}: {len(rodadas)} rodadas recebidas")
        if not rodadas:
            problemas.append(f"{nome}: nenhuma rodada recebida")
            continue
        ultima = max(datetime.fromisoformat(r["finalizado_utc"].replace("Z", "+00:00")) for r in rodadas)
        if agora - ultima > LIMITE_SEM_GIROS:
            problemas.append(f"{nome}: sem giros novos há {(agora - ultima).total_seconds() / 3600:.1f} horas")
        novas.extend(rodadas)

    total = gravar(novas)
    print(f"Total de rodadas novas gravadas: {total}")

    # Qualquer problema faz a execução "falhar" no GitHub, que então envia um e-mail de alerta.
    # Os dados coletados das outras mesas são salvos mesmo assim.
    if problemas:
        for p in problemas:
            print(f"::error::{p}")
        sys.exit(1)


if __name__ == "__main__":
    main()
