import json

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from ocorrencias.models import Ocorrencia


class Command(BaseCommand):
    help = "Importa ocorrências de um JSON da API para o banco atual (apenas SQLite)."

    def add_arguments(self, parser):
        parser.add_argument("arquivo")

    def handle(self, *args, arquivo, **opts):
        if connection.vendor != "sqlite":
            raise CommandError(
                "Recusado: este comando só roda no SQLite local (USE_SQLITE=1)."
            )
        campos = {f.name for f in Ocorrencia._meta.fields}
        with open(arquivo, encoding="utf-8") as f:
            registros = json.load(f)
        Ocorrencia.objects.all().delete()
        Ocorrencia.objects.bulk_create(
            Ocorrencia(**{k: v for k, v in r.items() if k in campos}) for r in registros
        )
        self.stdout.write(
            self.style.SUCCESS(f"{len(registros)} ocorrências importadas.")
        )
