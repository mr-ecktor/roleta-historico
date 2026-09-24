"""
Junta todos os CSVs diários da pasta dados/ em um banco SQLite (roleta.db).
Pode ser executado quantas vezes quiser: só adiciona as rodadas que faltam.
"""

import csv
import sqlite3
from pathlib import Path

PASTA = Path(__file__).parent
BANCO = PASTA / "roleta.db"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS giros (
    id               TEXT PRIMARY KEY,
    mesa             TEXT NOT NULL,
    numero           INTEGER NOT NULL,
    cor              TEXT,
    paridade         TEXT,
    duzia            TEXT,     -- 1a (1-12), 2a (13-24), 3a (25-36) ou Zero
    coluna           TEXT,     -- 1a, 2a, 3a ou Zero
    alto_baixo       TEXT,     -- Baixo (1-18), Alto (19-36) ou Zero
    horario_brasilia TEXT NOT NULL,
    dia              TEXT NOT NULL,
    iniciado_utc     TEXT,
    finalizado_utc   TEXT,
    numeros_sorte    TEXT
);
CREATE INDEX IF NOT EXISTS idx_giros_mesa_horario ON giros (mesa, horario_brasilia);
CREATE INDEX IF NOT EXISTS idx_giros_dia ON giros (dia);
"""


def classificar(numero):
    if numero == 0:
        return "Zero", "Zero", "Zero"
    duzia = f"{(numero - 1) // 12 + 1}a"
    coluna = f"{(numero - 1) % 3 + 1}a"
    alto_baixo = "Baixo" if numero <= 18 else "Alto"
    return duzia, coluna, alto_baixo


def main():
    con = sqlite3.connect(BANCO)
    con.executescript(ESQUEMA)
    antes = con.execute("SELECT COUNT(*) FROM giros").fetchone()[0]

    for arquivo in sorted((PASTA / "dados").rglob("*.csv")):
        with open(arquivo, newline="", encoding="utf-8") as f:
            linhas = []
            for r in csv.DictReader(f):
                numero = int(r["numero"])
                linhas.append((
                    r["id"], r["mesa"], numero, r["cor"], r["paridade"],
                    *classificar(numero),
                    r["horario_brasilia"], r["horario_brasilia"][:10],
                    r["iniciado_utc"], r["finalizado_utc"], r["numeros_sorte"],
                ))
        con.executemany("INSERT OR IGNORE INTO giros VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", linhas)

    con.commit()
    depois = con.execute("SELECT COUNT(*) FROM giros").fetchone()[0]
    print(f"Banco atualizado: {depois - antes} rodadas novas, {depois} no total.")
    for mesa, qtd, primeiro, ultimo in con.execute(
        "SELECT mesa, COUNT(*), MIN(horario_brasilia), MAX(horario_brasilia) FROM giros GROUP BY mesa ORDER BY mesa"
    ):
        print(f"  {mesa:<30} {qtd:>7} giros  ({primeiro} -> {ultimo})")
    con.close()


if __name__ == "__main__":
    main()
