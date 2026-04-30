import io
import unicodedata
import requests
import ssl
import urllib.request
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.http import HttpResponse, JsonResponse
from django.db.models import Count, Q
from django.db import IntegrityError, DatabaseError, transaction
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.pagesizes import letter, landscape, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from io import BytesIO
from .models import Ocorrencia
from .forms import OcorrenciaForm
from django.http import JsonResponse
from django.utils.dateparse import parse_date
from django.template.loader import render_to_string
from reportlab.lib.utils import ImageReader
#from django.db.models.functions import TruncMonth
import pandas as pd

# --------------------- LOGIN / LOGOUT ---------------------
LOGO_URL = "https://www.prefeitura.sp.gov.br/cidade/secretarias/upload/comunicacao/noticias/defesacivil.jpg"

def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            # Redireciona para 'next' se veio de uma página protegida
            next_url = request.GET.get('next')
            if next_url:
                return redirect(next_url)
            return redirect('home')  # Senão, vai para home
        else:
            messages.error(request, "Usuário ou senha inválidos.")
    return render(request, "login.html")


def logout_view(request):
    logout(request)
    return redirect('login')


# --------------------- PÁGINA HOME ---------------------

@login_required
def home(request):
    return render(request, "ocorrencias/home.html")


# --------------------- CADASTRO / LISTA ---------------------

@login_required
def cadastro_ocorrencia(request):
    if request.method == 'POST':
        form = OcorrenciaForm(request.POST)

        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, 'Ocorrência cadastrada com sucesso!')
                return redirect('lista_ocorrencias')

            except IntegrityError as e:
                msg = str(e)

                # 🔒 Mapas de erros comuns de integridade
                if 'ocorrencias_ocorrencia_numero_key' in msg or ('unique' in msg.lower() and 'numero' in msg.lower()):
                    form.add_error('numero', 'Número de FOC já cadastrado.')
                elif 'sigrc' in msg.lower() and 'unique' in msg.lower():
                    form.add_error('sigrc', 'SIGRC já cadastrado.')
                elif 'not null constraint failed' in msg.lower() and 'latitude' in msg.lower():
                    form.add_error('latitude', 'Latitude é obrigatória. Selecione no mapa.')
                elif 'not null constraint failed' in msg.lower() and 'longitude' in msg.lower():
                    form.add_error('longitude', 'Longitude é obrigatória. Selecione no mapa.')
                else:
                    form.add_error(None, 'Erro de integridade ao salvar. Verifique os campos e tente novamente.')

                messages.error(request, 'Não foi possível salvar. Corrija os erros destacados.')

            except DatabaseError:
                form.add_error(None, 'Erro no banco de dados. Tente novamente.')
                messages.error(request, 'Erro no banco de dados. Tente novamente.')

        else:
            messages.error(request, 'Corrija os erros abaixo e tente novamente.')

        return render(request, 'ocorrencias/cadastro.html', {'form': form})

    # GET
    form = OcorrenciaForm()
    return render(request, 'ocorrencias/cadastro.html', {'form': form})


@login_required
def lista_ocorrencias(request):
    ocorrencias = Ocorrencia.objects.all().order_by('-numero')
    return render(request, 'ocorrencias/lista_ocorrencias.html', {'ocorrencias': ocorrencias})


@login_required
def salvar_ocorrencia(request):
    if request.method == 'POST':
        form = OcorrenciaForm(request.POST)

        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, 'Ocorrência cadastrada com sucesso!')
                return redirect('lista_ocorrencias')

            except IntegrityError as e:
                msg = str(e)

                # 🔒 Mapas de erros comuns de integridade
                if 'ocorrencias_ocorrencia_numero_key' in msg or ('unique' in msg.lower() and 'numero' in msg.lower()):
                    form.add_error('numero', 'Número de FOC já cadastrado.')
                elif 'sigrc' in msg.lower() and 'unique' in msg.lower():
                    form.add_error('sigrc', 'SIGRC já cadastrado.')
                elif 'not null constraint failed' in msg.lower() and 'latitude' in msg.lower():
                    form.add_error('latitude', 'Latitude é obrigatória. Selecione no mapa.')
                elif 'not null constraint failed' in msg.lower() and 'longitude' in msg.lower():
                    form.add_error('longitude', 'Longitude é obrigatória. Selecione no mapa.')
                else:
                    form.add_error(None, 'Erro de integridade ao salvar. Verifique os campos e tente novamente.')

                messages.error(request, 'Não foi possível salvar. Corrija os erros destacados.')

            except DatabaseError:
                form.add_error(None, 'Erro no banco de dados. Tente novamente.')
                messages.error(request, 'Erro no banco de dados. Tente novamente.')

        else:
            messages.error(request, 'Corrija os erros abaixo e tente novamente.')

        return render(request, 'ocorrencias/cadastro.html', {'form': form})

    # GET
    form = OcorrenciaForm()
    return render(request, 'ocorrencias/cadastro.html', {'form': form})


# --------------------- EDIÇÃO / EXCLUSÃO ---------------------

@login_required


@require_POST
def editar_ocorrencia_inline(request, id):
    ocorrencia = get_object_or_404(Ocorrencia, id=id)

    ocorrencia.numero = request.POST.get('numero')
    ocorrencia.sigrc = request.POST.get('sigrc')
    ocorrencia.endereco = request.POST.get('endereco')
    ocorrencia.bairro = request.POST.get('bairro')
    ocorrencia.distrito = request.POST.get('distrito')
    ocorrencia.area_risco = request.POST.get('area_risco')
    ocorrencia.motivo = request.POST.get('motivo')
    ocorrencia.data = request.POST.get('data')

    ocorrencia.save()

    return JsonResponse({'status': 'ok'})

@login_required
def excluir_ocorrencia(request, id):
    ocorrencia = get_object_or_404(Ocorrencia, id=id)
    ocorrencia.delete()
    return redirect('lista_ocorrencias')


# --------------------- RELATÓRIOS / GRÁFICOS ---------------------

@login_required
def busca_relatorios(request):
    data_inicial = request.GET.get('data_inicial')
    data_final = request.GET.get('data_final')
    endereco = request.GET.get('endereco')
    distrito = request.GET.get('distrito')
    motivo = request.GET.get('motivo')
    bairro = request.GET.get('bairro')

    ocorrencias = Ocorrencia.objects.all().order_by('-numero')

    if data_inicial and data_final:
        ocorrencias = ocorrencias.filter(data__range=[data_inicial, data_final])
    elif data_inicial:
        ocorrencias = ocorrencias.filter(data__gte=data_inicial)
    elif data_final:
        ocorrencias = ocorrencias.filter(data__lte=data_final)

    if endereco:
        ocorrencias = ocorrencias.filter(endereco__icontains=endereco)
    if distrito:
        ocorrencias = ocorrencias.filter(distrito__icontains=distrito)
    if motivo:
        ocorrencias = ocorrencias.filter(motivo__icontains=motivo)
    if bairro:
        ocorrencias = ocorrencias.filter(bairro__icontains=bairro)

    return render(request, 'ocorrencias/relatorios.html', {'ocorrencias': ocorrencias})

# 1) Página (render do HTML) — use este para abrir /graficos/
def graficos_page(request):
    return render(request, 'ocorrencias/graficos.html')


# 2) Dados (JSON) — a página consome via fetch/Chart.js
@login_required
def graficos_data(request):
    qs = Ocorrencia.objects.all()

    # ---------------- FILTROS ----------------
    data_inicial = (request.GET.get("data_inicial") or "").strip()
    data_final   = (request.GET.get("data_final") or "").strip()
    distrito     = (request.GET.get("distrito") or "").strip()
    motivo       = (request.GET.get("motivo") or "").strip()

    if data_inicial:
        d_ini = parse_date(data_inicial)
        if d_ini:
            qs = qs.filter(data__gte=d_ini)

    if data_final:
        d_fim = parse_date(data_final)
        if d_fim:
            qs = qs.filter(data__lte=d_fim)

    if distrito:
        qs = qs.filter(distrito__icontains=distrito)

    if motivo:
        qs = qs.filter(motivo__icontains=motivo)

    # ---------------- DATAFRAME ----------------
    qs = qs.values("data", "motivo", "distrito", "bairro")
    df = pd.DataFrame(list(qs))
# 🔥 LIMPEZA DE DADOS (OBRIGATÓRIO)
    df['motivo'] = (
        df['motivo']
         .astype(str)
         .str.strip()
        .str.lower()
)
# 🔥 PADRONIZAÇÃO (resolve duplicidade)
    df['motivo'] = df['motivo'].replace({
    'rachadura em edificações': 'Rachadura em edificações',
    'rachadura em edificação': 'Rachadura em edificações',
    'rachadura em residencia': 'Rachadura em edificações',
    'rachadura em residências': 'Rachadura em edificações',
})
# 🔥 remove lixo
    df = df.dropna(subset=['data', 'motivo'])

    if df.empty:
        return JsonResponse({
         "motivos": {"labels": [], "data": []},
         "distritos": {"labels": [], "data": []},
         "evolucao_mensal_motivos": {"labels": [], "series": []},
         "heatmap": []
})
    # ---------------- TRATAMENTO ----------------
    df['data'] = pd.to_datetime(df['data'])
    df['mes'] = df['data'].dt.to_period('M').astype(str)
    # ---------------- MOTIVOS ----------------
    motivos = df['motivo'].value_counts()
    # ---------------- DISTRITOS ----------------
    distritos = df['distrito'].value_counts()
    # ---------------- PIVOT (BASE DE TUDO) ----------------
    pivot = pd.pivot_table(
        df,
        index='mes',
        columns='motivo',
        aggfunc='size',
        fill_value=0
    )
    pivot = pivot.sort_index()
    # ---------------- SERIES (GRÁFICO LINHA) ----------------
    labels_mes = pivot.index.tolist()

    series = []
    for col in pivot.columns:
        series.append({
            "label": col,
            "data": pivot[col].tolist()
        })
    # ---------------- HEATMAP ----------------
    heatmap_data = []
    for mes in pivot.index:
        for mot in pivot.columns:
            heatmap_data.append({
                "x": mes,
                "y": mot,
                "v": int(pivot.loc[mes, mot])
            })
#  AGRUPAMENTO MENSAL
    mensal = df.groupby('mes').size().sort_index()
#  MÉDIA E DESVIO (ANOMALIA)
    media = mensal.mean()
    desvio = mensal.std()
    limite = media + (2 * desvio)

    anomalias = mensal[mensal > limite]

    mes_anomalo = None
    if not anomalias.empty:
        mes_anomalo = anomalias.idxmax()

#  CRESCIMENTO (%)
    crescimento = None
    if len(mensal) >= 2:
        ult = mensal.iloc[-1]
        penult = mensal.iloc[-2]
    if penult > 0:
        crescimento = round(((ult - penult) / penult) * 100, 1)

#  TOP BAIRROS
    top_bairros = df['bairro'].value_counts().head(5)

# 🔥 RESPOSTA EXTRA
    analise_extra = {
    "mes_anomalo": mes_anomalo,
    "crescimento": crescimento,
    "top_bairros": top_bairros.index.tolist(),
    "media_mensal": round(media, 1)
}
    # ---------------- RESPOSTA ----------------
    return JsonResponse({
        "motivos": {
            "labels": motivos.index.tolist(),
            "data": motivos.values.tolist()
        },
        "distritos": {
            "labels": distritos.index.tolist(),
            "data": distritos.values.tolist()
        },
        "total_motivos": int(motivos.sum()),
        "total_distritos": int(distritos.sum()),
        "evolucao_mensal_motivos": {
            "labels": labels_mes,
            "series": series
        },
        "heatmap": heatmap_data,
        "analise_extra": analise_extra
    })
    
@login_required
def graficos_ocorrencias(request):
    tipo = request.GET.get('tipo')
    bairro = request.GET.get('bairro')
    distrito = request.GET.get('distrito')
    data_inicial = request.GET.get('data_inicial')
    data_final = request.GET.get('data_final')

    ocorrencias = Ocorrencia.objects.all()
    if tipo:
        ocorrencias = ocorrencias.filter(tipo=tipo)
    if bairro:
        ocorrencias = ocorrencias.filter(bairro=bairro)
    if distrito:
        ocorrencias = ocorrencias.filter(distrito=distrito)
    if data_inicial:
        ocorrencias = ocorrencias.filter(data__gte=data_inicial)
    if data_final:
        ocorrencias = ocorrencias.filter(data__lte=data_final)

    motivos_count = ocorrencias.values('motivo').annotate(total=Count('id')).order_by('-total')
    distritos_count = ocorrencias.values('distrito').annotate(total=Count('id')).order_by('-total')

    context = {
        'motivos_count': motivos_count,
        'distritos_count': distritos_count,
        'total_motivos': sum(m['total'] for m in motivos_count),
        'total_distritos': sum(d['total'] for d in distritos_count),
    }
    return render(request, 'ocorrencias/graficos.html', context)

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        super().showPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        self.setFont("Helvetica", 9)
        text = f"Página {self._pageNumber} de {page_count}"
        # Rodapé (direita)
        w = self.stringWidth(text, "Helvetica", 9)
        self.drawString(A4[0] - 20*mm - w, 12*mm, text)

_LOGO_IMG_READER = None

def _fetch_logo_bytes():
    """
    Baixa o logo da prefeitura tentando múltiplas estratégias.
    Retorna bytes (ou None).
    """
    url = "https://www.prefeitura.sp.gov.br/cidade/secretarias/upload/comunicacao/noticias/defesacivil.jpg"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ReportLab/3.x",
        "Referer": "https://www.prefeitura.sp.gov.br/",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }

    # 1) requests normal
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        if resp.content:
            return resp.content
    except Exception as e:
        print("[PDF] requests get falhou:", e)

    # 2) urllib com SSL padrão
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = r.read()
            if data:
                return data
    except Exception as e:
        print("[PDF] urllib padrão falhou:", e)

    # 3) urllib com SSL relaxado (caso servidor tenha cadeia estranha)
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            data = r.read()
            if data:
                return data
    except Exception as e:
        print("[PDF] urllib relaxado falhou:", e)

    return None

def _get_remote_image_reader(url: str) -> ImageReader | None:
    """
    Baixa imagem remota (com UA e fallback SSL) e retorna ImageReader.
    Retorna None se falhar.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ReportLab",
        "Referer": "https://www.prefeitura.sp.gov.br/",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }

    # 1) tentativa normal
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = r.read()
            if data:
                return ImageReader(io.BytesIO(data))
    except Exception as e:
        print("[PDF] urllib (padrão) falhou:", e)

    # 2) fallback com SSL relaxado
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            data = r.read()
            if data:
                return ImageReader(io.BytesIO(data))
    except Exception as e:
        print("[PDF] urllib (SSL relaxado) falhou:", e)

    return None

def draw_header_footer_with_logo(canvas, doc, titulo: str, logo_ir: ImageReader | None):
    """
    Cabeçalho com (tentativa de) logo à esquerda e título à direita; rodapé com página.
    Se logo_ir == None, escreve 'LOGO INDISPONÍVEL' no lugar do logo (pra ficar evidente).
    """
    canvas.saveState()
    page_w, page_h = A4
    left_margin = 15 * mm
    right_margin = 15 * mm
    top_margin = 15 * mm

    # --- Logo ---
    x_logo = left_margin
    target_h = 12 * mm
    x_title = left_margin  # fallback

    if logo_ir is not None:
        try:
            iw, ih = logo_ir.getSize()
            scale = target_h / float(ih)
            draw_w = iw * scale
            draw_h = target_h
            y_logo = page_h - top_margin - draw_h
            canvas.drawImage(
                logo_ir, x_logo, y_logo,
                width=draw_w, height=draw_h,
                preserveAspectRatio=True, mask='auto'
            )
            x_title = x_logo + draw_w + 6 * mm
        except Exception as e:
            print("[PDF] drawImage falhou:", e)
            # Marca visível para confirmar execução:
            canvas.setFont("Helvetica-Oblique", 8)
            canvas.setFillColor(colors.HexColor("#AA0000"))
            canvas.drawString(x_logo, page_h - top_margin - 9, "LOGO INDISPONÍVEL")
            canvas.setFillColor(colors.black)
            x_title = left_margin + 45
    else:
        # Marca visível para confirmar que o header rodou:
        canvas.setFont("Helvetica-Oblique", 8)
        canvas.setFillColor(colors.HexColor("#AA0000"))
        canvas.drawString(x_logo, page_h - top_margin - 9, "LOGO INDISPONÍVEL")
        canvas.setFillColor(colors.black)
        x_title = left_margin + 45

    # --- Título ---
    canvas.setFont("Helvetica-Bold", 12)
    canvas.setFillColor(colors.HexColor("#333333"))
    canvas.drawString(x_title, page_h - top_margin - 9, titulo)

    # Linha
    canvas.setStrokeColor(colors.HexColor("#f2a654"))
    canvas.setLineWidth(0.8)
    canvas.line(left_margin, page_h - 17 * mm, page_w - right_margin, page_h - 17 * mm)

    # --- Rodapé ---
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#777777"))
    canvas.drawString(left_margin, 12 * mm, "DDEC-MB • Relatório gerado automaticamente")

    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(colors.HexColor("#666666"))
    page_txt = f"Página {canvas.getPageNumber()}"
    canvas.drawRightString(page_w - right_margin, 12 * mm, page_txt)

    canvas.restoreState()
    
def _normalize_py(s: str) -> str:
    """Normaliza string para comparação acento-insensível e case-insensitive."""
    if s is None:
        return ''
    # NFD + remoção de diacríticos
    s = unicodedata.normalize('NFD', str(s))
    s = ''.join(ch for ch in s if unicodedata.category(ch) != 'Mn')
    return s.lower().strip()

def _match_contains(field_value: str, term: str) -> bool:
    """Retorna True se field_value contém term usando normalização robusta."""
    if not term:
        return True
    return _normalize_py(field_value).find(_normalize_py(term)) != -1

def _draw_header_footer(canvas, doc):
    """Cabeçalho e rodapé simples com número de página (ReportLab)."""
    canvas.saveState()
    w, h = A4  # (width, height)

    # Cabeçalho
    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawString(15 * mm, h - 15 * mm, "PREFEITURA DE SÃO PAULO - SMSU/DDEC-MB")

    # Rodapé (numeração)
    page_txt = f"Página {canvas.getPageNumber()}"
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawRightString(w - 15 * mm, 12 * mm, page_txt)

    canvas.restoreState()

@login_required
def gerar_relatorio_pdf(request):
    qs = Ocorrencia.objects.all().order_by('-numero')

    # Filtros GET (texto)
    endereco = request.GET.get('endereco', '').strip()
    bairro = request.GET.get('bairro', '').strip()
    distrito = request.GET.get('distrito', '').strip()
    motivo = request.GET.get('motivo', '').strip()
    q      = request.GET.get('q', '').strip()

    # Filtros GET (datas) -> filtrados no banco
    data_inicial = request.GET.get('data_inicial', '').strip()
    data_final   = request.GET.get('data_final', '').strip()

    if data_inicial:
        d_ini = parse_date(data_inicial)  # yyyy-mm-dd
        if d_ini:
            qs = qs.filter(data__gte=d_ini)

    if data_final:
        d_fim = parse_date(data_final)
        if d_fim:
            qs = qs.filter(data__lte=d_fim)

    # -----------------------------------------
    # FILTROS DE TEXTO (ACENTO/CASE INSENSITIVE)
    # -----------------------------------------
    # Como SQLite não tem "unaccent" nativo, vamos filtrar em Python
    # sobre o queryset já reduzido pelos filtros de data.
    filtros_texto_ativos = any([endereco, bairro, distrito, motivo, q])

    if filtros_texto_ativos:
        objetos_filtrados = []
        norm_q = _normalize_py(q)

        for o in qs:
            ok = True

            if endereco and not _match_contains(o.endereco or '', endereco):
                ok = False
            if ok and bairro and not _match_contains(o.bairro or '', bairro):
                ok = False
            if ok and distrito and not _match_contains(o.distrito or '', distrito):
                ok = False
            if ok and motivo and not _match_contains(o.motivo or '', motivo):
                ok = False

            if ok and norm_q:
                # busca ampla atravessando campos (inclui numero como texto)
                ok = (
                    _match_contains(str(o.numero or ''), norm_q) or
                    _match_contains(o.endereco or '', norm_q) or
                    _match_contains(o.bairro or '', norm_q) or
                    _match_contains(o.distrito or '', norm_q) or
                    _match_contains(o.motivo or '', norm_q)
                )

            if ok:
                objetos_filtrados.append(o)

        # Passa a operar sobre a lista filtrada
        registros = objetos_filtrados
    else:
        # Sem filtro de texto -> mantém avaliação lazy do banco (mas vamos iterar já)
        registros = list(qs)

    # ---------------------------
    # MONTAGEM DO PDF (UMA VEZ)
    # ---------------------------
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=25 * mm,
        bottomMargin=18 * mm,
    )

    styles = getSampleStyleSheet()
    small_style = ParagraphStyle(
        'SmallGrey',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor("#555555"),
        spaceAfter=6,
    )
    cell_style = ParagraphStyle(
        'Cell',
        parent=styles['Normal'],
        fontSize=9,
        leading=11,
        textColor=colors.black,
    )
    title_style = ParagraphStyle(
        'Title',
        parent=styles['Heading2'],
        alignment=1,  # center
        textColor=colors.HexColor("#333333"),
        spaceAfter=8,
    )

    elementos = []

    # Título
    elementos.append(Paragraph("RELATÓRIO DE OCORRÊNCIAS - DDEC-MB", title_style))

    # Resumo dos filtros
    filtros_txt = []
    if data_inicial: filtros_txt.append(f"Início: {data_inicial}")
    if data_final:   filtros_txt.append(f"Fim: {data_final}")
    if distrito:     filtros_txt.append(f"Distrito: {distrito}")
    if bairro:       filtros_txt.append(f"Bairro: {bairro}")
    if motivo:       filtros_txt.append(f"Motivo: {motivo}")
    if endereco:     filtros_txt.append(f"Endereço contém: {endereco}")
    if q:            filtros_txt.append(f"Busca geral: {q}")

    resumo = "NENHUM FILTRO SELECIONADO" if not filtros_txt else "Filtros aplicados — " + " | ".join(filtros_txt)
    elementos.append(Paragraph(resumo, small_style))
    elementos.append(Spacer(1, 6))

    # Cabeçalho da tabela
    header = [
        Paragraph("<b>FOC</b>", cell_style),
        Paragraph("<b>Endereço</b>", cell_style),
        Paragraph("<b>Bairro</b>", cell_style),
        Paragraph("<b>Distrito</b>", cell_style),
        Paragraph("<b>Motivo</b>", cell_style),
        Paragraph("<b>Data</b>", cell_style),
    ]

    data_rows = []
    for o in registros:
        data_rows.append([
            Paragraph(str(o.numero or ''), cell_style),
            Paragraph(o.endereco or '', cell_style),
            Paragraph(o.bairro or '', cell_style),
            Paragraph(o.distrito or '', cell_style),
            Paragraph(o.motivo or '', cell_style),
            Paragraph(o.data.strftime('%d/%m/%Y') if getattr(o, 'data', None) else '', cell_style),
        ])

    if not data_rows:
        elementos.append(Paragraph("Nenhuma ocorrência encontrada para os filtros informados.", styles['Normal']))
    else:
        # Larguras proporcionais
        proportions = [0.08, 0.30, 0.15, 0.13, 0.23, 0.11]
        total_width = A4[0] - (doc.leftMargin + doc.rightMargin)
        col_widths = [p * total_width for p in proportions]

        table = Table([header] + data_rows, colWidths=col_widths, repeatRows=1, hAlign='LEFT')
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f2a654")),
            ('TEXTCOLOR',  (0, 0), (-1, 0), colors.black),
            ('FONTNAME',   (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE',   (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),

            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.HexColor("#fffdf7")]),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor("#bbbbbb")),

            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('LEADING',  (0, 1), (-1, -1), 11),

            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (-1, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),

            ('LEFTPADDING',  (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING',   (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING',(0, 0), (-1, -1), 4),
        ]))
        elementos.append(table)

    # Gera o PDF (uma única vez)
    doc.build(
        elementos,
        onFirstPage=_draw_header_footer,
        onLaterPages=_draw_header_footer,
    )

    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="relatorio_ocorrencias.pdf"'
    return response

@login_required
def graficos_ajax(request):
    motivo = request.GET.get('motivo', '')
    distrito = request.GET.get('distrito', '')

    qs = Ocorrencia.objects.all()
    if motivo: qs = qs.filter(motivo=motivo)
    if distrito: qs = qs.filter(distrito=distrito)

    motivos_data = list(qs.values('motivo').annotate(total=Count('motivo')))
    distritos_data = list(qs.values('distrito').annotate(total=Count('distrito')))

    return JsonResponse({'motivos': motivos_data, 'distritos': distritos_data})

