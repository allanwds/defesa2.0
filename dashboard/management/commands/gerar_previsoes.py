from datetime import date

import numpy as np
import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction

from dashboard.models import ExecucaoModelo, PrevisaoDemanda, ProbabilidadeTipo
from ml import modelos as M
from ml.features import (
    VARIAVEIS_CLASSIFICACAO,
    VARIAVEIS_REGRESSAO,
    painel_semanal,
    tabela_classificacao,
)
from ml.limpeza import PERIODOS_COMPLETOS, limpar, marcar_periodos, ocorrencias_validas
from ocorrencias.models import Ocorrencia

INICIO_TESTE = pd.Timestamp("2025-07-01")
VARIAVEIS_CALENDARIO = ["sao_luis", "estacao_chuvosa", "verao"]
MIN_LEAF_REG = 5
MIN_LEAF_CLS, MAX_FEATURES_CLS = 10, None
TOLERANCIA_SEMANAS = 2

EPOCAS = {"verao": (1, 1), "chuvosa": (1, 0), "seca": (0, 0)}


def _calendario(mes: int) -> dict:
    return {
        "estacao_chuvosa": int(mes in {10, 11, 12, 1, 2, 3}),
        "verao": int(mes in {1, 2}),
    }


def _nivel(valor: float, tercis: tuple) -> str:
    return "baixo" if valor <= tercis[0] else "alto" if valor > tercis[1] else "medio"


class Command(BaseCommand):
    help = "Treina os modelos e grava previsões de demanda e probabilidades por tipo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--como-de",
            help="AAAA-MM-DD: usa só ocorrências até essa data e a trata como 'hoje'.",
        )

    def handle(self, *args, como_de=None, **opts):
        hoje = pd.Timestamp(como_de) if como_de else pd.Timestamp(date.today())
        df = pd.DataFrame(list(Ocorrencia.objects.values()))
        df["data"] = pd.to_datetime(df["data"])
        df = df[df["data"] <= hoje]
        oc = marcar_periodos(ocorrencias_validas(limpar(df)))

        periodos = [
            (a, min(pd.Timestamp(b), hoje))
            for a, b in PERIODOS_COMPLETOS
            if pd.Timestamp(a) <= hoje
        ]
        fim_cobertura = max(pd.Timestamp(b) for _, b in periodos)

        painel = painel_semanal(oc)
        painel = painel[painel["semana"] + pd.Timedelta(days=6) <= fim_cobertura]
        completas = oc[oc["periodo_completo"]]
        classif = tabela_classificacao(oc)

        meta = {
            "referencia": hoje.date().isoformat(),
            "periodos_completos": [
                [a, pd.Timestamp(b).date().isoformat()] for a, b in periodos
            ],
        }
        linhas = []

        semanas_teste = np.sort(
            painel.loc[painel["semana"] >= INICIO_TESTE, "semana"].unique()
        )
        if len(semanas_teste):
            ref = {"rf": lambda: M.regressor(MIN_LEAF_REG), "media_movel": M.MediaMovel}
            teste = M.previsao_passo_a_passo(
                painel, semanas_teste, ref, VARIAVEIS_REGRESSAO
            )
            meta["teste_regressao"] = {
                "semanas": len(semanas_teste),
                "previsoes": len(teste),
                "mae_modelo": round(
                    M.metricas_regressao(teste["ocorrencias"], teste["rf"])["MAE"], 2
                ),
                "mae_media_movel": round(
                    M.metricas_regressao(teste["ocorrencias"], teste["media_movel"])[
                        "MAE"
                    ],
                    2,
                ),
            }
            residuo = (teste["ocorrencias"] - teste["rf"]).to_numpy()
            r_baixo, r_alto = np.quantile(residuo, [0.1, 0.9])
            for _, r in teste.iterrows():
                linhas.append(
                    dict(
                        tipo=PrevisaoDemanda.TESTE,
                        distrito=r["distrito"],
                        referencia=r["semana"].date(),
                        previsto=r["rf"],
                        baixo=max(0, r["rf"] + r_baixo),
                        alto=r["rf"] + r_alto,
                        referencia_media_movel=r["media_movel"],
                        observado=r["ocorrencias"],
                        nivel="",
                    )
                )
        else:
            r_baixo, r_alto = -3.0, 3.0
            meta["teste_regressao"] = None

        proxima = (hoje - pd.Timedelta(days=hoje.dayofweek)).normalize()
        if hoje.dayofweek:
            proxima += pd.Timedelta(days=7)
        defasagem = (proxima - fim_cobertura).days / 7
        meta["proxima_semana_disponivel"] = bool(defasagem <= 1 + TOLERANCIA_SEMANAS)
        meta["fim_cobertura"] = fim_cobertura.date().isoformat()
        tercis = (
            painel.groupby("distrito")["ocorrencias"].quantile([1 / 3, 2 / 3]).unstack()
        )
        modelo_semana = M.regressor(MIN_LEAF_REG).fit(
            painel[VARIAVEIS_REGRESSAO], painel["ocorrencias"]
        )
        if meta["proxima_semana_disponivel"]:
            ultima = painel.sort_values("semana").groupby("distrito").tail(1).copy()
            ultimas4 = painel[
                painel["semana"] >= ultima["semana"].max() - pd.Timedelta(weeks=3)
            ]
            ultima["media4"] = ultima["distrito"].map(
                ultimas4.groupby("distrito")["ocorrencias"].mean()
            )
            ultima["lag1"] = ultima["ocorrencias"]
            ultima["total_lag1"] = ultima["ocorrencias"].sum()
            ultima["estacao_chuvosa"], ultima["verao"] = _calendario(
                proxima.month
            ).values()
            prev = modelo_semana.predict(ultima[VARIAVEIS_REGRESSAO])
            for (_, r), p in zip(ultima.iterrows(), prev):
                linhas.append(
                    dict(
                        tipo=PrevisaoDemanda.PROXIMA_SEMANA,
                        distrito=r["distrito"],
                        referencia=proxima.date(),
                        previsto=p,
                        baixo=max(0, p + r_baixo),
                        alto=p + r_alto,
                        referencia_media_movel=r["media4"],
                        nivel=_nivel(p, tuple(tercis.loc[r["distrito"]])),
                    )
                )

        modelo_cal = M.regressor(MIN_LEAF_REG).fit(
            painel[VARIAVEIS_CALENDARIO], painel["ocorrencias"]
        )
        distritos = sorted(painel["distrito"].unique())
        primeiro_mes = pd.Timestamp(hoje.year, hoje.month, 1)
        for i in range(12):
            mes = primeiro_mes + pd.DateOffset(months=i)
            cal = _calendario(mes.month)
            for dist in distritos:
                X = pd.DataFrame([{"sao_luis": int(dist == "Jardim São Luís"), **cal}])[
                    VARIAVEIS_CALENDARIO
                ]
                p = float(modelo_cal.predict(X)[0])
                grupo = painel[
                    (painel["distrito"] == dist)
                    & (painel["estacao_chuvosa"] == cal["estacao_chuvosa"])
                    & (painel["verao"] == cal["verao"])
                ]["ocorrencias"]
                baixo, alto = (
                    (grupo.quantile(0.1), grupo.quantile(0.9))
                    if len(grupo) >= 5
                    else (p + r_baixo, p + r_alto)
                )
                linhas.append(
                    dict(
                        tipo=PrevisaoDemanda.ESPERADO_MES,
                        distrito=dist,
                        referencia=mes.date(),
                        previsto=p,
                        baixo=float(baixo),
                        alto=float(alto),
                        nivel=_nivel(p, tuple(tercis.loc[dist])),
                    )
                )

        corte = INICIO_TESTE
        treino_c, teste_c = (
            classif[classif["data"] < corte],
            classif[classif["data"] >= corte],
        )
        if len(teste_c) and treino_c["grupo_motivo"].nunique() > 1:
            c = M.ClassificadorGrupo(MIN_LEAF_CLS, MAX_FEATURES_CLS).fit(
                treino_c[VARIAVEIS_CLASSIFICACAO], treino_c["grupo_motivo"]
            )
            base = M.ClasseMaisFrequente().fit(
                treino_c[VARIAVEIS_CLASSIFICACAO], treino_c["grupo_motivo"]
            )
            X = teste_c[VARIAVEIS_CLASSIFICACAO]
            m = M.metricas_classificacao(
                teste_c["grupo_motivo"], c.predict(X), c.predict_proba(X), c.classes_
            )
            b = M.metricas_classificacao(
                teste_c["grupo_motivo"],
                base.predict(X),
                base.predict_proba(X),
                base.classes_,
            )
            meta["teste_classificacao"] = {
                "ocorrencias_teste": len(teste_c),
                "modelo": {k: round(v, 3) for k, v in m.items()},
                "classe_mais_frequente": {k: round(v, 3) for k, v in b.items()},
            }
        else:
            meta["teste_classificacao"] = None
        classificador = M.ClassificadorGrupo(MIN_LEAF_CLS, MAX_FEATURES_CLS).fit(
            classif[VARIAVEIS_CLASSIFICACAO], classif["grupo_motivo"]
        )
        probs = []
        for area, g in classif.groupby("area_risco"):
            for epoca, (chuvosa, verao) in EPOCAS.items():
                x = pd.DataFrame(
                    [
                        {
                            "area_risco": area,
                            "estacao_chuvosa": chuvosa,
                            "verao": verao,
                            "dia_util": 1,
                            "sao_luis": int(round(g["sao_luis"].mean())),
                            "latitude": g["latitude"].median(),
                            "longitude": g["longitude"].median(),
                        }
                    ]
                )
                for grupo, pr in zip(
                    classificador.classes_,
                    classificador.predict_proba(x[VARIAVEIS_CLASSIFICACAO])[0],
                ):
                    probs.append(
                        dict(
                            area_risco=int(area),
                            epoca=epoca,
                            grupo=grupo,
                            probabilidade=float(pr),
                        )
                    )

        meta.update(
            classes=list(classificador.classes_),
            semanas_treino=int(painel["semana"].nunique()),
            ocorrencias_treino=len(completas),
        )
        with transaction.atomic():
            exec_ = ExecucaoModelo.objects.create(
                ocorrencias_usadas=len(completas),
                semanas_treino=meta["semanas_treino"],
                ultima_semana_coberta=fim_cobertura.date(),
                metadados=meta,
            )
            PrevisaoDemanda.objects.bulk_create(
                PrevisaoDemanda(execucao=exec_, **l) for l in linhas
            )
            ProbabilidadeTipo.objects.bulk_create(
                ProbabilidadeTipo(execucao=exec_, **p) for p in probs
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Execução {exec_.pk}: {len(linhas)} previsões, {len(probs)} probabilidades. "
                f"Cobertura até {fim_cobertura.date()}. Próxima semana: {'sim' if meta['proxima_semana_disponivel'] else 'indisponível'}."
            )
        )
