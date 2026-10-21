"""Carregamento das ocorrências a partir da API pública do sistema.

A API devolve as ocorrências em JSON sem exigir credenciais, então o mesmo
código funciona localmente e no Google Colab. O resultado é guardado em
``ml/dados/`` (fora do git) para não depender da API a cada execução.
"""

from pathlib import Path

import pandas as pd
import requests

API_URL = "https://defesa2-0.onrender.com/api/ocorrencias/"

DIR_DADOS = Path(__file__).resolve().parent / "dados"
CACHE_BRUTO = DIR_DADOS / "ocorrencias_bruto.csv"


def baixar_ocorrencias(url: str = API_URL, timeout: int = 180) -> pd.DataFrame:
    """Baixa todas as ocorrências da API, seguindo a paginação se houver.

    O timeout é alto porque o Render hiberna o serviço gratuito e a primeira
    requisição pode levar mais de um minuto.
    """
    registros = []
    while url:
        resp = requests.get(url, headers={"Accept": "application/json"}, timeout=timeout)
        resp.raise_for_status()
        dados = resp.json()
        if isinstance(dados, list):
            registros.extend(dados)
            url = None
        else:
            registros.extend(dados["results"])
            url = dados.get("next")
    return pd.DataFrame(registros)


def carregar_ocorrencias(atualizar: bool = False) -> pd.DataFrame:
    """Devolve as ocorrências brutas, usando o cache local quando existir."""
    if CACHE_BRUTO.exists() and not atualizar:
        df = pd.read_csv(CACHE_BRUTO)
    else:
        df = baixar_ocorrencias()
        DIR_DADOS.mkdir(exist_ok=True)
        df.to_csv(CACHE_BRUTO, index=False)
    df["data"] = pd.to_datetime(df["data"])
    return df
