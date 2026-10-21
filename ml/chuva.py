"""Chuva observada pelo INMET na estação automática mais próxima de M'Boi Mirim.

Fonte: BDMEP/INMET, arquivos anuais com os dados horários de todas as
estações automáticas do país (``portal.inmet.gov.br/dadoshistoricos``). Cada
arquivo tem mais de 100 MB, mas o servidor aceita requisições parciais (HTTP
Range). Por isso só o índice do zip e o CSV da estação escolhida são baixados
(algumas centenas de KB por ano).

Estação padrão: A771, São Paulo – Interlagos (-23,724; -46,677), cerca de
9 km a leste do centro de M'Boi Mirim. O CEMADEN tem pluviômetros dentro da
região, mas o acesso exige cadastro e aprovação na plataforma PED
(ped.cemaden.gov.br). Ver notebook 03.
"""

import io
import zipfile

import numpy as np
import pandas as pd
import requests

from .dados import DIR_DADOS

ESTACAO = "A771"
URL_BDMEP = "https://portal.inmet.gov.br/uploads/dadoshistoricos/{ano}.zip"

# O servidor do INMET derruba conexões com o User-Agent padrão de bibliotecas HTTP.
_CABECALHOS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
}

# Um dia só tem total de chuva quando a maioria das horas foi medida.
HORAS_MINIMAS_POR_DIA = 18


class _ArquivoRemoto(io.RawIOBase):
    """Arquivo somente leitura sobre HTTP, lido por partes com o cabeçalho Range."""

    def __init__(self, url: str, timeout: int = 120):
        self.url = url
        self.timeout = timeout
        self.posicao = 0
        resposta = requests.head(url, headers=_CABECALHOS, timeout=timeout, allow_redirects=True)
        resposta.raise_for_status()
        self.tamanho = int(resposta.headers["Content-Length"])

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.posicao

    def seek(self, deslocamento, origem=io.SEEK_SET):
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.posicao, io.SEEK_END: self.tamanho}[origem]
        self.posicao = base + deslocamento
        return self.posicao

    def readinto(self, buffer):
        if self.posicao >= self.tamanho:
            return 0
        fim = min(self.posicao + len(buffer), self.tamanho) - 1
        resposta = requests.get(
            self.url, headers=_CABECALHOS | {"Range": f"bytes={self.posicao}-{fim}"}, timeout=self.timeout
        )
        resposta.raise_for_status()
        dados = resposta.content
        buffer[: len(dados)] = dados
        self.posicao += len(dados)
        return len(dados)


def _baixar_csv_estacao(ano: int, estacao: str) -> bytes:
    remoto = io.BufferedReader(_ArquivoRemoto(URL_BDMEP.format(ano=ano)), buffer_size=1 << 16)
    with zipfile.ZipFile(remoto) as arquivo:
        nomes = [n for n in arquivo.namelist() if f"_{estacao}_" in n]
        if not nomes:
            raise ValueError(f"Estação {estacao} não encontrada no arquivo de {ano}")
        return arquivo.read(nomes[0])


def _ler_csv_bdmep(conteudo: bytes) -> pd.DataFrame:
    """Converte o CSV horário do BDMEP em (momento em horário de Brasília, chuva em mm)."""
    df = pd.read_csv(io.BytesIO(conteudo), sep=";", decimal=",", encoding="latin-1", skiprows=8,
                     dtype=str)
    col_data = next(c for c in df.columns if c.lower().startswith("data"))
    col_hora = next(c for c in df.columns if c.lower().startswith("hora"))
    col_chuva = next(c for c in df.columns if "PRECIPITA" in c.upper())

    # A hora vem como "0000 UTC" (anos recentes) ou "00:00" (anos antigos).
    hora = df[col_hora].str.replace(r"\D", "", regex=True).str[:4].str.zfill(4)
    utc = pd.to_datetime(df[col_data].str.replace("/", "-") + " " + hora, format="%Y-%m-%d %H%M")
    chuva = pd.to_numeric(df[col_chuva].str.replace(",", "."), errors="coerce")
    chuva = chuva.where(chuva >= 0)  # -9999 indica falha do sensor
    return pd.DataFrame({"momento": utc - pd.Timedelta(hours=3), "chuva_mm": chuva})


def chuva_horaria(anos, estacao: str = ESTACAO, atualizar: bool = False) -> pd.DataFrame:
    """Chuva horária (horário de Brasília) dos anos pedidos, com cache em ``ml/dados``.

    O arquivo do ano corrente é atualizado pelo INMET ao longo do ano. Use
    ``atualizar=True`` para baixá-lo de novo.
    """
    partes = []
    for ano in anos:
        cache = DIR_DADOS / f"chuva_{estacao}_{ano}.csv"
        if cache.exists() and not atualizar:
            parte = pd.read_csv(cache, parse_dates=["momento"])
        else:
            parte = _ler_csv_bdmep(_baixar_csv_estacao(ano, estacao))
            DIR_DADOS.mkdir(exist_ok=True)
            parte.to_csv(cache, index=False)
        partes.append(parte)
    return pd.concat(partes, ignore_index=True).sort_values("momento").reset_index(drop=True)


def chuva_diaria(anos, estacao: str = ESTACAO, atualizar: bool = False) -> pd.DataFrame:
    """Total diário de chuva (mm) por dia de calendário em horário de Brasília.

    Dias com menos de ``HORAS_MINIMAS_POR_DIA`` horas medidas ficam com total nulo.
    """
    horaria = chuva_horaria(anos, estacao, atualizar)
    horaria["data"] = horaria["momento"].dt.normalize()
    diaria = horaria.groupby("data").agg(chuva_mm=("chuva_mm", "sum"), horas_medidas=("chuva_mm", "count"))
    diaria.loc[diaria["horas_medidas"] < HORAS_MINIMAS_POR_DIA, "chuva_mm"] = np.nan
    todos_os_dias = pd.date_range(diaria.index.min(), diaria.index.max(), freq="D", name="data")
    diaria = diaria.reindex(todos_os_dias)
    diaria["horas_medidas"] = diaria["horas_medidas"].fillna(0).astype(int)
    return diaria.reset_index()


def acumulados(diaria: pd.DataFrame, janelas=(1, 3, 7)) -> pd.DataFrame:
    """Chuva acumulada nos últimos N dias (incluindo o próprio dia), por dia.

    Uma janela com algum dia sem medição fica nula, para não subestimar a chuva.
    """
    serie = diaria.set_index("data")["chuva_mm"]
    saida = pd.DataFrame(index=serie.index)
    for n in janelas:
        saida[f"chuva_{n}d"] = serie.rolling(n, min_periods=n).sum()
    return saida.reset_index()
