from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

import pdfplumber
import pandas as pd

ROTULOS = {
    "ementario": ("ementario",),
    "disciplina": ("disciplina",),
    "curso": ("curso",),
    "ementa": ("ementa",),
    "carga": ("carga horaria", "c.h.", "ch:"),
    "objetivo": ("objetivo",),
    "bibliografia": ("bibliografia", "referencias"),
    "prerequisito": ("pre-requisito", "prerequisito"),
}

TODOS_ROTULOS = {
    "disciplina", "curso", "ementa", "carga",
    "objetivo", "bibliografia", "prerequisito",
}

PADRAO_HIFEN = re.compile(r"-\n(?=[a-zà-ÿ])")

PADRAO_ANEXO = re.compile(r"\bANEXO\s+([IVXLCDM]+|\d+)\b", re.IGNORECASE)

PADRAO_VALOR_DISCIPLINA = re.compile(
    r"^(?:(\d{1,2})\s*[º°]\s+)?(.+?)\s+([A-ZÀ-Ý]{2,6}\d{0,2})$"
)

PADRAO_CARGA = re.compile(r"(\d{1,3})\s*h?\s+(\d{1,3})\s*h?\b", re.IGNORECASE)

ROMANOS = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7,
    "VIII": 8, "IX": 9, "X": 10,
}


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


@dataclass
class Bloco:
    pagina_inicio: int
    pagina_fim: int
    linhas: list[Linha]


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


def detectar_delimitador(linhas: list[Linha], minimo: int = 3) -> str | None:
    contador: Counter[str] = Counter()
    primeira_ocorrencia: dict[str, int] = {}
    for i, linha in enumerate(linhas):
        chave = _chave_contagem(linha.texto)
        contador[chave] += 1
        primeira_ocorrencia.setdefault(chave, i)

    if not contador:
        return None

    maximo = max(contador.values())
    if maximo < minimo:
        return None

    candidatas = sorted(
        (chave for chave, n in contador.items() if n == maximo),
        key=lambda c: primeira_ocorrencia[c],
    )
    return candidatas[0]


def segmentar(linhas: list[Linha]) -> list[Bloco]:
    delimitador = detectar_delimitador(linhas)
    if delimitador is None:
        if not linhas:
            return []
        return [Bloco(linhas[0].pagina, linhas[-1].pagina, linhas)]

    blocos: list[Bloco] = []
    atual: list[Linha] = []
    for linha in linhas:
        if _chave_contagem(linha.texto) == delimitador:
            if atual:
                blocos.append(Bloco(atual[0].pagina, atual[-1].pagina, atual))
            atual = []
            continue
        atual.append(linha)
    if atual:
        blocos.append(Bloco(atual[0].pagina, atual[-1].pagina, atual))
    return blocos


def localizar_anexos(paginas: list[tuple[int, str]]) -> list[tuple[int, int]]:
    marcos = []
    for numero, texto in paginas:
        achado = PADRAO_ANEXO.search(texto)
        if achado:
            valor = achado.group(1).upper()
            anexo = ROMANOS.get(valor) or (int(valor) if valor.isdigit() else None)
            if anexo is not None:
                marcos.append((numero, anexo))
    return marcos


def periodo_do_bloco(bloco: Bloco, marcos: list[tuple[int, int]]) -> int | None:
    periodo = None
    for pagina_marco, anexo in marcos:
        if pagina_marco <= bloco.pagina_inicio:
            periodo = anexo
        else:
            break
    return periodo


def _indice_rotulo(bloco: Bloco, rotulo: str) -> int | None:
    for i, linha in enumerate(bloco.linhas):
        if rotulo_da_linha(linha.texto) == rotulo:
            return i
    return None


def _indice_contendo(bloco: Bloco, termo: str, limite: int | None = None) -> int | None:
    linhas = bloco.linhas if limite is None else bloco.linhas[:limite]
    for i, linha in enumerate(linhas):
        if termo in normalizar(linha.texto):
            return i
    return None


def _texto_apos(bloco: Bloco, indice_rotulo: int, proximos_rotulos: set[str]) -> str:
    partes = []
    linha_rotulo = bloco.linhas[indice_rotulo].texto
    if ":" in linha_rotulo:
        _, resto = linha_rotulo.split(":", 1)
        resto = resto.strip()
        if resto:
            partes.append(resto)

    for linha in bloco.linhas[indice_rotulo + 1:]:
        if rotulo_da_linha(linha.texto) in proximos_rotulos:
            break
        partes.append(linha.texto)
    return " ".join(partes).strip()


def _carga_e_prereq(bloco: Bloco, idx_carga: int) -> tuple[int | None, int | None, int | None, str]:
    textos = []
    for linha in bloco.linhas[idx_carga + 1: idx_carga + 8]:
        if rotulo_da_linha(linha.texto):
            break
        textos.append(linha.texto.strip())
    bruto = " ".join(textos)

    achado = PADRAO_CARGA.search(bruto)
    if not achado:
        return None, None, None, bruto.strip()

    teorica, pratica = int(achado.group(1)), int(achado.group(2))
    antes = bruto[:achado.start()]
    depois = bruto[achado.end():]

    antes = re.sub(r"(?i)\bte[oó]rica\b", "", antes)
    antes = re.sub(r"(?i)\bpr[aá]tica\b", "", antes)
    prereq = (antes.strip() + " " + depois.strip()).strip(" .:-")

    return teorica, pratica, teorica + pratica, prereq


def extrair_campos(bloco: Bloco) -> dict:
    avisos: list[str] = []
    campos: dict = {
        "pagina_inicio": bloco.pagina_inicio,
        "pagina_fim": bloco.pagina_fim,
        "periodo": None,
        "disciplina": None,
        "codigo": None,
        "carga_teorica": None,
        "carga_pratica": None,
        "carga_total": None,
        "prerequisito": "",
        "ementa": "",
        "objetivo": "",
        "avisos": avisos,
    }

    idx_ementa = _indice_rotulo(bloco, "ementa")

    idx_cab = _indice_contendo(bloco, "disciplina", limite=idx_ementa)
    if idx_cab is not None and idx_cab + 1 < len(bloco.linhas):
        valor = bloco.linhas[idx_cab + 1].texto.strip()
        achado = PADRAO_VALOR_DISCIPLINA.match(valor)
        if not achado and idx_cab + 2 < len(bloco.linhas):
            valor2 = f"{valor} {bloco.linhas[idx_cab + 2].texto.strip()}"
            achado2 = PADRAO_VALOR_DISCIPLINA.match(valor2)
            if achado2:
                valor, achado = valor2, achado2
        if achado:
            periodo, nome, codigo = achado.groups()
            campos["periodo"] = int(periodo) if periodo else None
            campos["disciplina"] = nome.strip()
            campos["codigo"] = codigo
        else:
            campos["disciplina"] = valor or None
            avisos.append("nome/codigo nao separados")
    else:
        avisos.append("sem cabecalho disciplina")

    idx_carga = _indice_contendo(bloco, "carga horaria", limite=idx_ementa)
    if idx_carga is not None:
        teorica, pratica, total, prereq = _carga_e_prereq(bloco, idx_carga)
        campos["carga_teorica"] = teorica
        campos["carga_pratica"] = pratica
        campos["carga_total"] = total
        campos["prerequisito"] = prereq
    if campos["carga_total"] is None:
        avisos.append("sem carga horaria")

    for rotulo in ("ementa", "objetivo"):
        idx = _indice_rotulo(bloco, rotulo)
        if idx is not None:
            campos[rotulo] = _texto_apos(bloco, idx, TODOS_ROTULOS - {rotulo})
        else:
            avisos.append(f"sem rotulo {rotulo}")

    return campos


def pontuar(campos: dict) -> float:
    pontos = 0.0
    if campos.get("disciplina"):
        pontos += 0.25
    if campos.get("codigo"):
        pontos += 0.10
    if campos.get("ementa") and len(campos["ementa"]) > 20:
        pontos += 0.30
    if campos.get("objetivo") and len(campos["objetivo"]) > 10:
        pontos += 0.20
    if campos.get("carga_total"):
        pontos += 0.15
    return round(pontos, 2)


def extrair_ppc(caminho_pdf: str) -> pd.DataFrame:
    paginas_brutas = ler_paginas(caminho_pdf)
    marcos_anexo = localizar_anexos(paginas_brutas)

    paginas = [(n, desfazer_hifenizacao(t)) for n, t in paginas_brutas]
    paginas, _ = remover_repetidas(paginas)
    linhas = extrair_linhas(paginas)
    blocos = segmentar(linhas)

    registros = []
    for bloco in blocos:
        if len(bloco.linhas) > 150:
            continue
        campos = extrair_campos(bloco)
        nome = campos["disciplina"]
        if not nome or len(nome) > 80:
            continue
        if not campos["ementa"] and not campos["objetivo"]:
            continue
        if campos["periodo"] is None:
            campos["periodo"] = periodo_do_bloco(bloco, marcos_anexo)
        campos["confianca"] = pontuar(campos)
        registros.append(campos)

    return pd.DataFrame(registros)


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
            l for l in selecao if l.maiuscula and l.comprimento <= limite_comprimento
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