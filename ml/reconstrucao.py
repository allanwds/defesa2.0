"""Reconstrução (imputação) dos períodos sem cadastro.

A base do sistema tem meses inteiros sem registro (ver notebook 01, seção 4).
Este módulo estima quantas ocorrências houve por dia e distrito nesses
períodos, usando um modelo de contagem ajustado nos dias com cadastro completo:

    ocorrências(dia, distrito) ~ Binomial Negativa(μ, α)
    log μ = distrito + dia da semana + verão + estação chuvosa + chuva acumulada (1, 3, 7 e 14 dias)

A binomial negativa reproduz a variabilidade real das contagens (dias calmos e
dias de pico), que uma Poisson subestimaria.

Regras que tornam a reconstrução defensável:

- O modelo é ajustado **só com dados reais anteriores ao período de teste**,
  para que a avaliação dos modelos de previsão continue honesta.
- São geradas várias versões (imputação múltipla), cada uma com o modelo
  reajustado numa reamostragem por semanas, para carregar a incerteza.
- Onde a numeração oficial revela o total de ocorrências do período
  (fevereiro a maio de 2026), as versões respeitam esse total.
- Cada linha reconstruída é marcada (``origem = "estimado"``). As métricas
  dos modelos são sempre calculadas só em semanas reais.
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import PoissonRegressor

from .chuva import acumulados
from .limpeza import PERIODOS_COMPLETOS

DISTRITOS = ["Jardim São Luís", "Jardim Ângela"]
JANELAS_CHUVA = (1, 3, 7, 14)

# Períodos sem cadastro. ``total`` é o número de ocorrências do período quando a
# numeração oficial o revela: em 2026 o cadastro para no número 127 (03/02) e
# volta com os números 379 e 380 (07 e 08/05). Os 251 números intermediários
# são ocorrências que existiram e não foram cadastradas.
LACUNAS = [
    {"inicio": "2024-03-01", "fim": "2024-12-31", "total": None},
    {"inicio": "2025-10-08", "fim": "2025-12-31", "total": None},
    {"inicio": "2026-02-04", "fim": "2026-05-08", "total": 251},
]
FIM_DA_SERIE = "2026-05-08"


def contagens_diarias_reais(oc: pd.DataFrame) -> pd.DataFrame:
    """Contagem por dia e distrito em todos os dias dos períodos completos (zeros incluídos)."""
    dias = pd.DatetimeIndex(np.concatenate([pd.date_range(i, f) for i, f in PERIODOS_COMPLETOS]))
    grade = pd.MultiIndex.from_product([dias, DISTRITOS], names=["data", "distrito"]).to_frame(index=False)
    contagem = oc[oc["periodo_completo"]].groupby(["data", "distrito_padrao"]).size().rename("ocorrencias")
    grade = grade.join(contagem, on=["data", "distrito"])
    grade["ocorrencias"] = grade["ocorrencias"].fillna(0).astype(int)
    return grade


class ModeloDemandaDiaria:
    """Regressão de contagem (Poisson com sobredispersão estimada à parte)."""

    def __init__(self, chuva_diaria: pd.DataFrame, regularizacao: float = 1e-3):
        self.chuva = acumulados(chuva_diaria, JANELAS_CHUVA).set_index("data")
        self.regularizacao = regularizacao

    def variaveis(self, df: pd.DataFrame) -> pd.DataFrame:
        data, mes = df["data"], df["data"].dt.month
        X = pd.DataFrame({
            "sao_luis": (df["distrito"] == "Jardim São Luís").astype(int).to_numpy(),
            "verao": mes.isin({1, 2}).astype(int).to_numpy(),
            "estacao_chuvosa": mes.isin({10, 11, 12, 1, 2, 3}).astype(int).to_numpy(),
        })
        for k, nome in enumerate(["seg", "ter", "qua", "qui", "sex", "sab"]):
            X[nome] = (data.dt.dayofweek == k).astype(int).to_numpy()
        chuva = self.chuva.reindex(data)
        for n in JANELAS_CHUVA:
            coluna = chuva[f"chuva_{n}d"]
            X[f"log_chuva_{n}d"] = np.log1p(coluna.fillna(coluna.median())).to_numpy()
        return X

    def fit(self, df: pd.DataFrame):
        X, y = self.variaveis(df), df["ocorrencias"].to_numpy()
        self.glm_ = PoissonRegressor(alpha=self.regularizacao, max_iter=5000).fit(X, y)
        mu = self.glm_.predict(X)
        # Sobredispersão pelo método dos momentos: Var(y) = μ + α μ²
        self.alpha_ = max(0.0, float((((y - mu) ** 2 - y).sum()) / (mu ** 2).sum()))
        return self

    def media(self, df: pd.DataFrame) -> np.ndarray:
        return self.glm_.predict(self.variaveis(df))

    def taxas(self, df: pd.DataFrame, rng) -> np.ndarray:
        """Taxas diárias sorteadas (média com o ruído gama da binomial negativa)."""
        mu = self.media(df)
        if self.alpha_ == 0:
            return mu
        return rng.gamma(1 / self.alpha_, self.alpha_ * mu)

    def simular(self, df: pd.DataFrame, rng, total=None) -> np.ndarray:
        """Uma realização das contagens. Com ``total``, distribui exatamente esse total."""
        taxas = self.taxas(df, rng)
        if total is None:
            return rng.poisson(taxas)
        return rng.multinomial(total, taxas / taxas.sum())


def _reamostrar_semanas(df: pd.DataFrame, rng) -> pd.DataFrame:
    semanas = df["data"].dt.to_period("W-SUN")
    unicas = semanas.unique()
    sorteadas = rng.choice(unicas, len(unicas), replace=True)
    return pd.concat([df[semanas == s] for s in sorteadas], ignore_index=True)


def reconstruir(oc: pd.DataFrame, chuva_diaria: pd.DataFrame, ajuste_ate, versoes: int = 10,
                semente: int = 0) -> pd.DataFrame:
    """Série diária contínua por distrito, de 01/01/2024 até ``FIM_DA_SERIE``, em várias versões.

    ``ajuste_ate``: só os dias reais anteriores a esta data ajustam o modelo.
    Devolve colunas data, distrito, versao, ocorrencias e origem ("real" ou "estimado").
    Os dias reais são idênticos em todas as versões.
    """
    rng = np.random.default_rng(semente)
    reais = contagens_diarias_reais(oc)
    treino = reais[reais["data"] < pd.Timestamp(ajuste_ate)]

    # Registros reais isolados dentro das lacunas (ex.: 07 e 08/05/2026) são somados à estimativa.
    avulsos = oc[~oc["periodo_completo"]].groupby(["data", "distrito_padrao"]).size()

    partes = []
    for v in range(versoes):
        modelo = ModeloDemandaDiaria(chuva_diaria).fit(_reamostrar_semanas(treino, rng))
        partes.append(reais.assign(versao=v, origem="real"))
        for lacuna in LACUNAS:
            dias = pd.date_range(lacuna["inicio"], lacuna["fim"])
            grade = pd.MultiIndex.from_product([dias, DISTRITOS], names=["data", "distrito"]).to_frame(index=False)
            grade["ocorrencias"] = modelo.simular(grade, rng, lacuna["total"])
            extra = avulsos.reindex(pd.MultiIndex.from_frame(grade[["data", "distrito"]])).fillna(0).to_numpy()
            grade["ocorrencias"] = grade["ocorrencias"] + extra.astype(int)
            partes.append(grade.assign(versao=v, origem="estimado"))

    serie = pd.concat(partes, ignore_index=True)
    serie = serie[serie["data"] <= pd.Timestamp(FIM_DA_SERIE)]
    return serie.sort_values(["versao", "distrito", "data"]).reset_index(drop=True)
