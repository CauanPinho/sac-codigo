from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

import pdfplumber

ROTULOS = {
    "ementa": ("ementa",),
    "carga": ("carga horaria", "c.h.", "ch:"),
    "bibliografia": ("bibliografia", "referencias"),
    "objetivo": ("objetivo",),
    "prerequisito": ("pre-requisito", "prerequisito"),
}

PADRAO_HIFEN = re.compile(r"-\n(?=[a-zà-ÿ])")


def normalizar(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acento).strip().casefold()


def ler_paginas(caminho_pdf: str) -> list[tuple[int, str]]:
    paginas = []
    with pdfplumber.open(caminho_pdf) as pdf:
        for numero, pagina in enumerate(pdf.pages, start=1):
            paginas.append((numero, pagina.extract_text() or ""))
    return paginas


def desfazer_hifenizacao(texto: str) -> str:
    return PADRAO_HIFEN.sub("", texto)


def rotulo_da_linha(texto: str) -> str | None:
    n = normalizar(texto)
    for nome, variantes in ROTULOS.items():
        for v in variantes:
            if n.startswith(v):
                resto = n[len(v):]
                if not resto or not resto[0].isalpha():
                    return nome
    return None

def _chave_contagem(linha: str) -> str:
    return re.sub(r"\d+", "#", normalizar(linha))


def remover_repetidas(
    paginas: list[tuple[int, str]], limiar: float = 0.7
) -> tuple[list[tuple[int, str]], list[str]]:
    paginas_com_texto = sum(1 for _, t in paginas if t.strip())
    if paginas_com_texto == 0:
        return paginas, []

    contador: Counter[str] = Counter()
    for _, texto in paginas:
        chaves = {_chave_contagem(l) for l in texto.splitlines() if l.strip()}
        contador.update(chaves)

    corte = limiar * paginas_com_texto
    repetidas = {chave for chave, n in contador.items() if n >= corte}

    limpas = []
    for numero, texto in paginas:
        mantidas = [
            linha
            for linha in texto.splitlines()
            if linha.strip()
            and (
                rotulo_da_linha(linha) is not None
                or _chave_contagem(linha) not in repetidas
            )
        ]
        limpas.append((numero, "\n".join(mantidas)))

    return limpas, sorted(repetidas)


def e_maiuscula(texto: str) -> bool:
    letras = [c for c in texto if c.isalpha()]
    return bool(letras) and all(c.isupper() for c in letras)


@dataclass
class Linha:
    pagina: int
    indice: int
    texto: str
    maiuscula: bool
    comprimento: int
    rotulo_proximo: str | None
    distancia_rotulo: int | None


def extrair_linhas(paginas: list[tuple[int, str]], janela: int = 3) -> list[Linha]:
    brutas: list[tuple[int, int, str]] = []
    for numero, texto in paginas:
        for indice, conteudo in enumerate(texto.splitlines()):
            if conteudo.strip():
                brutas.append((numero, indice, conteudo.strip()))

    linhas = []
    for i, (pagina, indice, texto) in enumerate(brutas):
        rotulo, distancia = None, None
        for d in range(1, janela + 1):
            if i + d >= len(brutas):
                break
            achado = rotulo_da_linha(brutas[i + d][2])
            if achado:
                rotulo, distancia = achado, d
                break

        linhas.append(
            Linha(
                pagina=pagina,
                indice=indice,
                texto=texto,
                maiuscula=e_maiuscula(texto),
                comprimento=len(texto),
                rotulo_proximo=rotulo,
                distancia_rotulo=distancia,
            )
        )
    return linhas


def diagnosticar(
    caminho_pdf: str,
    pagina_inicio: int | None = None,
    pagina_fim: int | None = None,
    so_candidatas: bool = False,
    limite_comprimento: int = 60,
) -> None:
    paginas = ler_paginas(caminho_pdf)
    total = len(paginas)
    vazias = [n for n, t in paginas if not t.strip()]

    paginas = [(n, desfazer_hifenizacao(t)) for n, t in paginas]
    paginas, repetidas = remover_repetidas(paginas)
    linhas = extrair_linhas(paginas)

    print(f"\nArquivo: {caminho_pdf}")
    print(f"Páginas: {total}  |  sem texto: {len(vazias)}", end="")
    if vazias:
        print(f"  -> {vazias[:15]}{' ...' if len(vazias) > 15 else ''}")
    else:
        print()
    print(f"Linhas úteis: {len(linhas)}")

    print(f"\nRemovidas como cabeçalho/rodapé ({len(repetidas)}):")
    for chave in repetidas:
        print(f"  - {chave[:70]}")

    selecao = linhas
    if pagina_inicio is not None:
        selecao = [l for l in selecao if l.pagina >= pagina_inicio]
    if pagina_fim is not None:
        selecao = [l for l in selecao if l.pagina <= pagina_fim]
    if so_candidatas:
        selecao = [
            l
            for l in selecao
            if l.maiuscula and l.comprimento <= limite_comprimento
        ]

    print(f"\n{'pág':>4} {'nº':>3} {'MAI':>4} {'len':>4} {'rótulo':<14} texto")
    print("-" * 100)
    for l in selecao:
        marca = "SIM" if l.maiuscula else "—"
        if l.rotulo_proximo:
            rot = f"{l.rotulo_proximo}(+{l.distancia_rotulo})"
        else:
            rot = "—"
        print(
            f"{l.pagina:>4} {l.indice:>3} {marca:>4} {l.comprimento:>4} "
            f"{rot:<14} {l.texto[:58]}"
        )

    print(f"\nTotal exibido: {len(selecao)} linhas")