from django import forms
from .models import Ocorrencia

class OcorrenciaForm(forms.ModelForm):

    class Meta:
        model = Ocorrencia
        fields = [
            'numero', 'sigrc', 'motivo', 'data',
            'endereco', 'bairro', 'distrito',
            'area_risco', 'latitude', 'longitude'
        ]
        widgets = {
            'data': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean_sigrc(self):
        sigrc = self.cleaned_data.get('sigrc')
        if sigrc and Ocorrencia.objects.filter(sigrc=sigrc).exists():
            raise forms.ValidationError("Já existe ocorrência registrada com esse SIGRC.")
        return sigrc