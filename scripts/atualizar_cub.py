#!/usr/bin/env python3
"""Atualiza cub.js com a série histórica mais recente do CUB/RS (Sinduscon-RS).

1. Abre https://sinduscon-rs.com.br/cub-rs/ e localiza o primeiro link
   "Série Histórica – Valor" (o mais recente fica no topo da página).
2. Baixa o PDF e extrai a tabela de cada ano (uma página por ano).
3. Grava cub.js na raiz do projeto, somente se os dados mudaram.

Uso:  python scripts/atualizar_cub.py [--pdf arquivo.pdf]
"""
import argparse
import html
import io
import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber

PAGINA = "https://sinduscon-rs.com.br/cub-rs/"
SAIDA = Path(__file__).resolve().parent.parent / "cub.js"
PREFIXO_JS = "window.CUB_DADOS = "
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

# Projetos-padrão da NBR 12.721/2006, na ordem em que aparecem no PDF.
PROJETOS = [
    ("R 1-B", "Residência unifamiliar – padrão baixo", "RESIDENCIAL"),
    ("R 1-N", "Residência unifamiliar – padrão normal", "RESIDENCIAL"),
    ("R 1-A", "Residência unifamiliar – padrão alto", "RESIDENCIAL"),
    ("PP 4-B", "Prédio popular – padrão baixo", "RESIDENCIAL"),
    ("PP 4-N", "Prédio popular – padrão normal", "RESIDENCIAL"),
    ("R 8-B", "Residência multifamiliar (8 pav.) – padrão baixo", "RESIDENCIAL"),
    ("R 8-N", "Residência multifamiliar (8 pav.) – padrão normal", "RESIDENCIAL"),
    ("R 8-A", "Residência multifamiliar (8 pav.) – padrão alto", "RESIDENCIAL"),
    ("R 16-N", "Residência multifamiliar (16 pav.) – padrão normal", "RESIDENCIAL"),
    ("R 16-A", "Residência multifamiliar (16 pav.) – padrão alto", "RESIDENCIAL"),
    ("PIS", "Projeto de interesse social", "RESIDENCIAL"),
    ("RP1Q", "Residência popular", "RESIDENCIAL"),
    ("CAL 8-N", "Comercial andares livres – padrão normal", "COMERCIAL"),
    ("CAL 8-A", "Comercial andares livres – padrão alto", "COMERCIAL"),
    ("CSL 8-N", "Comercial salas e lojas (8 pav.) – padrão normal", "COMERCIAL"),
    ("CSL 8-A", "Comercial salas e lojas (8 pav.) – padrão alto", "COMERCIAL"),
    ("CSL 16-N", "Comercial salas e lojas (16 pav.) – padrão normal", "COMERCIAL"),
    ("CSL 16-A", "Comercial salas e lojas (16 pav.) – padrão alto", "COMERCIAL"),
    ("GI", "Galpão industrial", "INDUSTRIAL"),
]
CODIGOS = [p[0] for p in PROJETOS]

# Código seguido apenas de valores até o fim da linha. Os códigos mais longos
# vêm primeiro para "R 16-N" não casar como "R 1…".
RE_LINHA = re.compile(
    r"(?<![A-Za-z0-9])("
    + "|".join(re.escape(c).replace(r"\ ", r"\s*") for c in sorted(CODIGOS, key=len, reverse=True))
    + r")\s+(\d[\d.,\s]*)$"
)
RE_VALOR = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}")
RE_ANO = re.compile(r"C.digo\s+((?:19|20)\d{2})\b")
RE_LINK = re.compile(r'<a\b[^>]*\bhref="([^"]+\.pdf)"[^>]*>(.*?)</a>', re.I | re.S)
RE_TITULO = re.compile(r"CUB/m[²2]/RS[^<]*Divulgado em[^<]*", re.I)


def sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").lower()


def baixar(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def localizar_pdf():
    """Devolve (url_do_pdf, título da divulgação) da série histórica mais recente."""
    pagina = baixar(PAGINA).decode("utf-8", errors="replace")
    for m in RE_LINK.finditer(pagina):
        rotulo = sem_acento(html.unescape(re.sub(r"<[^>]+>", "", m.group(2))))
        if "serie historica" in rotulo and "valor" in rotulo:
            titulos = RE_TITULO.findall(pagina[: m.start()])
            titulo = html.unescape(titulos[-1]).strip() if titulos else ""
            return urllib.parse.urljoin(PAGINA, html.unescape(m.group(1))), titulo
    raise SystemExit('ERRO: link "Série Histórica – Valor" não encontrado em ' + PAGINA)


def ler_valores(trecho):
    # O PDF traz espaços soltos dentro dos números ("2 .443,87"); sem eles a
    # leitura da esquerda para a direita é inequívoca (sempre 2 casas decimais).
    return [float(v.replace(".", "").replace(",", ".")) for v in RE_VALOR.findall(re.sub(r"\s+", "", trecho))]


def extrair_serie(pdf_bytes):
    """Devolve {ano: {codigo: [valores na ordem do PDF]}}."""
    bruto = {}
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text() or ""
            ano = RE_ANO.search(texto)
            if not ano:
                continue
            linhas = {}
            for linha in texto.splitlines():
                m = RE_LINHA.search(linha.strip())
                if m:
                    codigo = next(c for c in CODIGOS if c.replace(" ", "") == re.sub(r"\s+", "", m.group(1)))
                    linhas[codigo] = ler_valores(m.group(2))
            if linhas:
                bruto[int(ano.group(1))] = linhas
    return bruto


def montar_serie(bruto):
    """Valida e alinha cada ano em 12 posições (jan..dez, None = não divulgado)."""
    if not bruto:
        raise SystemExit("ERRO: nenhuma tabela reconhecida no PDF (layout mudou?).")
    recente, antigo = max(bruto), min(bruto)
    serie = {}
    for ano in sorted(bruto, reverse=True):
        linhas = bruto[ano]
        tamanhos = {len(v) for v in linhas.values()}
        ok = set(linhas) == set(CODIGOS) and len(tamanhos) == 1 and 1 <= min(tamanhos) <= 12
        n = min(tamanhos) if ok else 0
        # Só o ano corrente (meses ainda não divulgados) e o primeiro ano da
        # série (começa em fevereiro/2007) podem ter menos de 12 valores.
        if ok and n < 12 and ano not in (recente, antigo):
            ok = False
        if not ok:
            if ano == recente:
                faltando = sorted(set(CODIGOS) - set(linhas))
                raise SystemExit(
                    f"ERRO: tabela de {ano} inconsistente (faltando: {faltando}; "
                    f"quantidades de valores: {sorted(tamanhos)}). cub.js não foi alterado."
                )
            print(f"AVISO: ano {ano} ignorado (tabela inconsistente).", file=sys.stderr)
            continue
        vazio = [None] * (12 - n)
        serie[str(ano)] = {
            c: (linhas[c] + vazio if ano == recente else vazio + linhas[c]) for c in CODIGOS
        }
    return serie


def ler_atual():
    try:
        texto = SAIDA.read_text(encoding="utf-8")
        return json.loads(texto[texto.index("{") : texto.rindex("}") + 1])
    except (OSError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pdf", help="usa um PDF local em vez de buscar no site")
    args = ap.parse_args()

    if args.pdf:
        url_pdf, titulo = Path(args.pdf).name, ""
        pdf_bytes = Path(args.pdf).read_bytes()
    else:
        url_pdf, titulo = localizar_pdf()
        print("PDF:", url_pdf)
        pdf_bytes = baixar(url_pdf)

    serie = montar_serie(extrair_serie(pdf_bytes))
    ano = max(serie, key=int)
    mes = max(i for i, v in enumerate(serie[ano]["R 1-N"]) if v is not None) + 1
    referencia = f"{ano}-{mes:02d}"

    atual = ler_atual()
    if atual and atual.get("serie") == serie and atual.get("fonte", {}).get("pdf") == url_pdf:
        print(f"Sem alteração (referência {referencia}).")
        return

    dados = {
        "atualizadoEm": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "referencia": referencia,
        "fonte": {"pagina": PAGINA, "pdf": url_pdf, "divulgacao": titulo},
        "projetos": [{"codigo": c, "descricao": d, "ocupacao": o} for c, d, o in PROJETOS],
        "serie": serie,
    }
    corpo = json.dumps(dados, ensure_ascii=False, indent=1)
    # Uma linha por projeto/ano em vez de um número por linha.
    corpo = re.sub(r"\[\s+([^\[\]{}]*?)\s+\]", lambda m: "[" + re.sub(r"\s+", " ", m.group(1)) + "]", corpo)
    SAIDA.write_text(
        "// Gerado por scripts/atualizar_cub.py - não editar à mão.\n" + PREFIXO_JS + corpo + ";\n",
        encoding="utf-8",
    )
    print(f"cub.js atualizado: referência {referencia}, R 1-N = {serie[ano]['R 1-N'][mes - 1]:.2f}, {len(serie)} anos.")


if __name__ == "__main__":
    main()
