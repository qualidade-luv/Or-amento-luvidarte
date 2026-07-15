import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from datetime import datetime, timedelta
import pytz
import re
import os
from io import BytesIO

# ============================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================
st.set_page_config(
    page_title="Dashboard LUVidarte",
    page_icon="📊",
    layout="wide"
)

# ============================================
# CONFIGURAÇÕES
# ============================================
TIMEZONE_BR = pytz.timezone('America/Sao_Paulo')
ID_PLANILHA_CADASTRO = "1_s01QhZJni2dYoJwkWflEtdrKzSZ5yt7mpZvASPlFxk"

ESCOPOS = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

def formatar_moeda(valor):
    """Formata valor numérico para moeda brasileira"""
    if valor is None or pd.isna(valor) or valor == 0:
        return "R$ 0,00"
    valor = float(valor)
    inteiro = int(valor)
    decimal = int(round((valor - inteiro) * 100))
    decimal_str = f"{decimal:02d}"
    inteiro_str = f"{inteiro:,}".replace(",", ".")
    return f"R$ {inteiro_str},{decimal_str}"

def formatar_telefone(telefone):
    """Formata telefone para exibição"""
    if not telefone or pd.isna(telefone):
        return "-"
    telefone = str(telefone).replace(' ', '').replace('(', '').replace(')', '').replace('-', '')
    if len(telefone) == 11:
        return f"({telefone[:2]}) {telefone[2:7]}-{telefone[7:]}"
    elif len(telefone) == 10:
        return f"({telefone[:2]}) {telefone[2:6]}-{telefone[6:]}"
    return telefone

def formatar_cnpj(cnpj):
    """Formata CNPJ para exibição"""
    if not cnpj or pd.isna(cnpj):
        return "-"
    cnpj = str(cnpj).replace('.', '').replace('/', '').replace('-', '')
    if len(cnpj) == 14:
        return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
    return cnpj

def converter_valor_para_numero(valor_str):
    """Converte formato de moeda brasileira para número"""
    if valor_str is None or pd.isna(valor_str):
        return 0.0
    valor_str = str(valor_str).strip()
    numeros = re.findall(r'[\d,]+', valor_str)
    if not numeros:
        return 0.0
    valor_limpo = numeros[0]
    if ',' in valor_limpo:
        partes = valor_limpo.split(',')
        parte_inteira = ''.join(partes[:-1]).replace('.', '')
        parte_decimal = partes[-1][:2]
        parte_decimal = parte_decimal.ljust(2, '0')[:2]
        if not parte_inteira:
            parte_inteira = '0'
        valor_numero = float(f"{parte_inteira}.{parte_decimal}")
    else:
        valor_limpo = valor_limpo.replace('.', '')
        valor_numero = float(valor_limpo)
    return round(valor_numero, 2)

# ============================================
# FUNÇÕES DE EXPORTAÇÃO
# ============================================
def converter_para_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Dados')
    return output.getvalue()

def converter_para_csv(df):
    return df.to_csv(index=False).encode('utf-8')

# ============================================
# CONEXÃO COM GOOGLE SHEETS
# ============================================
@st.cache_resource
def conectar_google_sheets():
    try:
        credenciais_dict = None
        if os.path.exists('credentials.json'):
            with open('credentials.json', 'r') as f:
                credenciais_dict = json.load(f)
        if not credenciais_dict and hasattr(st, 'secrets') and 'google' in st.secrets:
            credenciais_dict = {
                "type": st.secrets["google"].get("type"),
                "project_id": st.secrets["google"].get("project_id"),
                "private_key_id": st.secrets["google"].get("private_key_id"),
                "private_key": st.secrets["google"].get("private_key"),
                "client_email": st.secrets["google"].get("client_email"),
                "client_id": st.secrets["google"].get("client_id"),
                "auth_uri": st.secrets["google"].get("auth_uri"),
                "token_uri": st.secrets["google"].get("token_uri")
            }
        if not credenciais_dict or not credenciais_dict.get('private_key'):
            st.error("❌ Credenciais não encontradas!")
            return None
        creds = ServiceAccountCredentials.from_json_keyfile_dict(credenciais_dict, ESCOPOS)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"❌ Erro: {str(e)}")
        return None

def carregar_dados_historicos():
    try:
        cliente = conectar_google_sheets()
        if not cliente:
            return None
        planilha = cliente.open_by_key(ID_PLANILHA_CADASTRO)
        try:
            aba_historico = planilha.worksheet("Historico")
            dados = aba_historico.get_all_values()
            if len(dados) > 1:
                df = pd.DataFrame(dados[1:], columns=dados[0])
                df['VALOR_NUM'] = df['VALOR'].apply(converter_valor_para_numero)
                df['VALOR_EXIBICAO'] = df['VALOR_NUM'].apply(formatar_moeda)
                df['DATA_CONVERTIDA'] = pd.to_datetime(df['DATA'], format='%d/%m/%Y', errors='coerce')
                return df
            return pd.DataFrame()
        except Exception as e:
            st.error(f"Erro ao ler histórico: {e}")
            return None
    except Exception as e:
        st.error(f"Erro: {e}")
        return None

def carregar_dados_cadastro():
    try:
        cliente = conectar_google_sheets()
        if not cliente:
            return None
        planilha = cliente.open_by_key(ID_PLANILHA_CADASTRO)
        try:
            aba_cadastro = planilha.worksheet("Cadastro")
            dados = aba_cadastro.get_all_values()
            if len(dados) > 1:
                df = pd.DataFrame(dados[1:], columns=dados[0])
                df = df.rename(columns={
                    'RAZÃO SOCIAL': 'RAZAO_SOCIAL',
                    'CNPJ': 'CNPJ',
                    'INSCRIÇÃO ESTADUAL': 'IE',
                    'ENDEREÇO': 'ENDERECO',
                    'E-MAIL': 'EMAIL',
                    'NÚMERO': 'NUMERO',
                    'BAIRRO': 'BAIRRO',
                    'CEP': 'CEP',
                    'TEL/CONTATO': 'TELEFONE',
                    'UF': 'UF',
                    'DATA_CADASTRO': 'DATA_CADASTRO',
                    'HORA_CADASTRO': 'HORA_CADASTRO'
                })
                df['CNPJ_FORMATADO'] = df['CNPJ'].apply(formatar_cnpj)
                df['TELEFONE_FORMATADO'] = df['TELEFONE'].apply(formatar_telefone)
                df['DATA_DT'] = pd.to_datetime(df['DATA_CADASTRO'], format='%d/%m/%Y', errors='coerce')
                return df
            return pd.DataFrame()
        except Exception as e:
            st.error(f"Erro ao ler cadastro: {e}")
            return None
    except Exception as e:
        st.error(f"Erro: {e}")
        return None

# ============================================
# CSS TEMA CLARO
# ============================================
st.markdown("""
<style>
    .stApp { background: #F8FAFC; }
    [data-testid="stSidebar"] { background: white; border-right: 1px solid #E2E8F0; }
    [data-testid="stSidebar"] * { color: #1E293B !important; }
    .sidebar-title {
        font-size: 18px;
        font-weight: 700;
        border-bottom: 2px solid #3B82F6;
        padding-bottom: 10px;
        margin-bottom: 20px;
        color: #0F172A;
    }
    .filter-section {
        background: #F1F5F9;
        border-radius: 12px;
        padding: 12px;
        margin-bottom: 20px;
    }
    .filter-section p { font-weight: 600; margin-bottom: 8px; }
    .main-header {
        background: linear-gradient(135deg, #3B82F6 0%, #1D4ED8 100%);
        border-radius: 20px;
        padding: 24px 32px;
        margin-bottom: 24px;
        color: white;
    }
    .main-header h1 { font-size: 24px; margin: 0 0 4px 0; }
    .main-header p { font-size: 13px; opacity: 0.9; margin: 0; }
    .update-time { font-size: 11px; color: #64748B; margin-bottom: 16px; }
    .metric-card {
        background: white;
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        border: 1px solid #E2E8F0;
        text-align: center;
        transition: all 0.2s;
    }
    .metric-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
    .metric-icon { font-size: 32px; margin-bottom: 8px; }
    .metric-title { font-size: 12px; color: #64748B; text-transform: uppercase; letter-spacing: 0.5px; }
    .metric-value { font-size: 32px; font-weight: 700; color: #0F172A; margin: 8px 0 4px 0; }
    .metric-sub { font-size: 11px; color: #94A3B8; }
    .section-title {
        font-size: 18px;
        font-weight: 600;
        color: #0F172A;
        margin-bottom: 20px;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .section-title span {
        background: #3B82F6;
        width: 4px;
        height: 20px;
        border-radius: 2px;
        display: inline-block;
    }
    .ranking-row {
        display: flex;
        align-items: center;
        padding: 12px 0;
        border-bottom: 1px solid #F1F5F9;
    }
    .ranking-row:hover { background: #F8FAFC; }
    .ranking-position { width: 60px; font-weight: 700; color: #3B82F6; }
    .ranking-client { flex: 2; font-weight: 500; color: #1E293B; }
    .ranking-value { width: 150px; text-align: right; font-weight: 700; color: #059669; }
    .cliente-card {
        background: white;
        border-radius: 12px;
        padding: 16px;
        border: 1px solid #E2E8F0;
        transition: all 0.2s;
    }
    .cliente-card:hover { transform: translateY(-2px); border-color: #3B82F6; box-shadow: 0 4px 12px rgba(59,130,246,0.1); }
    .cliente-nome { font-size: 16px; font-weight: 700; color: #0F172A; margin-bottom: 8px; }
    .cliente-info { font-size: 13px; color: #64748B; margin-bottom: 4px; }
    .footer {
        text-align: center;
        padding: 24px;
        margin-top: 32px;
        border-top: 1px solid #E2E8F0;
        color: #94A3B8;
        font-size: 12px;
    }
</style>
""", unsafe_allow_html=True)

# ============================================
# FUNÇÃO DO MAPA
# ============================================
def criar_mapa_brasil(df):
    coords_estados = {
        'SP': {'lat': -23.55, 'lon': -46.63, 'nome': 'São Paulo'},
        'RJ': {'lat': -22.90, 'lon': -43.20, 'nome': 'Rio de Janeiro'},
        'MG': {'lat': -19.92, 'lon': -43.94, 'nome': 'Minas Gerais'},
        'RS': {'lat': -30.03, 'lon': -51.23, 'nome': 'Rio Grande do Sul'},
        'SC': {'lat': -27.60, 'lon': -48.55, 'nome': 'Santa Catarina'},
        'PR': {'lat': -25.43, 'lon': -49.27, 'nome': 'Paraná'},
        'BA': {'lat': -12.97, 'lon': -38.51, 'nome': 'Bahia'},
        'PE': {'lat': -8.05, 'lon': -34.90, 'nome': 'Pernambuco'},
        'CE': {'lat': -3.73, 'lon': -38.53, 'nome': 'Ceará'},
        'DF': {'lat': -15.83, 'lon': -47.86, 'nome': 'Brasília'},
        'GO': {'lat': -16.68, 'lon': -49.25, 'nome': 'Goiás'},
        'MT': {'lat': -15.60, 'lon': -56.10, 'nome': 'Mato Grosso'},
        'MS': {'lat': -20.44, 'lon': -54.65, 'nome': 'Mato Grosso do Sul'},
        'ES': {'lat': -20.32, 'lon': -40.34, 'nome': 'Espírito Santo'}
    }
    df_uf = df.groupby('UF')['VALOR_NUM'].sum().reset_index()
    mapa_dados = []
    for _, row in df_uf.iterrows():
        uf = row['UF']
        if uf in coords_estados:
            mapa_dados.append({
                'lat': coords_estados[uf]['lat'],
                'lon': coords_estados[uf]['lon'],
                'uf': uf,
                'nome': coords_estados[uf]['nome'],
                'valor': row['VALOR_NUM'],
                'valor_texto': formatar_moeda(row['VALOR_NUM'])
            })
    if not mapa_dados:
        return None
    fig = go.Figure()
    valores = [d['valor'] for d in mapa_dados]
    max_valor = max(valores) if valores else 1
    min_size, max_size = 15, 60
    fig.add_trace(go.Scattermapbox(
        lat=[d['lat'] for d in mapa_dados],
        lon=[d['lon'] for d in mapa_dados],
        mode='markers+text',
        marker=dict(
            size=[min_size + (v / max_valor) * (max_size - min_size) for v in valores],
            color=[d['valor'] for d in mapa_dados],
            colorscale='Blues',
            showscale=True,
            colorbar=dict(title="Valor (R$)", tickformat=",.0f"),
            sizemin=min_size, sizemode='diameter'
        ),
        text=[d['uf'] for d in mapa_dados],
        textposition='top center',
        textfont=dict(size=12, color='#1E293B'),
        hovertext=[f"<b>{d['nome']}</b><br>Valor: {d['valor_texto']}" for d in mapa_dados],
        hoverinfo='text'
    ))
    fig.update_layout(
        mapbox=dict(style='open-street-map', center=dict(lat=-15.78, lon=-47.93), zoom=3.8),
        height=450, margin=dict(l=0, r=0, t=0, b=0), showlegend=False
    )
    return fig

# ============================================
# PÁGINA DE GERENCIAMENTO DE CADASTROS
# ============================================
def pagina_gerenciamento_cadastros(df_cadastro):
    st.markdown("<div class='section-title'><span></span>📇 Gestão de Cadastros</div>", unsafe_allow_html=True)
    
    # Filtros
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        uf_cad_filter = st.multiselect("Filtrar por UF", df_cadastro['UF'].unique().tolist() if not df_cadastro.empty else [], default=[])
    with col_f2:
        busca_cad = st.text_input("Buscar por nome, CNPJ ou e-mail", placeholder="Digite para buscar...")
    with col_f3:
        periodo_cad = st.selectbox("Período de cadastro", ["Todos", "Últimos 30 dias", "Últimos 60 dias", "Últimos 90 dias"])
    
    # Aplicar filtros
    df_cad_filtrado = df_cadastro.copy()
    if uf_cad_filter:
        df_cad_filtrado = df_cad_filtrado[df_cad_filtrado['UF'].isin(uf_cad_filter)]
    if busca_cad:
        busca_lower = busca_cad.lower()
        df_cad_filtrado = df_cad_filtrado[
            df_cad_filtrado['RAZAO_SOCIAL'].str.lower().str.contains(busca_lower, na=False) |
            df_cad_filtrado['CNPJ'].str.contains(busca_cad, na=False) |
            df_cad_filtrado['EMAIL'].str.lower().str.contains(busca_lower, na=False)
        ]
    if periodo_cad != "Todos" and 'DATA_DT' in df_cad_filtrado.columns:
        hoje = datetime.now()
        if periodo_cad == "Últimos 30 dias":
            df_cad_filtrado = df_cad_filtrado[df_cad_filtrado['DATA_DT'] >= hoje - timedelta(days=30)]
        elif periodo_cad == "Últimos 60 dias":
            df_cad_filtrado = df_cad_filtrado[df_cad_filtrado['DATA_DT'] >= hoje - timedelta(days=60)]
        elif periodo_cad == "Últimos 90 dias":
            df_cad_filtrado = df_cad_filtrado[df_cad_filtrado['DATA_DT'] >= hoje - timedelta(days=90)]
    
    # Métricas de cadastro
    col_a1, col_a2, col_a3, col_a4 = st.columns(4)
    with col_a1:
        st.metric("Total de Cadastros", len(df_cad_filtrado))
    with col_a2:
        st.metric("Estados Atendidos", df_cad_filtrado['UF'].nunique() if not df_cad_filtrado.empty else 0)
    with col_a3:
        st.metric("Total Cadastros Geral", len(df_cadastro))
    with col_a4:
        taxa = (len(df_cad_filtrado) / len(df_cadastro) * 100) if len(df_cadastro) > 0 else 0
        st.metric("Filtrados", f"{taxa:.0f}%")
    
    st.markdown("---")
    
    # Gráficos de cadastro
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        st.markdown("#### 📍 Cadastros por Estado")
        if not df_cad_filtrado.empty:
            df_uf_cad = df_cad_filtrado.groupby('UF').size().reset_index(name='quantidade')
            fig = px.bar(df_uf_cad, x='UF', y='quantidade', text='quantidade', color='quantidade', color_continuous_scale='Blues')
            fig.update_layout(showlegend=False, height=300)
            st.plotly_chart(fig, use_container_width=True)
    with col_g2:
        st.markdown("#### 📅 Cadastros por Mês")
        if not df_cad_filtrado.empty and 'DATA_DT' in df_cad_filtrado.columns:
            df_mes = df_cad_filtrado.groupby(df_cad_filtrado['DATA_DT'].dt.strftime('%b/%Y')).size().reset_index(name='quantidade')
            df_mes.columns = ['Mês', 'quantidade']
            fig = px.line(df_mes, x='Mês', y='quantidade', markers=True, color_discrete_sequence=['#3B82F6'])
            fig.update_layout(height=300)
            st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    
    # Exportar cadastros
    col_e1, col_e2 = st.columns([1, 5])
    with col_e1:
        df_export = df_cad_filtrado[['RAZAO_SOCIAL', 'CNPJ_FORMATADO', 'EMAIL', 'TELEFONE_FORMATADO', 'UF', 'DATA_CADASTRO']].copy()
        df_export.columns = ['Razão Social', 'CNPJ', 'E-mail', 'Telefone', 'UF', 'Data Cadastro']
        excel_data = converter_para_excel(df_export)
        st.download_button("📊 Exportar Excel", data=excel_data, file_name=f"cadastros_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx", use_container_width=True)
    
    # Tabela de cadastros
    df_exibicao_cad = df_cad_filtrado[['RAZAO_SOCIAL', 'CNPJ_FORMATADO', 'EMAIL', 'TELEFONE_FORMATADO', 'UF', 'DATA_CADASTRO']].copy()
    df_exibicao_cad.columns = ['Razão Social', 'CNPJ', 'E-mail', 'Telefone', 'UF', 'Cadastro']
    st.dataframe(df_exibicao_cad, use_container_width=True, hide_index=True)
    st.caption(f"📊 Total de {len(df_exibicao_cad)} cadastros encontrados")
    
    st.markdown("---")
    
    # Detalhes do cliente (selecionável)
    st.markdown("#### 🔍 Detalhes do Cliente")
    clientes_lista = df_cad_filtrado['RAZAO_SOCIAL'].tolist() if not df_cad_filtrado.empty else []
    if clientes_lista:
        cliente_selecionado = st.selectbox("Selecione um cliente para ver detalhes completos:", clientes_lista)
        if cliente_selecionado:
            cliente_data = df_cad_filtrado[df_cad_filtrado['RAZAO_SOCIAL'] == cliente_selecionado].iloc[0]
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                st.markdown(f"""
                <div class='cliente-card'>
                    <div class='cliente-nome'>🏢 {cliente_data['RAZAO_SOCIAL']}</div>
                    <div class='cliente-info'>📄 CNPJ: {cliente_data['CNPJ_FORMATADO']}</div>
                    <div class='cliente-info'>🔢 IE: {cliente_data['IE'] if pd.notna(cliente_data['IE']) else '-'}</div>
                    <div class='cliente-info'>📧 E-mail: {cliente_data['EMAIL']}</div>
                    <div class='cliente-info'>📞 Telefone: {cliente_data['TELEFONE_FORMATADO']}</div>
                </div>
                """, unsafe_allow_html=True)
            with col_d2:
                st.markdown(f"""
                <div class='cliente-card'>
                    <div class='cliente-nome'>📍 Endereço</div>
                    <div class='cliente-info'>🏠 {cliente_data['ENDERECO']}, {cliente_data['NUMERO']}</div>
                    <div class='cliente-info'>🏘️ Bairro: {cliente_data['BAIRRO']}</div>
                    <div class='cliente-info'>📮 CEP: {cliente_data['CEP']}</div>
                    <div class='cliente-info'>🗺️ UF: {cliente_data['UF']}</div>
                </div>
                """, unsafe_allow_html=True)
            col_b1, col_b2, col_b3 = st.columns(3)
            with col_b1:
                if cliente_data['EMAIL'] and pd.notna(cliente_data['EMAIL']):
                    st.markdown(f'<a href="mailto:{cliente_data["EMAIL"]}" target="_blank"><button style="width:100%; background:#3B82F6; color:white; border:none; border-radius:8px; padding:8px;">✉️ Enviar E-mail</button></a>', unsafe_allow_html=True)
            with col_b2:
                if cliente_data['TELEFONE'] and pd.notna(cliente_data['TELEFONE']):
                    telefone_clean = str(cliente_data['TELEFONE']).replace(' ', '').replace('(', '').replace(')', '').replace('-', '')
                    st.markdown(f'<a href="https://wa.me/55{telefone_clean}" target="_blank"><button style="width:100%; background:#25D366; color:white; border:none; border-radius:8px; padding:8px;">💬 WhatsApp</button></a>', unsafe_allow_html=True)
            with col_b3:
                st.markdown(f'<a href="https://www.google.com/maps/search/{cliente_data["ENDERECO"]}+{cliente_data["NUMERO"]}+{cliente_data["BAIRRO"]}" target="_blank"><button style="width:100%; background:#EF4444; color:white; border:none; border-radius:8px; padding:8px;">🗺️ Ver Mapa</button></a>', unsafe_allow_html=True)

# ============================================
# PÁGINA DE ANÁLISE DE ORÇAMENTOS
# ============================================
def pagina_analise_orcamentos(df_historico):
    # SIDEBAR COM FILTROS
    with st.sidebar:
        st.markdown("<div class='sidebar-title'>🔍 FILTROS</div>", unsafe_allow_html=True)
        
        st.markdown("<div class='filter-section'>", unsafe_allow_html=True)
        st.markdown("**📅 Período**")
        tipo_periodo = st.radio("Tipo de período", ["Pré-definido", "Personalizado"], label_visibility="collapsed", horizontal=True)
        if tipo_periodo == "Pré-definido":
            periodo = st.selectbox("Selecione", ["Todos", "Últimos 30 dias", "Últimos 60 dias", "Últimos 90 dias", "Este mês", "Mês passado"], label_visibility="collapsed")
            data_inicio, data_fim = None, None
        else:
            st.markdown("**Data inicial**")
            data_inicio = st.date_input("Data inicial", value=datetime.now() - timedelta(days=30), label_visibility="collapsed")
            st.markdown("**Data final**")
            data_fim = st.date_input("Data final", value=datetime.now(), label_visibility="collapsed")
            periodo = "Personalizado"
        st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("<div class='filter-section'>", unsafe_allow_html=True)
        st.markdown("**📍 Estado**")
        uf_filter = st.multiselect("UF", ["SP", "RJ", "MG", "RS", "SC", "PR", "BA", "PE", "CE", "DF", "GO", "MT", "MS", "ES"], default=[], label_visibility="collapsed", placeholder="Todos os estados")
        st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("<div class='filter-section'>", unsafe_allow_html=True)
        st.markdown("**💳 Pagamento**")
        pag_filter = st.multiselect("Pagamento", ["VISTA", "30", "45", "60", "PREÇO BASE"], default=[], label_visibility="collapsed", placeholder="Todas as formas")
        st.markdown("</div>", unsafe_allow_html=True)
        
        if st.button("🗑️ Limpar Filtros", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    
    # APLICAR FILTROS
    df_filtrado = df_historico.copy()
    if periodo != "Todos" and periodo != "Personalizado" and 'DATA_CONVERTIDA' in df_filtrado.columns:
        hoje = datetime.now()
        if periodo == "Últimos 30 dias":
            df_filtrado = df_filtrado[df_filtrado['DATA_CONVERTIDA'] >= hoje - timedelta(days=30)]
        elif periodo == "Últimos 60 dias":
            df_filtrado = df_filtrado[df_filtrado['DATA_CONVERTIDA'] >= hoje - timedelta(days=60)]
        elif periodo == "Últimos 90 dias":
            df_filtrado = df_filtrado[df_filtrado['DATA_CONVERTIDA'] >= hoje - timedelta(days=90)]
        elif periodo == "Este mês":
            df_filtrado = df_filtrado[df_filtrado['DATA_CONVERTIDA'] >= hoje.replace(day=1)]
        elif periodo == "Mês passado":
            primeiro_dia = (hoje.replace(day=1) - timedelta(days=1)).replace(day=1)
            ultimo_dia = hoje.replace(day=1) - timedelta(days=1)
            df_filtrado = df_filtrado[(df_filtrado['DATA_CONVERTIDA'] >= primeiro_dia) & (df_filtrado['DATA_CONVERTIDA'] <= ultimo_dia)]
    if tipo_periodo == "Personalizado" and data_inicio and data_fim:
        df_filtrado = df_filtrado[(df_filtrado['DATA_CONVERTIDA'] >= pd.to_datetime(data_inicio)) & (df_filtrado['DATA_CONVERTIDA'] <= pd.to_datetime(data_fim))]
    if uf_filter and 'UF' in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado['UF'].isin(uf_filter)]
    if pag_filter and 'FORMA_PAGAMENTO' in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado['FORMA_PAGAMENTO'].isin(pag_filter)]
    
    # MÉTRICAS
    total_orcamentos = len(df_filtrado)
    total_clientes = df_filtrado['CNPJ'].nunique() if 'CNPJ' in df_filtrado.columns else 0
    valor_total = df_filtrado['VALOR_NUM'].sum()
    ticket_medio = valor_total / total_orcamentos if total_orcamentos > 0 else 0
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"<div class='metric-card'><div class='metric-icon'>📋</div><div class='metric-title'>Total de Orçamentos</div><div class='metric-value'>{total_orcamentos}</div><div class='metric-sub'>Orçamentos gerados</div></div>", unsafe_allow_html=True)
    with col2:
        st.markdown(f"<div class='metric-card'><div class='metric-icon'>🏢</div><div class='metric-title'>Clientes Ativos</div><div class='metric-value'>{total_clientes}</div><div class='metric-sub'>Empresas cadastradas</div></div>", unsafe_allow_html=True)
    with col3:
        st.markdown(f"<div class='metric-card'><div class='metric-icon'>💰</div><div class='metric-title'>Valor Total Orçado</div><div class='metric-value'>{formatar_moeda(valor_total)}</div><div class='metric-sub'>Soma de todos os orçamentos</div></div>", unsafe_allow_html=True)
    with col4:
        st.markdown(f"<div class='metric-card'><div class='metric-icon'>🎯</div><div class='metric-title'>Ticket Médio</div><div class='metric-value'>{formatar_moeda(ticket_medio)}</div><div class='metric-sub'>Média por orçamento</div></div>", unsafe_allow_html=True)
    
    st.markdown("---")
    
    # ANÁLISE REGIONAL
    st.markdown("<div class='section-title'><span></span>📍 Análise Regional</div>", unsafe_allow_html=True)
    if 'UF' in df_filtrado.columns and not df_filtrado.empty and df_filtrado['VALOR_NUM'].sum() > 0:
        mapa = criar_mapa_brasil(df_filtrado)
        if mapa:
            st.plotly_chart(mapa, use_container_width=True)
        st.markdown("<br>", unsafe_allow_html=True)
        df_uf = df_filtrado.groupby('UF')['VALOR_NUM'].sum().reset_index().sort_values('VALOR_NUM', ascending=False)
        cols = st.columns(4)
        for i, row in df_uf.iterrows():
            percentual = (row['VALOR_NUM'] / valor_total * 100) if valor_total > 0 else 0
            with cols[i % 4]:
                st.markdown(f"<div class='uf-card'><div class='uf-nome'>{row['UF']}</div><div class='uf-valor'>{formatar_moeda(row['VALOR_NUM'])}</div><div class='uf-percentual'>{percentual:.1f}% do total</div></div>", unsafe_allow_html=True)
    else:
        st.info("Nenhum dado regional disponível para o período selecionado")
    
    st.markdown("---")
    
    # RANKING DE CLIENTES
    st.markdown("<div class='section-title'><span></span>🏆 Top Clientes</div>", unsafe_allow_html=True)
    if 'VALOR_NUM' in df_filtrado.columns and df_filtrado['VALOR_NUM'].sum() > 0:
        ranking = df_filtrado.groupby(['CNPJ', 'RAZÃO SOCIAL'])['VALOR_NUM'].sum().reset_index().sort_values('VALOR_NUM', ascending=False).head(5)
        for i, row in ranking.iterrows():
            st.markdown(f"<div class='ranking-row'><div class='ranking-position'>#{i+1}</div><div class='ranking-client'>{row['RAZÃO SOCIAL']}</div><div class='ranking-value'>{formatar_moeda(row['VALOR_NUM'])}</div></div>", unsafe_allow_html=True)
    else:
        st.info("Nenhum dado de clientes disponível para o período selecionado")
    
    st.markdown("---")
    
    # TABELA DE ORÇAMENTOS
    st.markdown("<div class='section-title'><span></span>📋 Todos os Orçamentos</div>", unsafe_allow_html=True)
    col_btn1, col_btn2 = st.columns([1, 5])
    with col_btn1:
        excel_data = converter_para_excel(df_filtrado)
        st.download_button("📊 Exportar Excel", data=excel_data, file_name=f"orcamentos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx", use_container_width=True)
        csv_data = converter_para_csv(df_filtrado)
        st.download_button("📄 Exportar CSV", data=csv_data, file_name=f"orcamentos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", use_container_width=True)
    st.markdown("<br>", unsafe_allow_html=True)
    
    colunas_exibicao = {'DATA': 'Data', 'RAZÃO SOCIAL': 'Cliente', 'CNPJ': 'CNPJ', 'UF': 'UF', 'VALOR_EXIBICAO': 'Valor', 'FORMA_PAGAMENTO': 'Pagamento', 'QTD_ITENS': 'Qtd Itens', 'TIPO_CLIENTE': 'Tipo Cliente'}
    colunas_presentes = [col for col in colunas_exibicao.keys() if col in df_filtrado.columns]
    df_exibicao = df_filtrado[colunas_presentes].rename(columns={k: v for k, v in colunas_exibicao.items() if k in colunas_presentes})
    if 'DATA' in df_exibicao.columns:
        df_exibicao = df_exibicao.sort_values('DATA', ascending=False)
    st.dataframe(df_exibicao, use_container_width=True, hide_index=True)
    st.caption(f"📊 Total de {len(df_exibicao)} registros encontrados")

# ============================================
# MAIN
# ============================================
def main():
    # HEADER
    st.markdown("""
    <div class='main-header'>
        <h1>📊 Sistema de Gestão LUVidarte</h1>
        <p>Dashboard gerencial e gestão de cadastros integrados</p>
    </div>
    """, unsafe_allow_html=True)
    
    agora = datetime.now(TIMEZONE_BR)
    st.markdown(f"<div class='update-time'>📅 Última atualização: {agora.strftime('%d/%m/%Y %H:%M:%S')}</div>", unsafe_allow_html=True)
    
    # CARREGAR DADOS
    with st.spinner("🔄 Carregando dados..."):
        df_historico = carregar_dados_historicos()
        df_cadastro = carregar_dados_cadastro()
    
    if df_historico is None or df_cadastro is None:
        st.error("❌ Erro ao carregar dados. Verifique a conexão com o Google Sheets.")
        return
    
    # TABS
    tab1, tab2 = st.tabs(["📊 Análise de Orçamentos", "📇 Gestão de Cadastros"])
    
    with tab1:
        if df_historico.empty:
            st.warning("⚠️ Nenhum orçamento encontrado. Aguarde os primeiros orçamentos.")
        else:
            pagina_analise_orcamentos(df_historico)
    
    with tab2:
        if df_cadastro.empty:
            st.warning("⚠️ Nenhum cadastro encontrado. Aguarde os primeiros cadastros.")
        else:
            pagina_gerenciamento_cadastros(df_cadastro)
    
    # RODAPÉ
    st.markdown("""
    <div class='footer'>
        <p>📊 Sistema atualizado automaticamente • Dados em tempo real • Conforme LGPD</p>
        <p>© 2026 LUVidarte - Todos os direitos reservados</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
