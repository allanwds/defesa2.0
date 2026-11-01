import calendar

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.shortcuts import render

from ocorrencias.models import Ocorrencia

from .models import ExecucaoModelo


@login_required
def dashboard_page(request):
    return render(request, "dashboard/dashboard.html")


def _mes_completo(mes, periodos):
    fim_do_mes = mes.replace(day=calendar.monthrange(mes.year, mes.month)[1])
    return any(
        a <= mes.isoformat() and fim_do_mes.isoformat() <= b for a, b in periodos
    )


@login_required
def dashboard_dados(request):
    execucao = ExecucaoModelo.objects.first()
    meta = execucao.metadados if execucao else {}
    periodos = meta.get("periodos_completos", [])

    qs = Ocorrencia.objects.all()
    distrito = request.GET.get("distrito", "").strip()
    ano = request.GET.get("ano", "").strip()
    if distrito:
        qs = qs.filter(distrito=distrito)
    if ano.isdigit():
        qs = qs.filter(data__year=int(ano))

    mensal = [
        {
            "mes": r["mes"].isoformat(),
            "total": r["total"],
            "completo": _mes_completo(r["mes"], periodos),
        }
        for r in qs.annotate(mes=TruncMonth("data"))
        .values("mes")
        .annotate(total=Count("id"))
        .order_by("mes")
    ]
    por_motivo = list(
        qs.values("motivo").annotate(total=Count("id")).order_by("-total")[:8]
    )
    por_area = list(
        qs.values("area_risco").annotate(total=Count("id")).order_by("area_risco")
    )
    pontos = list(
        qs.filter(
            latitude__range=(-23.80, -23.62), longitude__range=(-46.82, -46.69)
        ).values_list("latitude", "longitude", "area_risco", "motivo")[:3000]
    )
    todos_os_meses = (
        Ocorrencia.objects.annotate(mes=TruncMonth("data"))
        .values_list("mes", flat=True)
        .distinct()
    )
    meses_com_registro_total = len(todos_os_meses)
    meses_completos_total = sum(1 for m in todos_os_meses if _mes_completo(m, periodos))

    previsoes = {"proxima_semana": [], "esperado_mes": [], "teste": []}
    probabilidades = []
    if execucao:
        for p in execucao.previsoes.all():
            previsoes[p.tipo].append(
                {
                    "distrito": p.distrito,
                    "referencia": p.referencia.isoformat(),
                    "previsto": round(p.previsto, 2),
                    "baixo": round(p.baixo, 2),
                    "alto": round(p.alto, 2),
                    "media_movel": None
                    if p.referencia_media_movel is None
                    else round(p.referencia_media_movel, 2),
                    "observado": p.observado,
                    "nivel": p.nivel,
                }
            )
        probabilidades = [
            {
                "area_risco": p.area_risco,
                "epoca": p.epoca,
                "grupo": p.grupo,
                "probabilidade": round(p.probabilidade, 3),
            }
            for p in execucao.probabilidades.all()
        ]

    return JsonResponse(
        {
            "kpis": {
                "total": qs.count(),
                "meses_com_registro_total": meses_com_registro_total,
                "meses_completos_total": meses_completos_total,
            },
            "mensal": mensal,
            "por_motivo": por_motivo,
            "por_area": por_area,
            "pontos": [
                {"lat": a, "lon": b, "area": c, "motivo": d} for a, b, c, d in pontos
            ],
            "distritos": list(
                Ocorrencia.objects.order_by()
                .values_list("distrito", flat=True)
                .distinct()
            ),
            "anos": [d.year for d in Ocorrencia.objects.dates("data", "year")],
            "previsoes": previsoes,
            "probabilidades": probabilidades,
            "modelo": None
            if not execucao
            else {
                "gerado_em": execucao.gerado_em.isoformat(),
                "semanas_treino": execucao.semanas_treino,
                "ocorrencias_usadas": execucao.ocorrencias_usadas,
                **meta,
            },
        }
    )
