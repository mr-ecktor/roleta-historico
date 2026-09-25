"""
Coletor de resultados das roletas ao vivo da Evolution.

Busca as últimas rodadas de cada mesa no CasinoScores e grava as novas
em arquivos CSV diários: dados/AAAA/AAAA-MM-DD.csv (dia no horário de Brasília).
Rodadas já gravadas são ignoradas (pelo ID único de cada rodada).
"""

import csv
import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Mesas monitoradas: "nome na API": "nome amigável"
MESAS = {
    "lightningroulette": "Lightning Roulette",
    "xxxtremelightningroulette": "XXXtreme Lightning Roulette",
    "immersiveroulette": "Immersive Roulette",
    "autoroulette": "Auto Roulette",
    "goldvaultroulette": "Gold Vault Roulette",
    "reddoorroulette": "Red Door Roulette",
    # Fireball Roulette foi removida: a fonte guarda só ~1h de histórico e o registro ficava com buracos
}

URL_API = (
    "https://api.casinoscores.com/svc-evolution-game-events/api/{mesa}"
    "?page=0&size=500&sort=data.settledAt,desc&duration=24"
)

PASTA_DADOS = Path(__file__).parent / "dados"
FUSO_BRASILIA = timezone(timedelta(hours=-3))  # Brasil não tem horário de verão desde 2019

COLUNAS = [
    "id", "mesa", "numero", "cor", "paridade",
    "horario_brasilia", "iniciado_utc", "finalizado_utc", "numeros_sorte",
]


def buscar_rodadas(mesa):
    req = urllib.request.Request(URL_API.format(mesa=mesa), headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def converter(item, nome_mesa):
    d = item["data"]
    resultado = d["result"]["outcome"]
    finalizado = datetime.fromisoformat(d["settledAt"].replace("Z", "+00:00"))
    sorte = [
        f'{n["number"]}x{n["roundedMultiplier"]}'
        for n in d["result"].get("luckyNumbersList") or []
    ]
    return {
        "id": item["id"],
        "mesa": nome_mesa,
        "numero": resultado["number"],
        "cor": {"Red": "Vermelho", "Black": "Preto", "Green": "Verde"}.get(resultado.get("color"), resultado.get("color")),
        "paridade": {"Even": "Par", "Odd": "Impar"}.get(resultado.get("type"), resultado.get("type")),
        "horario_brasilia": finalizado.astimezone(FUSO_BRASILIA).strftime("%Y-%m-%d %H:%M:%S"),
        "iniciado_utc": d.get("startedAt", ""),
        "finalizado_utc": d["settledAt"],
        "numeros_sorte": " ".join(sorte),
    }


def arquivo_do_dia(horario_brasilia):
    dia = horario_brasilia[:10]
    return PASTA_DADOS / dia[:4] / f"{dia}.csv"


def ids_existentes(arquivo):
    if not arquivo.exists():
        return set()
    with open(arquivo, newline="", encoding="utf-8") as f:
        return {linha["id"] for linha in csv.DictReader(f)}


def main():
    novas = []
    for mesa, nome in MESAS.items():
        try:
            itens = buscar_rodadas(mesa)
        except Exception as erro:
            print(f"[ERRO] {nome}: {erro}")
            continue
        rodadas, ignoradas = [], 0
        for i in itens:
            try:
                if i["data"]["status"] == "Resolved" and i["data"]["result"]["outcome"]["number"] is not None:
                    rodadas.append(converter(i, nome))
                    continue
            except (KeyError, TypeError, ValueError):
                pass
            ignoradas += 1
        print(f"{nome}: {len(rodadas)} rodadas recebidas" + (f" ({ignoradas} ignoradas)" if ignoradas else ""))
        novas.extend(rodadas)
        time.sleep(1)  # pausa curta para não sobrecarregar o site

    # Agrupa por arquivo diário e grava só o que ainda não existe
    por_arquivo = {}
    for r in novas:
        por_arquivo.setdefault(arquivo_do_dia(r["horario_brasilia"]), []).append(r)

    total_gravadas = 0
    for arquivo, rodadas in por_arquivo.items():
        existentes = ids_existentes(arquivo)
        inedita = [r for r in rodadas if r["id"] not in existentes]
        if not inedita:
            continue
        inedita.sort(key=lambda r: r["finalizado_utc"])
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        novo_arquivo = not arquivo.exists()
        with open(arquivo, "a", newline="", encoding="utf-8") as f:
            escritor = csv.DictWriter(f, fieldnames=COLUNAS)
            if novo_arquivo:
                escritor.writeheader()
            escritor.writerows(inedita)
        total_gravadas += len(inedita)
        print(f"  -> {arquivo.name}: +{len(inedita)} rodadas")

    print(f"Total de rodadas novas gravadas: {total_gravadas}")


if __name__ == "__main__":
    main()
