from django import forms
from .models import Ocorrencia

class OcorrenciaForm(forms.ModelForm):
    class Meta:
        model = Ocorrencia
        # Removi 'tipo' para bater com seu template atual
        fields = [
            'numero', 'sigrc', 'motivo', 'data',
            'endereco', 'bairro', 'distrito',
            'area_risco', 'latitude', 'longitude'
        ]
        widgets = {
            'data': forms.DateInput(attrs={'type': 'date'}),
            'latitude': forms.TextInput(attrs={'readonly': 'readonly'}),
            'longitude': forms.TextInput(attrs={'readonly': 'readonly'}),
        }
        error_messages = {
            'latitude': {'required': 'Latitude é obrigatória. Selecione no mapa.'},
            'longitude': {'required': 'Longitude é obrigatória. Selecione no mapa.'},
        }

    def clean_numero(self):
        numero = self.cleaned_data.get('numero')
        if numero and Ocorrencia.objects.filter(numero=numero).exists():
            raise forms.ValidationError("Já existe ocorrência registrada com esse número.")
        return numero

    def clean_sigrc(self):
        sigrc = self.cleaned_data.get('sigrc')
        if sigrc and Ocorrencia.objects.filter(sigrc=sigrc).exists():
            raise forms.ValidationError("Já existe ocorrência registrada com esse SIGRC.")
        return sigrc

    def clean_latitude(self):
        lat = self.cleaned_data.get('latitude')
        if lat in (None, ''):
            raise forms.ValidationError("Latitude é obrigatória. Selecione no mapa.")
        try:
            lat = float(str(lat).replace(',', '.'))
        except (TypeError, ValueError):
            raise forms.ValidationError("Latitude inválida.")
        if not (-90.0 <= lat <= 90.0):
            raise forms.ValidationError("Latitude fora do intervalo (-90 a 90).")
        return lat

    def clean_longitude(self):
        lon = self.cleaned_data.get('longitude')
        if lon in (None, ''):
            raise forms.ValidationError("Longitude é obrigatória. Selecione no mapa.")
        try:
            lon = float(str(lon).replace(',', '.'))
        except (TypeError, ValueError):
            raise forms.ValidationError("Longitude inválida.")
        if not (-180.0 <= lon <= 180.0):
            raise forms.ValidationError("Longitude fora do intervalo (-180 a 180).")
        return lon

    def clean(self):
        cleaned = super().clean()
        lat = cleaned.get('latitude')
        lon = cleaned.get('longitude')
        if (lat in (None, '')) or (lon in (None, '')):
            # garante também erro geral
            self.add_error(None, "É obrigatório selecionar a localização no mapa (latitude e longitude).")
        return cleaned
