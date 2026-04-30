from django.db import models
from django.core.exceptions import ValidationError

class Ocorrencia(models.Model):
    numero = models.IntegerField()
    sigrc = models.IntegerField()
    tipo = models.CharField(max_length=100, blank=True, null=True)
    motivo = models.CharField(max_length=255)  
    data = models.DateField()
    endereco = models.CharField(max_length=255)
    bairro = models.CharField(max_length=255)
    distrito = models.CharField(max_length=255)
    area_risco = models.IntegerField()
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    def __str__(self):
        return f'Ocorrência {self.numero}'

    def clean(self):
    
        if not self.data:
            return

        ano = self.data.year

        if Ocorrencia.objects.filter(
        numero=self.numero,
        data__year=ano
        ).exclude(id=self.id).exists():

            raise ValidationError({
            "numero": "Já existe uma ocorrência com esse número neste ano."
        })