from django.db.models import Count
from django.db.models.functions import TruncMonth

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly

from ocorrencias.models import Ocorrencia

from .serializers import (
    OcorrenciaSerializer,
    OcorrenciaResumoSerializer,
)


class OcorrenciaViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API pública de ocorrências da Defesa Civil.
    Apenas consulta de dados.
    """

    # Ordena:
    # 1º número da ocorrência
    # 2º data
    queryset = Ocorrencia.objects.all().order_by("-numero", "-data")

    serializer_class = OcorrenciaSerializer

    permission_classes = [IsAuthenticatedOrReadOnly]

    # Apenas GET
    http_method_names = ["get"]

    # Remove paginação
    pagination_class = None


    @action(detail=False, methods=["get"], url_path="mapa")
    def mapa(self, request):

        qs = self.get_queryset().filter(
            latitude__isnull=False,
            longitude__isnull=False
        )

        serializer = OcorrenciaResumoSerializer(qs, many=True)

        return Response(serializer.data)


    @action(detail=False, methods=["get"], url_path="estatisticas")
    def estatisticas(self, request):

        qs = self.get_queryset()

        total = qs.count()

        por_motivo = list(
            qs.values("motivo")
            .annotate(total=Count("id"))
            .order_by("-total")
        )

        por_bairro = list(
            qs.values("bairro")
            .annotate(total=Count("id"))
            .order_by("-total")[:10]
        )

        por_risco = list(
            qs.values("area_risco")
            .annotate(total=Count("id"))
            .order_by("area_risco")
        )

        por_mes = list(
            qs.annotate(mes=TruncMonth("data"))
            .values("mes")
            .annotate(total=Count("id"))
            .order_by("mes")
        )

        for item in por_mes:
            item["mes"] = item["mes"].strftime("%Y-%m") if item["mes"] else None

        return Response(
            {
                "total_ocorrencias": total,
                "por_motivo": por_motivo,
                "por_bairro": por_bairro,
                "por_risco": por_risco,
                "por_mes": por_mes,
            },
            status=status.HTTP_200_OK
        )