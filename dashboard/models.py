from django.db import models


class ExecucaoModelo(models.Model):
    gerado_em = models.DateTimeField(auto_now_add=True)
    ocorrencias_usadas = models.IntegerField()
    semanas_treino = models.IntegerField()
    ultima_semana_coberta = models.DateField(null=True, blank=True)
    metadados = models.JSONField(default=dict)

    class Meta:
        ordering = ["-gerado_em"]


class PrevisaoDemanda(models.Model):
    PROXIMA_SEMANA = "proxima_semana"
    ESPERADO_MES = "esperado_mes"
    TESTE = "teste"

    execucao = models.ForeignKey(
        ExecucaoModelo, on_delete=models.CASCADE, related_name="previsoes"
    )
    tipo = models.CharField(max_length=20)
    distrito = models.CharField(max_length=60)
    referencia = models.DateField(
        help_text="Segunda-feira da semana ou primeiro dia do mês"
    )
    previsto = models.FloatField()
    baixo = models.FloatField()
    alto = models.FloatField()
    referencia_media_movel = models.FloatField(null=True, blank=True)
    observado = models.FloatField(
        null=True, blank=True, help_text="Só nas linhas de teste"
    )
    nivel = models.CharField(
        max_length=10,
        help_text="baixo, medio ou alto, em relação ao histórico do distrito",
    )

    class Meta:
        ordering = ["tipo", "distrito", "referencia"]


class ProbabilidadeTipo(models.Model):
    execucao = models.ForeignKey(
        ExecucaoModelo, on_delete=models.CASCADE, related_name="probabilidades"
    )
    area_risco = models.IntegerField()
    epoca = models.CharField(max_length=10, help_text="verao, chuvosa ou seca")
    grupo = models.CharField(max_length=30)
    probabilidade = models.FloatField()

    class Meta:
        ordering = ["area_risco", "epoca", "-probabilidade"]
