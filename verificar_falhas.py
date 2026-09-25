"""Mostra, para cada mesa, os intervalos em que a coleta falhou (buracos no histórico)."""

from analise import FUSO_BRASILIA, carregar_giros, dividir_em_trechos

for mesa, giros in sorted(carregar_giros().items()):
    trechos = dividir_em_trechos(giros)
    falhas = [
        f"{a[-1][0].astimezone(FUSO_BRASILIA):%d/%m %H:%M} -> {b[0][0].astimezone(FUSO_BRASILIA):%d/%m %H:%M}"
        for a, b in zip(trechos, trechos[1:])
    ]
    print(f"{mesa:<30} {len(giros):>7} giros   falhas: {', '.join(falhas) if falhas else 'nenhuma'}")
