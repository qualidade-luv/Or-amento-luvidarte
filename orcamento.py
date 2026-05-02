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
# FUNÇÃO DE EXPORTAÇÃO
# ============================================
def converter_para_excel(df):
    """Converte DataFrame para Excel em memória"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Orçamentos')
    return output.getvalue()

def converter_para_csv(df):
    """Converte DataFrame para CSV em memória"""
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

def carregar_dados():
    try:
        cliente = conectar_google_sheets()
        if not cliente:
            return None, None
        
        planilha = cliente.open_by_key(ID_PLANILHA_CADASTRO)
        
        try:
            aba_historico = planilha.worksheet("Historico")
            dados = aba_historico.get_all_values()
            
            if len(dados) > 1:
                df = pd.DataFrame(dados[1:], columns=dados[0])
                
                df['VALOR_NUM'] = df['VALOR'].apply(converter_valor_para_numero)
                df['VALOR_EXIBICAO'] = df['VALOR_NUM'].apply(formatar_moeda)
                df['DATA_CONVERTIDA'] = pd.to_datetime(df['DATA'], format='%d/%m/%Y', errors='coerce')
                
                return None, df
            else:
                return None, None
                
        except Exception as e:
            st.error(f"Erro ao ler planilha: {e}")
            return None, None
            
    except Exception as e:
        st.error(f"Erro: {e}")
        return None, None

# ============================================
# CSS TEMA CLARO
# ============================================
st.markdown("""
<style>
    .stApp {
        background: #F8FAFC;
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background: white;
        border-right: 1px solid #E2E8F0;
    }
    [data-testid="stSidebar"] * {
        color: #1E293B !important;
    }
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
    .filter-section p {
        font-weight: 600;
        margin-bottom: 8px;
    }
    
    /* Header */
    .main-header {
        background: linear-gradient(135deg, #3B82F6 0%, #1D4ED8 100%);
        border-radius: 20px;
        padding: 24px 32px;
        margin-bottom: 24px;
        color: white;
    }
    .main-header h1 {
        font-size: 24px;
        margin: 0 0 4px 0;
    }
    .main-header p {
        font-size: 13px;
        opacity: 0.9;
        margin: 0;
    }
    .update-time {
        font-size: 11px;
        color: #64748B;
        margin-bottom: 16px;
    }
    
    /* Cards principais */
    .metric-card {
        background: white;
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        border: 1px solid #E2E8F0;
        text-align: center;
        transition: all 0.2s;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }
    .metric-icon {
        font-size: 32px;
        margin-bottom: 8px;
    }
    .metric-title {
        font-size: 12px;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        font-weight: 500;
    }
    .metric-value {
        font-size: 32px;
        font-weight: 700;
        color: #0F172A;
        margin: 8px 0 4px 0;
    }
    .metric-sub {
        font-size: 11px;
        color: #94A3B8;
    }
    
    /* Cards de UF */
    .uf-card {
        background: white;
        border-radius: 12px;
        padding: 12px;
        text-align: center;
        border: 1px solid #E2E8F0;
        transition: all 0.2s;
    }
    .uf-card:hover {
        transform: translateY(-2px);
        border-color: #3B82F6;
        box-shadow: 0 4px 12px rgba(59,130,246,0.1);
    }
    .uf-nome {
        font-size: 14px;
        font-weight: 600;
        color: #1E293B;
        margin-bottom: 4px;
    }
    .uf-valor {
        font-size: 12px;
        font-weight: 700;
        color: #059669;
    }
    .uf-percentual {
        font-size: 10px;
        color: #64748B;
    }
    
    /* Seções */
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
    
    /* Ranking */
    .ranking-row {
        display: flex;
        align-items: center;
        padding: 12px 0;
        border-bottom: 1px solid #F1F5F9;
    }
    .ranking-row:hover {
        background: #F8FAFC;
    }
    .ranking-position {
        width: 60px;
        font-weight: 700;
        color: #3B82F6;
    }
    .ranking-client {
        flex: 2;
        font-weight: 500;
        color: #1E293B;
    }
    .ranking-value {
        width: 150px;
        text-align: right;
        font-weight: 700;
        color: #059669;
    }
    
    /* Export buttons */
    .export-buttons {
        display: flex;
        gap: 12px;
        margin-bottom: 20px;
        justify-content: flex-end;
    }
    
    /* Footer */
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
    """Cria mapa do Brasil com faturamento por estado"""
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
    min_size = 15
    max_size = 60
    
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
            sizemin=min_size,
            sizemode='diameter'
        ),
        text=[d['uf'] for d in mapa_dados],
        textposition='top center',
        textfont=dict(size=12, color='#1E293B'),
        hovertext=[f"<b>{d['nome']}</b><br>Valor: {d['valor_texto']}" for d in mapa_dados],
        hoverinfo='text'
    ))
    
    fig.update_layout(
        mapbox=dict(
            style='open-street-map',
            center=dict(lat=-15.78, lon=-47.93),
            zoom=3.8
        ),
        height=450,
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False
    )
    
    return fig

# ============================================
# MAIN
# ============================================

def main():
    # HEADER
    st.markdown("""
    <div class='main-header'>
        <h1>📊 Análise de Orçamentos</h1>
        <p>Dashboard gerencial com métricas e indicadores de performance</p>
    </div>
    """, unsafe_allow_html=True)
    
    agora = datetime.now(TIMEZONE_BR)
    st.markdown(f"<div class='update-time'>📅 Última atualização: {agora.strftime('%d/%m/%Y %H:%M:%S')}</div>", unsafe_allow_html=True)
    
    # SIDEBAR COM FILTROS
    with st.sidebar:
        st.markdown("<div class='sidebar-title'>🔍 FILTROS</div>", unsafe_allow_html=True)
        
        # Período
        st.markdown("<div class='filter-section'>", unsafe_allow_html=True)
        st.markdown("**📅 Período**")
        
        tipo_periodo = st.radio(
            "Tipo de período",
            ["Pré-definido", "Personalizado"],
            label_visibility="collapsed",
            horizontal=True
        )
        
        if tipo_periodo == "Pré-definido":
            periodo = st.selectbox(
                "Selecione",
                ["Todos", "Últimos 30 dias", "Últimos 60 dias", "Últimos 90 dias", "Este mês", "Mês passado"],
                label_visibility="collapsed"
            )
            data_inicio = None
            data_fim = None
        else:
            st.markdown("**Data inicial**")
            data_inicio = st.date_input("Data inicial", value=datetime.now() - timedelta(days=30), label_visibility="collapsed")
            st.markdown("**Data final**")
            data_fim = st.date_input("Data final", value=datetime.now(), label_visibility="collapsed")
            periodo = "Personalizado"
        
        st.markdown("</div>", unsafe_allow_html=True)
        
        # UF
        st.markdown("<div class='filter-section'>", unsafe_allow_html=True)
        st.markdown("**📍 Estado**")
        uf_filter = st.multiselect(
            "UF",
            ["SP", "RJ", "MG", "RS", "SC", "PR", "BA", "PE", "CE", "DF", "GO", "MT", "MS", "ES"],
            default=[],
            label_visibility="collapsed",
            placeholder="Todos os estados"
        )
        st.markdown("</div>", unsafe_allow_html=True)
        
        # Forma de Pagamento
        st.markdown("<div class='filter-section'>", unsafe_allow_html=True)
        st.markdown("**💳 Pagamento**")
        pag_filter = st.multiselect(
            "Pagamento",
            ["VISTA", "30", "45", "60", "PREÇO BASE"],
            default=[],
            label_visibility="collapsed",
            placeholder="Todas as formas"
        )
        st.markdown("</div>", unsafe_allow_html=True)
        
        # Botão limpar
        if st.button("🗑️ Limpar Filtros", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    
    # CARREGAR DADOS
    with st.spinner("🔄 Carregando dados..."):
        _, df = carregar_dados()
    
    if df is None or df.empty:
        st.warning("⚠️ Nenhum dado encontrado nas planilhas. Aguarde os primeiros orçamentos.")
        return
    
    # APLICAR FILTROS
    df_filtrado = df.copy()
    
    if periodo != "Todos" and periodo != "Personalizado" and 'DATA_CONVERTIDA' in df_filtrado.columns:
        hoje = datetime.now()
        if periodo == "Últimos 30 dias":
            df_filtrado = df_filtrado[df_filtrado['DATA_CONVERTIDA'] >= hoje - timedelta(days=30)]
        elif periodo == "Últimos 60 dias":
            df_filtrado = df_filtrado[df_filtrado['DATA_CONVERTIDA'] >= hoje - timedelta(days=60)]
        elif periodo == "Últimos 90 dias":
            df_filtrado = df_filtrado[df_filtrado['DATA_CONVERTIDA'] >= hoje - timedelta(days=90)]
        elif periodo == "Este mês":
            inicio_mes = hoje.replace(day=1)
            df_filtrado = df_filtrado[df_filtrado['DATA_CONVERTIDA'] >= inicio_mes]
        elif periodo == "Mês passado":
            primeiro_dia = (hoje.replace(day=1) - timedelta(days=1)).replace(day=1)
            ultimo_dia = hoje.replace(day=1) - timedelta(days=1)
            df_filtrado = df_filtrado[(df_filtrado['DATA_CONVERTIDA'] >= primeiro_dia) & 
                                      (df_filtrado['DATA_CONVERTIDA'] <= ultimo_dia)]
    
    if tipo_periodo == "Personalizado" and data_inicio and data_fim:
        df_filtrado = df_filtrado[(df_filtrado['DATA_CONVERTIDA'] >= pd.to_datetime(data_inicio)) & 
                                  (df_filtrado['DATA_CONVERTIDA'] <= pd.to_datetime(data_fim))]
    
    if uf_filter and 'UF' in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado['UF'].isin(uf_filter)]
    
    if pag_filter and 'FORMA_PAGAMENTO' in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado['FORMA_PAGAMENTO'].isin(pag_filter)]
    
    # MÉTRICAS PRINCIPAIS
    total_orcamentos = len(df_filtrado)
    total_clientes = df_filtrado['CNPJ'].nunique() if 'CNPJ' in df_filtrado.columns else 0
    valor_total = df_filtrado['VALOR_NUM'].sum()
    ticket_medio = valor_total / total_orcamentos if total_orcamentos > 0 else 0
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class='metric-card'>
            <div class='metric-icon'>📋</div>
            <div class='metric-title'>Total de Orçamentos</div>
            <div class='metric-value'>{total_orcamentos}</div>
            <div class='metric-sub'>Orçamentos gerados</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class='metric-card'>
            <div class='metric-icon'>🏢</div>
            <div class='metric-title'>Clientes Ativos</div>
            <div class='metric-value'>{total_clientes}</div>
            <div class='metric-sub'>Empresas cadastradas</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class='metric-card'>
            <div class='metric-icon'>💰</div>
            <div class='metric-title'>Valor Total Orçado</div>
            <div class='metric-value'>{formatar_moeda(valor_total)}</div>
            <div class='metric-sub'>Soma de todos os orçamentos</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class='metric-card'>
            <div class='metric-icon'>🎯</div>
            <div class='metric-title'>Ticket Médio</div>
            <div class='metric-value'>{formatar_moeda(ticket_medio)}</div>
            <div class='metric-sub'>Média por orçamento</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # ANÁLISE REGIONAL - MAPA + CARDS
    st.markdown("<div class='section-title'><span></span>📍 Análise Regional</div>", unsafe_allow_html=True)
    
    if 'UF' in df_filtrado.columns and not df_filtrado.empty and df_filtrado['VALOR_NUM'].sum() > 0:
        # Mapa
        mapa = criar_mapa_brasil(df_filtrado)
        if mapa:
            st.plotly_chart(mapa, use_container_width=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Cards por UF
        df_uf = df_filtrado.groupby('UF')['VALOR_NUM'].sum().reset_index()
        df_uf = df_uf.sort_values('VALOR_NUM', ascending=False)
        
        cols = st.columns(4)
        for i, row in df_uf.iterrows():
            percentual = (row['VALOR_NUM'] / valor_total * 100) if valor_total > 0 else 0
            with cols[i % 4]:
                st.markdown(f"""
                <div class='uf-card'>
                    <div class='uf-nome'>{row['UF']}</div>
                    <div class='uf-valor'>{formatar_moeda(row['VALOR_NUM'])}</div>
                    <div class='uf-percentual'>{percentual:.1f}% do total</div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("Nenhum dado regional disponível para o período selecionado")
    
    st.markdown("---")
    
    # RANKING DE CLIENTES
    st.markdown("<div class='section-title'><span></span>🏆 Top Clientes</div>", unsafe_allow_html=True)
    
    if 'VALOR_NUM' in df_filtrado.columns and df_filtrado['VALOR_NUM'].sum() > 0:
        ranking = df_filtrado.groupby(['CNPJ', 'RAZÃO SOCIAL'])['VALOR_NUM'].sum().reset_index()
        ranking = ranking.sort_values('VALOR_NUM', ascending=False).head(5)
        
        for i, row in ranking.iterrows():
            st.markdown(f"""
            <div class='ranking-row'>
                <div class='ranking-position'>#{i+1}</div>
                <div class='ranking-client'>{row['RAZÃO SOCIAL']}</div>
                <div class='ranking-value'>{formatar_moeda(row['VALOR_NUM'])}</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("Nenhum dado de clientes disponível para o período selecionado")
    
    st.markdown("---")
    
    # TABELA COMPLETA DE ORÇAMENTOS COM EXPORTAÇÃO
    st.markdown("<div class='section-title'><span></span>📋 Todos os Orçamentos</div>", unsafe_allow_html=True)
    
    # Botões de exportação
    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 4])
    
    with col_btn1:
        # Botão para exportar Excel
        excel_data = converter_para_excel(df_filtrado)
        st.download_button(
            label="📊 Exportar Excel",
            data=excel_data,
            file_name=f"orcamentos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    
    with col_btn2:
        # Botão para exportar CSV
        csv_data = converter_para_csv(df_filtrado)
        st.download_button(
            label="📄 Exportar CSV",
            data=csv_data,
            file_name=f"orcamentos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Preparar DataFrame para exibição
    df_exibicao = df_filtrado.copy()
    
    # Selecionar e renomear colunas para exibição
    colunas_exibicao = {
        'DATA': 'Data',
        'RAZÃO SOCIAL': 'Cliente',
        'CNPJ': 'CNPJ',
        'UF': 'UF',
        'VALOR_EXIBICAO': 'Valor',
        'FORMA_PAGAMENTO': 'Pagamento',
        'QTD_ITENS': 'Qtd Itens',
        'TIPO_CLIENTE': 'Tipo Cliente'
    }
    
    # Filtrar apenas colunas que existem
    colunas_presentes = [col for col in colunas_exibicao.keys() if col in df_exibicao.columns]
    df_exibicao = df_exibicao[colunas_presentes]
    df_exibicao = df_exibicao.rename(columns={k: v for k, v in colunas_exibicao.items() if k in colunas_presentes})
    
    # Ordenar por data (mais recente primeiro)
    if 'DATA' in df_exibicao.columns:
        df_exibicao = df_exibicao.sort_values('DATA', ascending=False)
    
    # Mostrar tabela completa com paginação
    st.dataframe(
        df_exibicao,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Valor": st.column_config.TextColumn("Valor", width="small"),
            "Cliente": st.column_config.TextColumn("Cliente", width="medium"),
            "CNPJ": st.column_config.TextColumn("CNPJ", width="small"),
        }
    )
    
    # Informação de quantos registros
    st.caption(f"📊 Total de {len(df_exibicao)} registros encontrados")
    
    # RODAPÉ
    st.markdown("""
    <div class='footer'>
        <p>📊 Dashboard atualizado automaticamente • Dados em tempo real • Conforme LGPD</p>
        <p>© 2026 LUVidarte - Todos os direitos reservados</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
