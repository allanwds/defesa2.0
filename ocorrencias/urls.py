from django.urls import path
from . import views

urlpatterns = [
    path('cadastro/', views.cadastro_ocorrencia, name='cadastro_ocorrencia'),
    path('salvar/', views.salvar_ocorrencia, name='salvar_ocorrencia'),
    path('lista/', views.lista_ocorrencias, name='lista_ocorrencias'),
    path('relatorios/', views.busca_relatorios, name='relatorios'),
    path('ocorrencia/editar/<int:id>/', views.editar_ocorrencia_inline, name='editar_ocorrencia_inline'),
    path('ocorrencia/excluir/<int:id>/', views.excluir_ocorrencia, name='excluir_ocorrencia'),
    path('relatorio/pdf/', views.gerar_relatorio_pdf, name='relatorio_pdf'),
    path('graficos/data/', views.graficos_data, name='graficos_data'),
    path('graficos/', views.graficos_page, name='graficos_page'),
]