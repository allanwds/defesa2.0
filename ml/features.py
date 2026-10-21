"""Tabelas de treino dos dois modelos.

- ``painel_semanal``: contagem de ocorrências por semana × distrito (regressão).
- ``tabela_classificacao``: uma linha por ocorrência com as variáveis do grupo
  do motivo (classificação).

Só entram semanas e ocorrências dos períodos com cadastro completo
(``limpeza.PERIODOS_COMPLETOS``). As variáveis defasadas nunca atravessam a
fronteira entre dois períodos, porque o intervalo entre eles não tem dados.
"""

import pandas as pd

from .chuva import acumulados
from .limpeza import semanas_completas

# Estação chuvosa em São Paulo: outubro a março.
MESES_CHUVOSOS = {10, 11, 12, 1, 2, 3}

VARIAVEIS_REGRESSAO = ["sao_luis", "estacao_chuvosa", "verao", "lag1", "media4", "total_lag1"]
VARIAVEIS_CLASSIFICACAO = ["area_risco", "estacao_chuvosa", "verao", "dia_util", "sao_luis", "latitude", "longitude"]

# Chuva já observada antes da semana prevista: pode ser usada na prática.
CHUVA_SEMANA_ANTERIOR = ["chuva_sem_ant", "chuva_max_sem_ant"]
# Chuva da própria semana prevista: na prática viria da previsão do tempo.
# Avaliá-la com a chuva observada mede o ganho máximo de uma previsão perfeita.
CHUVA_SEMANA_PREVISTA = ["chuva_sem", "chuva_max_sem"]
CHUVA_OCORRENCIA = ["chuva_1d", "chuva_3d", "chuva_7d"]


def _calendario(datas: pd.Series) -> pd.DataFrame:
    mes = datas.dt.month
    return pd.DataFrame({
        "estacao_chuvosa": mes.isin(MESES_CHUVOSOS).astype(int),
        "verao": mes.isin({1, 2}).astype(int),
    }, index=datas.index)


def painel_semanal(oc: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por semana completa e distrito, com a contagem e as defasagens.

    ``lag1`` é a contagem da semana anterior no distrito, ``media4`` a média das
    até 4 semanas anteriores e ``total_lag1`` a contagem da semana anterior nos
    dois distritos. A primeira semana de cada período fica sem defasagem e é
    descartada.
    """
    semanas = semanas_completas()
    distritos = pd.DataFrame({"distrito": sorted(oc["distrito_padrao"].unique())})
    painel = semanas.merge(distritos, how="cross")

    contagem = oc.groupby(["semana", "distrito_padrao"]).size().rename("ocorrencias")
    painel = painel.join(contagem, on=["semana", "distrito"])
    painel["ocorrencias"] = painel["ocorrencias"].fillna(0).astype(int)
    return _defasagens_e_calendario(painel)


def painel_semanal_continuo(serie: pd.DataFrame) -> pd.DataFrame:
    """Painel semana × distrito a partir de uma série diária contínua.

    ``serie`` é uma versão de ``reconstrucao.reconstruir`` (colunas data,
    distrito, ocorrencias, origem). Como não há buracos, as defasagens são
    contínuas. ``semana_real`` indica as semanas com os 7 dias reais: só elas
    servem para avaliar modelos.
    """
    s = serie.assign(semana=serie["data"].dt.to_period("W-SUN").dt.start_time,
                     real=serie["origem"].eq("real"))
    painel = s.groupby(["semana", "distrito"]).agg(
        ocorrencias=("ocorrencias", "sum"), dias=("data", "nunique"), dias_reais=("real", "sum")
    ).reset_index()
    painel = painel[painel["dias"] == 7].copy()
    painel["semana_real"] = painel["dias_reais"] == 7
    painel["bloco"] = 0
    return _defasagens_e_calendario(painel.drop(columns=["dias", "dias_reais"]))


def _defasagens_e_calendario(painel: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta lag1, media4, total_lag1, sao_luis e o calendário; descarta linhas sem lag1."""
    painel = painel.sort_values(["distrito", "semana"]).reset_index(drop=True)

    por_serie = painel.groupby(["distrito", "bloco"])["ocorrencias"]
    painel["lag1"] = por_serie.shift(1)
    painel["media4"] = por_serie.transform(lambda s: s.shift(1).rolling(4, min_periods=1).mean())

    total = painel.groupby(["bloco", "semana"])["ocorrencias"].sum()
    total_lag1 = total.groupby(level="bloco").shift(1).rename("total_lag1")
    painel = painel.join(total_lag1, on=["bloco", "semana"])

    painel["sao_luis"] = (painel["distrito"] == "Jardim São Luís").astype(int)
    painel = painel.join(_calendario(painel["semana"]))
    return painel.dropna(subset=["lag1"]).reset_index(drop=True)


def tabela_classificacao(oc: pd.DataFrame) -> pd.DataFrame:
    """Ocorrências dos períodos completos com as variáveis da classificação.

    Latitude e longitude podem ser nulas (coordenadas inválidas). O pipeline
    do modelo é responsável por imputá-las.
    """
    tabela = oc[oc["periodo_completo"]].copy()
    tabela = tabela.join(_calendario(tabela["data"]))
    tabela["dia_util"] = (tabela["dia_semana"] < 5).astype(int)
    tabela["sao_luis"] = (tabela["distrito_padrao"] == "Jardim São Luís").astype(int)
    return tabela.sort_values("data").reset_index(drop=True)


def adicionar_chuva_painel(painel: pd.DataFrame, diaria: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta ao painel semanal o total e o maior dia de chuva da semana
    (``chuva_sem``, ``chuva_max_sem``) e da semana anterior (``*_sem_ant``).

    ``diaria`` vem de ``chuva.chuva_diaria``. As semanas começam na segunda-feira.
    """
    serie = diaria.set_index("data")["chuva_mm"]
    # Intervalos [segunda, próxima segunda), rotulados pela segunda-feira inicial.
    por_semana = serie.resample("W-MON", label="left", closed="left")
    semanal = pd.DataFrame({
        "chuva_sem": por_semana.sum(min_count=7),
        "chuva_max_sem": por_semana.max(),
    })
    semanal["chuva_sem_ant"] = semanal["chuva_sem"].shift(1)
    semanal["chuva_max_sem_ant"] = semanal["chuva_max_sem"].shift(1)
    return painel.join(semanal, on="semana")


def adicionar_chuva_ocorrencias(tabela: pd.DataFrame, diaria: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta a chuva acumulada em 1, 3 e 7 dias até a data de cada ocorrência."""
    return tabela.merge(acumulados(diaria), on="data", how="left")
