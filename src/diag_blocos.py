import sys

from extracao import (
    ler_paginas,
    desfazer_hifenizacao,
    remover_repetidas,
    extrair_linhas,
    detectar_delimitador,
    segmentar,
    rotulo_da_linha,
    _chave_contagem,
)

caminho = sys.argv[1]
arg = sys.argv[2] if len(sys.argv) > 2 else None

paginas = ler_paginas(caminho)
paginas = [(n, desfazer_hifenizacao(t)) for n, t in paginas]
paginas, _ = remover_repetidas(paginas)
linhas = extrair_linhas(paginas)

delim = detectar_delimitador(linhas)
blocos = segmentar(linhas)

alvo = None
if arg is not None:
    if arg.startswith("p"):
        pagina = int(arg[1:])
        for i, b in enumerate(blocos, start=1):
            if b.pagina_inicio <= pagina <= b.pagina_fim:
                alvo = i
                break
    else:
        alvo = int(arg)

if alvo is not None:
    b = blocos[alvo - 1]
    print(f"=== BLOCO {alvo} (pags {b.pagina_inicio}-{b.pagina_fim}) ===")
    for l in b.linhas:
        r = rotulo_da_linha(l.texto) or ""
        print(f"[{r:<12}] {l.texto[:110]}")
    raise SystemExit

print(f"Delimitador: {delim!r}")
print(f"Blocos: {len(blocos)}\n")
print(f"{'#':>3} {'pags':>10} {'linhas':>6}  rotulos")
print("-" * 110)
for i, b in enumerate(blocos, start=1):
    rotulos = sorted({r for r in (rotulo_da_linha(l.texto) for l in b.linhas) if r})
    primeira = b.linhas[0].texto[:40] if b.linhas else ""
    print(
        f"{i:>3} {b.pagina_inicio:>4}-{b.pagina_fim:<5} {len(b.linhas):>6}  "
        f"{','.join(rotulos):<30} {primeira}"
    )