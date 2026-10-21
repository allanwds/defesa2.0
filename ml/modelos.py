"""Modelos, referências simples e avaliação temporal.

As referências simples seguem a interface do scikit-learn (``fit``/``predict``)
para serem avaliadas exatamente como os modelos: um modelo só tem valor se
superá-las no mesmo conjunto de teste.
"""

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin, RegressorMixin
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    log_loss,
    mean_absolute_error,
    root_mean_squared_error,
)
from sklearn.pipeline import make_pipeline

SEMENTE = 0


# ---------------------------------------------------------------- referências

class UltimaSemana(RegressorMixin, BaseEstimator):
    """Prevê que a próxima semana repete a anterior."""

    def fit(self, X, y):
        return self

    def predict(self, X):
        return X["lag1"].to_numpy(dtype=float)


class MediaMovel(RegressorMixin, BaseEstimator):
    """Prevê a média das até 4 semanas anteriores."""

    def fit(self, X, y):
        return self

    def predict(self, X):
        return X["media4"].to_numpy(dtype=float)


class MediaHistorica(RegressorMixin, BaseEstimator):
    """Prevê a média semanal do distrito em todo o histórico de treino."""

    def fit(self, X, y):
        self.medias_ = pd.Series(np.asarray(y, dtype=float), index=X.index).groupby(X["sao_luis"]).mean()
        return self

    def predict(self, X):
        return X["sao_luis"].map(self.medias_).to_numpy(dtype=float)


class ClasseMaisFrequente(ClassifierMixin, BaseEstimator):
    """Prevê sempre a classe mais frequente, com as proporções do treino como probabilidade."""

    def fit(self, X, y):
        freq = pd.Series(y).value_counts(normalize=True).sort_index()
        self.classes_ = freq.index.to_numpy()
        self.proporcoes_ = freq.to_numpy()
        return self

    def predict(self, X):
        return np.full(len(X), self.classes_[self.proporcoes_.argmax()])

    def predict_proba(self, X):
        return np.tile(self.proporcoes_, (len(X), 1))


# ---------------------------------------------------------------- modelos

def regressor(min_samples_leaf: int = 5) -> RandomForestRegressor:
    return RandomForestRegressor(
        n_estimators=500, min_samples_leaf=min_samples_leaf, random_state=SEMENTE, n_jobs=-1
    )


class ClassificadorGrupo(ClassifierMixin, BaseEstimator):
    """Random Forest para o grupo do motivo.

    O treino usa pesos de classe balanceados, para que as classes pequenas
    (Hidrológico, Geológico) não sejam ignoradas nas decisões de ``predict``.
    Esses pesos fazem o modelo agir como se todas as classes fossem igualmente
    frequentes, o que distorce as probabilidades. Por isso ``predict_proba``
    reajusta as probabilidades às proporções reais das classes no treino.
    Coordenadas ausentes são imputadas pela mediana.
    """

    def __init__(self, min_samples_leaf: int = 10, max_features="sqrt"):
        self.min_samples_leaf = min_samples_leaf
        self.max_features = max_features

    def fit(self, X, y):
        self.modelo_ = make_pipeline(
            SimpleImputer(strategy="median"),
            RandomForestClassifier(
                n_estimators=500,
                min_samples_leaf=self.min_samples_leaf,
                max_features=self.max_features,
                class_weight="balanced",
                random_state=SEMENTE,
                n_jobs=-1,
            ),
        ).fit(X, y)
        self.classes_ = self.modelo_.classes_
        self.proporcoes_ = pd.Series(y).value_counts(normalize=True).reindex(self.classes_).to_numpy()
        return self

    def predict(self, X):
        return self.modelo_.predict(X)

    def predict_proba_balanceada(self, X):
        """Probabilidades sem o reajuste (como se as classes fossem igualmente frequentes)."""
        return self.modelo_.predict_proba(X)

    def predict_proba(self, X):
        p = self.modelo_.predict_proba(X) * self.proporcoes_
        return p / p.sum(axis=1, keepdims=True)


# ---------------------------------------------------------------- avaliação

def previsao_passo_a_passo(painel: pd.DataFrame, semanas_alvo, modelos: dict, variaveis: list) -> pd.DataFrame:
    """Avaliação "walk-forward": para cada semana alvo, treina com todas as
    semanas anteriores e prevê aquela semana, como aconteceria na prática.

    ``modelos`` mapeia nome -> função sem argumentos que devolve um estimador novo.
    Devolve as linhas das semanas alvo com uma coluna de previsão por modelo.
    """
    saida = []
    for semana in semanas_alvo:
        treino = painel[painel["semana"] < semana]
        alvo = painel[painel["semana"] == semana].copy()
        for nome, fabrica in modelos.items():
            modelo = fabrica().fit(treino[variaveis], treino["ocorrencias"])
            alvo[nome] = modelo.predict(alvo[variaveis])
        saida.append(alvo)
    return pd.concat(saida, ignore_index=True)


def metricas_regressao(real, previsto) -> dict:
    return {
        "MAE": mean_absolute_error(real, previsto),
        "RMSE": root_mean_squared_error(real, previsto),
    }


def metricas_classificacao(real, previsto, probabilidades, classes) -> dict:
    return {
        "acurácia": accuracy_score(real, previsto),
        "acurácia balanceada": balanced_accuracy_score(real, previsto),
        "F1 macro": f1_score(real, previsto, average="macro"),
        "log loss": log_loss(real, probabilidades, labels=classes),
    }


def intervalo_bootstrap(diferenca, n: int, grupos=None, repeticoes: int = 2000, nivel: float = 0.95):
    """Intervalo de confiança por bootstrap pareado de uma diferença entre dois modelos.

    ``diferenca(indices)`` calcula a diferença (modelo B menos modelo A) nas
    linhas reamostradas. Com ``grupos`` (por exemplo, a semana de cada linha),
    a reamostragem sorteia grupos inteiros, preservando a dependência dentro deles.
    """
    rng = np.random.default_rng(SEMENTE)
    if grupos is None:
        amostras = (rng.integers(0, n, n) for _ in range(repeticoes))
    else:
        grupos = np.asarray(grupos)
        indices = [np.flatnonzero(grupos == g) for g in np.unique(grupos)]
        amostras = (
            np.concatenate([indices[i] for i in rng.integers(0, len(indices), len(indices))])
            for _ in range(repeticoes)
        )
    valores = np.array([diferenca(i) for i in amostras])
    alfa = (1 - nivel) / 2
    return np.quantile(valores, [alfa, 1 - alfa])


# ---------------------------------------------------------------- protocolo completo
# Mesmo protocolo do notebook 02, empacotado para comparar conjuntos de variáveis:
# hiperparâmetro escolhido na validação, teste usado uma única vez.

def avaliar_regressao(painel, variaveis, inicio_validacao, inicio_teste, folhas=(1, 3, 5, 10, 20)) -> dict:
    semanas = np.sort(painel["semana"].unique())
    validacao = semanas[(semanas >= inicio_validacao) & (semanas < inicio_teste)]
    teste = semanas[semanas >= inicio_teste]

    candidatos = {str(n): (lambda n=n: regressor(n)) for n in folhas}
    prev_val = previsao_passo_a_passo(painel, validacao, candidatos, variaveis)
    mae_validacao = {int(n): mean_absolute_error(prev_val["ocorrencias"], prev_val[n]) for n in candidatos}
    folha = min(mae_validacao, key=mae_validacao.get)

    prev_teste = previsao_passo_a_passo(painel, teste, {"previsto": lambda: regressor(folha)}, variaveis)
    return {
        "min_samples_leaf": folha,
        "mae_validacao": mae_validacao[folha],
        "teste": prev_teste,
        "metricas_teste": metricas_regressao(prev_teste["ocorrencias"], prev_teste["previsto"]),
    }


def avaliar_classificacao(tabela, variaveis, inicio_validacao, inicio_teste, alvo="grupo_motivo",
                          folhas=(1, 3, 5, 10, 20), max_features=("sqrt", None)) -> dict:
    treino = tabela[tabela["data"] < inicio_validacao]
    validacao = tabela[(tabela["data"] >= inicio_validacao) & (tabela["data"] < inicio_teste)]
    teste = tabela[tabela["data"] >= inicio_teste]

    resultados = []
    for folha in folhas:
        for mf in max_features:
            modelo = ClassificadorGrupo(folha, mf).fit(treino[variaveis], treino[alvo])
            resultados.append({
                "min_samples_leaf": folha,
                "max_features": mf,
                **metricas_classificacao(validacao[alvo], modelo.predict(validacao[variaveis]),
                                         modelo.predict_proba(validacao[variaveis]), modelo.classes_),
            })
    escolha = max(resultados, key=lambda r: (r["F1 macro"], -r["log loss"]))
    folha, mf = escolha["min_samples_leaf"], escolha["max_features"]

    treino_final = tabela[tabela["data"] < inicio_teste]
    modelo = ClassificadorGrupo(folha, mf).fit(treino_final[variaveis], treino_final[alvo])
    previsto = modelo.predict(teste[variaveis])
    probabilidades = modelo.predict_proba(teste[variaveis])
    return {
        "min_samples_leaf": folha,
        "max_features": mf,
        "f1_validacao": escolha["F1 macro"],
        "modelo": modelo,
        "previsto": previsto,
        "probabilidades": probabilidades,
        "metricas_teste": metricas_classificacao(teste[alvo], previsto, probabilidades, modelo.classes_),
    }
