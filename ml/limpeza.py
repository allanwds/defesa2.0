"""Limpeza e padronização das ocorrências.

Os campos ``motivo``, ``bairro`` e ``distrito`` são digitados no cadastro e
acumulam variações de grafia, abreviações e erros de codificação. As funções
deste módulo não apagam informação: acrescentam colunas padronizadas e
indicadores (``atividade_administrativa``, ``coord_valida`` etc.) para que a
análise decida o que filtrar.
"""

import re
import unicodedata

import numpy as np
import pandas as pd

# Retângulo que envolve os distritos Jardim Ângela e Jardim São Luís
# (subprefeitura M'Boi Mirim). Coordenadas fora dele são erros de geocodificação
# ou atividades realizadas em outras regiões da cidade.
LAT_MIN, LAT_MAX = -23.80, -23.62
LON_MIN, LON_MAX = -46.82, -46.69

DISTRITOS_VALIDOS = {"Jd. Angela": "Jardim Ângela", "Jd. São Luis": "Jardim São Luís"}

# Chave normalizada (ver ``chave``) -> motivo canônico.
MOTIVOS = {
    "alagamento": "Alagamento",
    "desabamento": "Desabamento",
    "deslizamento": "Deslizamento",
    "erosao na via": "Erosão na via",
    "incencio": "Incêndio",
    "incendio": "Incêndio",
    "inundacao": "Inundação",
    "queda de arvore": "Queda de árvore",
    "rachadura em edificacao": "Rachadura em edificação",
    "rachadura em edificacoes": "Rachadura em edificação",
    "rachadura em residencia": "Rachadura em edificação",
    "rachadura em residencias": "Rachadura em edificação",
    "risco de desabamento": "Risco de desabamento",
    "risco de queda de arvore": "Risco de queda de árvore",
    "solapamento de via": "Solapamento de via",
    "solapamento de margem de corrego": "Solapamento de margem de córrego",
    "outros": "Outros",
}

# Agrupamento dos motivos por natureza do evento, usado como alvo da
# classificação: com ~770 registros, 13 classes deixam várias com menos de 30
# exemplos.
GRUPO_MOTIVO = {
    "Alagamento": "Hidrológico",
    "Inundação": "Hidrológico",
    "Deslizamento": "Geológico",
    "Erosão na via": "Geológico",
    "Solapamento de via": "Geológico",
    "Solapamento de margem de córrego": "Geológico",
    "Desabamento": "Estrutural",
    "Risco de desabamento": "Estrutural",
    "Rachadura em edificação": "Estrutural",
    "Queda de árvore": "Arbóreo",
    "Risco de queda de árvore": "Arbóreo",
    "Incêndio": "Outros",
    "Outros": "Outros",
}

# Abreviações no início do nome do bairro.
_ABREVIACOES = [
    (r"^(jd|jardimm|jarim)\b\.?", "jardim"),
    (r"^(pq|p q)\b\.?", "parque"),
    (r"^vl\b\.?", "vila"),
]

# Erros de digitação encontrados na base (aplicados sobre a chave).
_CORRECOES = [
    (r"\bedwirges\b", "edwiges"),
    (r"\balegrre\b", "alegre"),
    (r"\briveira\b", "riviera"),
    (r"\b(inpendencia|indepedencia)\b", "independencia"),
    (r"\bbananl\b", "bananal"),
    (r"\bmanuel\b", "manoel"),
    (r"\bda flores\b", "das flores"),
    (r"\baracai\b", "aracati"),
]

_PARTICULAS = {"da", "de", "do", "das", "dos", "e"}


def chave(texto) -> str:
    """Forma comparável de um texto: sem acentos, minúsculo e com espaços simples.

    Também resolve o erro de codificação "Ãngela" (de "Ângela"), porque os
    dois viram "angela" ao remover os acentos.
    """
    if pd.isna(texto):
        return ""
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip().lower()


def padronizar_motivo(motivo) -> str:
    return MOTIVOS.get(chave(motivo), "Outros")


def chave_bairro(bairro) -> str:
    """Chave do bairro sem abreviações, observações entre parênteses ou números."""
    k = chave(bairro)
    k = re.sub(r"\(.*?\)", "", k)
    k = re.sub(r",\s*\d+\s*$", "", k)
    for padrao, troca in _ABREVIACOES + _CORRECOES:
        k = re.sub(padrao, troca, k)
    return re.sub(r"\s+", " ", k).strip()


def _titulo(nome: str) -> str:
    palavras = nome.split()
    return " ".join(
        p.lower() if i > 0 and p.lower() in _PARTICULAS else p[:1].upper() + p[1:].lower()
        for i, p in enumerate(palavras)
    )


def _nomes_bairro(bairros: pd.Series, chaves: pd.Series) -> dict:
    """Escolhe, para cada chave, a grafia original mais frequente e bem formada.

    Uma grafia é bem formada quando, sem acentos, já coincide com a chave
    corrigida (sem abreviações nem erros de digitação) e não tem o erro de
    codificação "Ã".
    """
    limpos = bairros.str.replace(r"\s+", " ", regex=True).str.strip()
    limpos = limpos.str.replace(r"\s*\(.*?\)", "", regex=True)
    limpos = limpos.str.replace(r",\s*\d+\s*$", "", regex=True)
    mal_formado = limpos.str.contains("Ã") | (limpos.map(chave) != chaves)
    nomes = {}
    for k, grupo in limpos.groupby(chaves):
        candidatos = grupo[~mal_formado.loc[grupo.index]]
        if candidatos.empty:
            nomes[k] = _titulo(k)
        else:
            nomes[k] = _titulo(candidatos.value_counts().index[0])
    return nomes


def _imputar_distrito(df: pd.DataFrame) -> pd.Series:
    """Preenche o distrito ausente pelo distrito mais comum do mesmo bairro e,
    na falta dele, pelo distrito da ocorrência mais próxima no mapa."""
    distrito = df["distrito_padrao"].copy()
    conhecidos = df[distrito.notna()]
    por_bairro = conhecidos.groupby("bairro_chave")["distrito_padrao"].agg(
        lambda s: s.value_counts().index[0]
    )
    faltando = distrito.isna()
    distrito[faltando] = df.loc[faltando, "bairro_chave"].map(por_bairro)

    ref = conhecidos[conhecidos["coord_valida"]]
    for i in df.index[distrito.isna() & df["coord_valida"]]:
        d2 = (ref["latitude"] - df.at[i, "latitude"]) ** 2 + (
            ref["longitude"] - df.at[i, "longitude"]
        ) ** 2
        distrito[i] = ref.at[d2.idxmin(), "distrito_padrao"]
    return distrito


def limpar(df: pd.DataFrame) -> pd.DataFrame:
    """Devolve uma cópia de ``df`` com colunas padronizadas e indicadores de qualidade.

    Colunas acrescentadas:
        motivo_padrao, grupo_motivo, bairro_chave, bairro_nome, distrito_padrao,
        distrito_imputado, coord_valida, atividade_administrativa, ano, mes,
        semana, dia_semana.
    Latitude e longitude fora da região passam a ser NaN.
    """
    df = df.copy()

    df["motivo_padrao"] = df["motivo"].map(padronizar_motivo)
    df["grupo_motivo"] = df["motivo_padrao"].map(GRUPO_MOTIVO)

    # Registros como "Ipiranga ( Reunião)" ou "Ponte Rasa ( Simulado)" são
    # atividades do órgão, não ocorrências atendidas.
    df["atividade_administrativa"] = df["bairro"].str.contains(r"\(", regex=True)

    df["bairro_chave"] = df["bairro"].map(chave_bairro)
    df["bairro_nome"] = df["bairro_chave"].map(_nomes_bairro(df["bairro"], df["bairro_chave"]))

    dentro = df["latitude"].between(LAT_MIN, LAT_MAX) & df["longitude"].between(LON_MIN, LON_MAX)
    df["coord_valida"] = dentro
    df.loc[~dentro, ["latitude", "longitude"]] = np.nan

    df["distrito_padrao"] = df["distrito"].map(DISTRITOS_VALIDOS)
    df["distrito_imputado"] = df["distrito_padrao"].isna()
    df["distrito_padrao"] = _imputar_distrito(df)

    df["ano"] = df["data"].dt.year
    df["mes"] = df["data"].dt.month
    df["semana"] = df["data"].dt.to_period("W-SUN").dt.start_time
    df["dia_semana"] = df["data"].dt.dayofweek

    return df


def ocorrencias_validas(df: pd.DataFrame) -> pd.DataFrame:
    """Somente ocorrências atendidas (sem as atividades administrativas)."""
    return df[~df["atividade_administrativa"]].copy()


# Trechos em que o cadastro está completo: do primeiro dia do ano até a última
# data em que a numeração anual (campo ``numero``) é contínua. Fora deles a base
# tem meses inteiros sem registro, que não significam ausência de ocorrências
# (ver notebook 01, seção 4).
PERIODOS_COMPLETOS = [
    ("2024-01-01", "2024-02-29"),
    ("2025-01-01", "2025-10-07"),
    ("2026-01-01", "2026-02-03"),
]


def marcar_periodos(df: pd.DataFrame, periodos=PERIODOS_COMPLETOS) -> pd.DataFrame:
    """Acrescenta ``periodo_completo``, ``mes_completo`` e ``semana_completa``.

    Um mês ou uma semana (segunda a domingo) é completo quando cabe inteiro
    dentro de um dos períodos. Requer a coluna ``semana`` criada por ``limpar``.
    """
    df = df.copy()
    df["periodo_completo"] = False
    df["mes_completo"] = False
    df["semana_completa"] = False
    fim_do_mes = df["data"] + pd.offsets.MonthEnd(0)
    for inicio, fim in periodos:
        inicio, fim = pd.Timestamp(inicio), pd.Timestamp(fim)
        df.loc[df["data"].between(inicio, fim), "periodo_completo"] = True
        df.loc[(df["data"] >= inicio) & (fim_do_mes <= fim), "mes_completo"] = True
        df.loc[(df["semana"] >= inicio) & (df["semana"] + pd.Timedelta(days=6) <= fim), "semana_completa"] = True
    return df


def semanas_completas(periodos=PERIODOS_COMPLETOS) -> pd.DataFrame:
    """Todas as semanas completas (inclusive as sem nenhum registro), com o
    índice do período a que pertencem."""
    linhas = []
    for i, (inicio, fim) in enumerate(periodos):
        inicio, fim = pd.Timestamp(inicio), pd.Timestamp(fim)
        primeira = inicio + pd.offsets.Week(weekday=0) if inicio.dayofweek else inicio
        for semana in pd.date_range(primeira, fim - pd.Timedelta(days=6), freq="W-MON"):
            linhas.append({"semana": semana, "bloco": i})
    return pd.DataFrame(linhas)
