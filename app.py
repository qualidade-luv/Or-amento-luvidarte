import streamlit as st
import pandas as pd
import numpy as np
import re
from PIL import Image
import requests
from io import BytesIO
import base64
from datetime import datetime
import time
import urllib.parse

# ============================================
# CONFIGURAÇÃO DA PÁGINA (com favicon)
# ============================================
def carregar_logo_favicon():
    url_drive = "https://drive.google.com/uc?export=download&id=1wiwp3txOXGsEMRrUgzdLFlxQL2188uTw"
    try:
        response = requests.get(url_drive, timeout=10)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            img = img.resize((32, 32))
            return img
    except:
        pass
    return None

favicon = carregar_logo_favicon()
if favicon:
    st.set_page_config(
        page_title="Luvidarte - Catálogo Virtual",
        page_icon=favicon,
        layout="wide"
    )
else:
    st.set_page_config(
        page_title="Luvidarte - Catálogo Virtual",
        page_icon="📦",
        layout="wide"
    )

# ============================================
# INICIALIZAR SESSION STATE
# ============================================
if 'carrinho' not in st.session_state:
    st.session_state.carrinho = []
if 'pagina_atual' not in st.session_state:
    st.session_state.pagina_atual = 1
if 'carrinho_aberto' not in st.session_state:
    st.session_state.carrinho_aberto = False
if 'filtros_anteriores' not in st.session_state:
    st.session_state.filtros_anteriores = None

# ============================================
# FUNÇÃO PARA BUSCAR ALÍQUOTA ST (QUALQUER UF)
# ============================================
def buscar_aliquota_st(ncm: str, uf: str, df_st: pd.DataFrame) -> float:
    if df_st.empty or not ncm or not uf:
        return 0.0
    
    ncm_limpo = str(ncm).replace(".", "").strip()
    df_st['NCM_LIMPO'] = df_st.iloc[:, 1].astype(str).str.replace(".", "").str.strip()
    
    linha_ncm = df_st[df_st['NCM_LIMPO'] == ncm_limpo]
    if linha_ncm.empty:
        return 0.0
    
    uf_upper = uf.upper().strip()
    colunas_uf = {}
    for col in df_st.columns[2:]:
        col_clean = str(col).strip().upper()
        colunas_uf[col_clean] = col
    
    if uf_upper not in colunas_uf:
        for col_key in colunas_uf.keys():
            if uf_upper in col_key or col_key in uf_upper:
                nome_coluna = colunas_uf[col_key]
                break
        else:
            return 0.0
    else:
        nome_coluna = colunas_uf[uf_upper]
    
    valor = linha_ncm.iloc[0][nome_coluna]
    
    if pd.isna(valor):
        return 0.0
    
    if isinstance(valor, str):
        valor = valor.replace("%", "").replace(",", ".").strip()
    
    try:
        aliquota = float(valor)
        if aliquota > 1 and aliquota <= 100:
            aliquota = aliquota / 100
        return aliquota
    except:
        return 0.0

# ============================================
# FUNÇÃO PARA RECALCULAR TODO O CARRINHO
# ============================================
def recalcular_todo_carrinho(uf, cliente_isento, forma_pagamento, dados_st, dados_promo, dados, dados_normal, dados_isento):
    if not st.session_state.carrinho:
        return
    
    icms_uf = determinar_icms_por_uf(uf)
    tabela_desconto = dados_isento if cliente_isento else dados_normal
    
    for item in st.session_state.carrinho:
        referencia = item['referencia']
        produto_dados = dados[dados['Referência'] == referencia]
        
        if produto_dados.empty:
            continue
        
        produto = produto_dados.iloc[0]
        
        is_promo = 'SIM' in str(produto.get('Promo', '')).strip().upper()
        preco_promo = None
        
        if is_promo and not dados_promo.empty:
            preco_promo = buscar_preco_promo(referencia, uf, dados_promo)
        
        if is_promo and preco_promo is not None and preco_promo > 0:
            preco_bruto = preco_promo
            desconto_percentual = 0
            valor_desconto = 0
            preco_com_desconto = preco_bruto
            if cliente_isento:
                preco_com_desconto = preco_com_desconto * 1.10
            preco_final = preco_com_desconto
        else:
            preco_bruto = produto['Preço'] if pd.notna(produto['Preço']) and produto['Preço'] > 0 else 0
            if forma_pagamento != "PREÇO BASE":
                desconto_percentual = buscar_desconto(icms_uf, forma_pagamento, tabela_desconto)
                valor_desconto = preco_bruto * desconto_percentual
                preco_com_desconto = preco_bruto - valor_desconto
            else:
                desconto_percentual = 0
                valor_desconto = 0
                preco_com_desconto = preco_bruto
            if cliente_isento:
                preco_com_desconto = preco_com_desconto * 1.10
            preco_final = preco_com_desconto
        
        ncm_produto = produto.get('NCM', '')
        ipi_percentual = buscar_ipi(ncm_produto, dados_st)
        valor_ipi = preco_final * ipi_percentual
        
        aliquota_st = buscar_aliquota_st(ncm_produto, uf, dados_st)
        if cliente_isento:
            valor_st = 0
        else:
            valor_st = preco_final * aliquota_st
        
        valor_total = preco_final + valor_ipi + valor_st
        
        quantidade = item['quantidade']
        item['preco_bruto'] = preco_bruto
        item['desconto_percentual'] = desconto_percentual
        item['valor_desconto'] = valor_desconto
        item['preco_com_desconto'] = preco_com_desconto
        item['preco_final'] = preco_final
        item['preco_unitario'] = preco_final
        item['preco_total'] = preco_final * quantidade
        item['ipi_percentual'] = ipi_percentual
        item['valor_ipi'] = valor_ipi
        item['ipi_total'] = valor_ipi * quantidade
        item['st_aliquota'] = aliquota_st
        item['valor_st'] = valor_st
        item['st_total'] = valor_st * quantidade
        item['total_geral'] = valor_total * quantidade

# ============================================
# FUNÇÕES DO CARRINHO
# ============================================
def adicionar_ao_carrinho(produto, quantidade, preco_bruto, desconto_percentual, valor_desconto, preco_com_desconto, preco_final, valor_ipi, valor_st, ipi_percentual, aliquota_st, valor_total):
    for item in st.session_state.carrinho:
        if item['referencia'] == produto['Referência']:
            item['quantidade'] += quantidade
            item['preco_total'] += preco_final * quantidade
            item['ipi_total'] += valor_ipi * quantidade
            item['st_total'] += valor_st * quantidade
            item['total_geral'] += valor_total * quantidade
            return
    
    st.session_state.carrinho.append({
        'referencia': produto['Referência'],
        'descricao': produto['Descrição'],
        'grupo': produto['GRUPO'],
        'quantidade': quantidade,
        'preco_bruto': preco_bruto,
        'desconto_percentual': desconto_percentual,
        'valor_desconto': valor_desconto,
        'preco_com_desconto': preco_com_desconto,
        'preco_final': preco_final,
        'preco_unitario': preco_final,
        'preco_total': preco_final * quantidade,
        'ipi_percentual': ipi_percentual,
        'valor_ipi': valor_ipi,
        'ipi_total': valor_ipi * quantidade,
        'st_aliquota': aliquota_st,
        'valor_st': valor_st,
        'st_total': valor_st * quantidade,
        'total_geral': valor_total * quantidade,
        'medidas': produto.get('Medidas', ''),
        'ml': produto.get('ml', ''),
        'imagem_url': produto.get('imagem_url', '')
    })

def remover_do_carrinho(indice):
    if 0 <= indice < len(st.session_state.carrinho):
        st.session_state.carrinho.pop(indice)

def limpar_carrinho():
    st.session_state.carrinho = []

def formatar_mensagem_whatsapp(uf, tipo_cliente, forma_pagamento):
    if not st.session_state.carrinho:
        return "Olá! Gostaria de solicitar um orçamento."
    
    mensagem = "🛍️ *ORÇAMENTO LUVidarte* 🛍️\n\n"
    mensagem += f"📅 Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
    mensagem += f"📍 UF: {uf}\n"
    mensagem += f"👤 Cliente: {tipo_cliente}\n"
    mensagem += f"💳 Pagamento: {forma_pagamento}\n\n"
    mensagem += "─" * 30 + "\n\n"
    
    total_geral = 0
    
    for item in st.session_state.carrinho:
        mensagem += f"📦 *{item['descricao']}*\n"
        mensagem += f"🔖 REF: {item['referencia']}\n"
        mensagem += f"📊 Quantidade: {item['quantidade']}\n"
        if item.get('medidas'):
            mensagem += f"📐 Medidas: {item['medidas']}\n"
        mensagem += f"💰 Valor unitário: R$ {item['preco_unitario']:.2f}\n"
        if item.get('ipi_percentual', 0) > 0:
            mensagem += f"🔷 IPI: {item['ipi_percentual']*100:.2f}%\n"
        mensagem += f"✅ Subtotal: R$ {item['preco_total']:.2f}\n"
        if item.get('ipi_total', 0) > 0:
            mensagem += f"   + IPI: R$ {item['ipi_total']:.2f}\n"
        if item.get('st_total', 0) > 0:
            mensagem += f"   + ST: R$ {item['st_total']:.2f}\n"
        mensagem += f"━━━━━━━━━━━━━━━━━━━━━━\n"
        mensagem += f"💎 Total item: R$ {item['total_geral']:.2f}\n\n"
        total_geral += item['total_geral']
    
    mensagem += "─" * 30 + "\n\n"
    mensagem += f"💰 *TOTAL DO ORÇAMENTO: R$ {total_geral:.2f}*\n\n"
    mensagem += "─" * 30 + "\n\n"
    mensagem += "📋 *OBSERVAÇÕES IMPORTANTES:*\n"
    mensagem += "• Este é um ORÇAMENTO VIRTUAL, não uma compra finalizada\n"
    mensagem += "• Valores sujeitos à confirmação de estoque\n"
    mensagem += "• Prazos e condições serão informados por nossa equipe\n"
    mensagem += "• Descontos especiais podem ser aplicados mediante negociação\n\n"
    mensagem += "✨ Aguardo confirmação da equipe Luvidarte! ✨"
    
    return mensagem

def calcular_resumo_carrinho():
    if not st.session_state.carrinho:
        return {'total_itens': 0, 'total_geral': 0.0, 'total_ipi': 0.0, 'total_st': 0.0, 'total_desconto': 0.0, 'total_bruto': 0.0}
    
    total_itens = sum(item['quantidade'] for item in st.session_state.carrinho)
    total_geral = sum(item['total_geral'] for item in st.session_state.carrinho)
    total_ipi = sum(item['ipi_total'] for item in st.session_state.carrinho)
    total_st = sum(item['st_total'] for item in st.session_state.carrinho)
    total_desconto = sum(item['valor_desconto'] * item['quantidade'] for item in st.session_state.carrinho)
    total_bruto = sum(item['preco_bruto'] * item['quantidade'] for item in st.session_state.carrinho)
    
    return {
        'total_itens': total_itens,
        'total_geral': total_geral,
        'total_ipi': total_ipi,
        'total_st': total_st,
        'total_desconto': total_desconto,
        'total_bruto': total_bruto
    }

# ============================================
# ESTILO PERSONALIZADO
# ============================================
st.markdown("""
<style>
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

.stDecoration { display: none; }
.stAppDeployButton { display: none !important; }

.main > div {
    padding-top: 0.5rem;
}

.stApp {
    background-color: #F7F7F7;
}

.main-banner {
    background-color: #FFFFFF;
    border-radius: 16px;
    padding: 15px 20px;
    margin-bottom: 20px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 15px;
    min-height: 90px;
    border: 1px solid #E0E0E0;
    flex-wrap: wrap;
}

.logo-container {
    flex-shrink: 0;
}

.logo-img {
    max-height: 60px;
    width: auto;
    object-fit: contain;
}

.banner-text {
    flex-grow: 1;
    text-align: center;
}

.banner-text h1 {
    font-size: clamp(20px, 5vw, 38px);
    margin: 0;
    font-weight: bold;
    color: #000000;
}

.banner-text p {
    font-size: clamp(11px, 3vw, 15px);
    margin: 5px 0 0 0;
    color: #333333;
}

.legal-banner {
    background-color: #FFF9E6;
    border-left: 4px solid #C9A03D;
    border-radius: 8px;
    padding: 10px 15px;
    margin: 10px 0;
    font-size: 12px;
    color: #666;
}

.contato-central {
    text-align: center;
    margin: 10px 0 20px 0;
    padding: 10px;
    font-size: clamp(11px, 3vw, 13px);
    color: #666666;
    background-color: #FFFFFF;
    border-radius: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    border: 1px solid #E8E8E8;
    word-wrap: break-word;
}

/* HEADER COM TÍTULO E BOTÃO */
.header-container {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
    flex-wrap: wrap;
    gap: 15px;
}

.header-title {
    font-size: 24px;
    font-weight: bold;
    color: #333;
}

/* WHATSAPP FLUTUANTE */
.whatsapp-float-fixed {
    position: fixed;
    bottom: 60px;
    right: 20px;
    z-index: 99997;
}

.whatsapp-float {
    background-color: #25D366;
    color: white;
    border-radius: 50px;
    padding: 10px 18px;
    font-size: 13px;
    font-weight: bold;
    box-shadow: 0 4px 12px rgba(0,0,0,0.25);
    transition: all 0.3s ease;
    display: flex;
    align-items: center;
    gap: 8px;
    text-decoration: none;
}

.whatsapp-float:hover {
    transform: scale(1.05);
    background-color: #075E54;
}

.whatsapp-float a {
    color: white;
    text-decoration: none;
    display: flex;
    align-items: center;
    gap: 8px;
}

/* Botão do carrinho */
.cart-button {
    background: linear-gradient(135deg, #2E7D32 0%, #1B5E20 100%);
    color: white;
    border: none;
    border-radius: 40px;
    padding: 10px 20px;
    font-weight: bold;
    font-size: 13px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.2);
    transition: all 0.3s ease;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 8px;
}

.cart-button:hover {
    transform: scale(1.02);
    background: linear-gradient(135deg, #1B5E20 0%, #0D3B0F 100%);
}

.cart-button-empty {
    background: linear-gradient(135deg, #999999 0%, #666666 100%);
    cursor: not-allowed;
    opacity: 0.7;
}

/* CARDS DE PRODUTO */
.product-card {
    background-color: #FFFFFF;
    border-radius: 12px;
    padding: 16px;
    margin: 10px 0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    transition: all 0.2s ease;
    position: relative;
    height: 100%;
    display: flex;
    flex-direction: column;
}

.product-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}

.product-card.promo-card {
    border: 1.5px solid #D32F2F;
    box-shadow: 0 2px 8px rgba(211, 47, 47, 0.15);
}

.product-card.normal-card {
    border: 1px solid #E0E0E0;
}

.promo-badge {
    position: absolute;
    top: -8px;
    right: -8px;
    background: linear-gradient(135deg, #D32F2F 0%, #B71C1C 100%);
    color: white;
    font-size: 10px;
    font-weight: bold;
    padding: 4px 10px;
    border-radius: 20px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.2);
    z-index: 10;
    letter-spacing: 0.5px;
}

.tabela-badge {
    position: absolute;
    top: -8px;
    right: -8px;
    background: linear-gradient(135deg, #666666 0%, #444444 100%);
    color: white;
    font-size: 10px;
    font-weight: bold;
    padding: 4px 10px;
    border-radius: 20px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.2);
    z-index: 10;
    letter-spacing: 0.5px;
}

.ref {
    color: #666666;
    font-size: 11px;
    font-weight: 500;
    text-transform: uppercase;
    display: block;
}

.product-name {
    color: #000000;
    font-size: 17px;
    font-weight: 600;
    margin: 8px 0 4px 0;
}

.product-category {
    color: #666666;
    font-size: 12px;
    margin-bottom: 12px;
}

.product-detail {
    font-size: 13px;
    margin: 5px 0;
    min-height: 24px;
}

.resumo-card {
    background-color: #FFFFFF;
    border-radius: 12px;
    padding: 16px;
    margin: 10px 0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    border: 1px solid #E0E0E0;
}

.resumo-title {
    font-size: 16px;
    font-weight: bold;
    color: #2E7D32;
    margin-bottom: 10px;
    border-bottom: 2px solid #C9A03D;
    display: inline-block;
    padding-bottom: 5px;
}

.resumo-line {
    display: flex;
    justify-content: space-between;
    padding: 5px 0;
    font-size: 13px;
}

.resumo-line.total {
    font-weight: bold;
    font-size: 16px;
    border-top: 1px solid #E0E0E0;
    margin-top: 8px;
    padding-top: 8px;
    color: #D32F2F;
}

.social-links-container {
    text-align: center;
    margin: 15px 0;
}

.social-title {
    color: #C9A03D;
    font-weight: bold;
    font-size: 14px;
}

.social-links {
    display: flex;
    justify-content: center;
    gap: 25px;
    margin: 10px 0;
    flex-wrap: wrap;
}

.social-link {
    text-decoration: none;
    font-size: 14px;
    font-weight: 500;
    padding: 5px 0;
}

.contact-footer {
    text-align: center;
    font-size: 13px;
    color: #555555;
}

.footer-bottom {
    text-align: center;
    font-size: 12px;
    color: #666666;
    padding: 15px 0;
    border-top: 1px solid #E0E0E0;
    margin-top: 20px;
}

.horario-atendimento {
    text-align: center;
    margin: 10px 0;
    font-size: 13px;
}

.horario-label {
    color: #C9A03D;
    font-weight: bold;
}

.horario-text {
    color: #555555;
}

@media (max-width: 768px) {
    .stColumn {
        padding: 0 5px !important;
    }
    .whatsapp-float-fixed {
        bottom: 50px;
        right: 15px;
    }
    .whatsapp-float {
        padding: 8px 14px;
        font-size: 12px;
    }
    .header-title {
        font-size: 18px;
    }
    .cart-button {
        padding: 6px 12px;
        font-size: 11px;
    }
}
</style>
""", unsafe_allow_html=True)

# ============================================
# FUNÇÕES AUXILIARES
# ============================================
def converter_moeda_para_numero(valor):
    if pd.isna(valor) or valor == '' or valor is None:
        return np.nan
    valor_str = str(valor)
    valor_str = valor_str.replace('R$', '').replace(' ', '')
    valor_str = valor_str.replace('.', '')
    valor_str = valor_str.replace(',', '.')
    valor_str = re.sub(r'[^0-9.]', '', valor_str)
    try:
        return float(valor_str)
    except:
        return np.nan

def converter_percentual_para_numero(valor):
    if pd.isna(valor) or valor == '' or valor is None:
        return 0.0
    valor_str = str(valor).strip()
    valor_str = valor_str.replace('%', '')
    valor_str = valor_str.replace(',', '.')
    try:
        percentual = float(valor_str)
        if percentual > 1 and percentual <= 100:
            percentual = percentual / 100
        return percentual
    except:
        return 0.0

def formatar_ml(valor):
    if pd.isna(valor) or valor == 0 or valor is None or valor == '':
        return None
    try:
        ml_valor = float(valor)
        if ml_valor >= 1000:
            litros = ml_valor / 1000
            return f"{litros:.3f}".replace(',', '.') + " L"
        else:
            if ml_valor == int(ml_valor):
                return f"{int(ml_valor)} ml"
            else:
                return f"{ml_valor:.3f}".rstrip('0').rstrip('.') + " ml"
    except:
        return None

# ============================================
# FUNÇÕES DE CARREGAMENTO DE DADOS
# ============================================
@st.cache_data(ttl=600)
def carregar_planilha(id_planilha, nome_aba="base"):
    try:
        url = f"https://docs.google.com/spreadsheets/d/{id_planilha}/gviz/tq?tqx=out:csv&sheet={nome_aba}"
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()
        
        if 'Codigo SISTEMA' in df.columns:
            df = df.rename(columns={'Codigo SISTEMA': 'Promo'})
        
        if 'Preço Bruto' in df.columns:
            df['Preço'] = df['Preço Bruto'].apply(converter_moeda_para_numero)
        
        df['GRUPO'] = df['GRUPO'].fillna('Outros')
        df['Descrição'] = df['Descrição'].fillna('Produto sem descrição')
        df['Referência'] = df['Referência'].fillna('').astype(str)
        
        if 'Promo' not in df.columns:
            df['Promo'] = ''
        
        if 'ml' in df.columns:
            df['ml'] = pd.to_numeric(df['ml'], errors='coerce')
        
        return df
    except Exception as erro:
        st.error(f"❌ Erro ao carregar a planilha: {erro}")
        return pd.DataFrame()

@st.cache_data(ttl=600)
def carregar_planilha_promo(id_planilha, nome_aba="PROMO"):
    try:
        url = f"https://docs.google.com/spreadsheets/d/{id_planilha}/gviz/tq?tqx=out:csv&sheet={nome_aba}"
        df_promo = pd.read_csv(url)
        df_promo.columns = df_promo.columns.str.strip()
        return df_promo
    except:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def carregar_base_st(id_planilha_st, nome_aba_st="BASE_ST"):
    try:
        url = f"https://docs.google.com/spreadsheets/d/{id_planilha_st}/gviz/tq?tqx=out:csv&sheet={nome_aba_st}"
        df_st = pd.read_csv(url)
        df_st.columns = df_st.columns.str.strip()
        return df_st
    except:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def carregar_descontos_normal(id_planilha, nome_aba="NORMAL"):
    try:
        url = f"https://docs.google.com/spreadsheets/d/{id_planilha}/gviz/tq?tqx=out:csv&sheet={nome_aba}"
        df_normal = pd.read_csv(url)
        df_normal.columns = df_normal.columns.str.strip()
        return df_normal
    except:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def carregar_descontos_isento(id_planilha, nome_aba="ISENTO"):
    try:
        url = f"https://docs.google.com/spreadsheets/d/{id_planilha}/gviz/tq?tqx=out:csv&sheet={nome_aba}"
        df_isento = pd.read_csv(url)
        df_isento.columns = df_isento.columns.str.strip()
        return df_isento
    except:
        return pd.DataFrame()

# ============================================
# FUNÇÕES DE CÁLCULO
# ============================================
def buscar_preco_promo(referencia: str, uf: str, df_promo: pd.DataFrame) -> float:
    if df_promo.empty or not referencia:
        return None
    
    ref_limpa = str(referencia).strip()
    coluna_ref = df_promo.columns[0]
    
    df_promo[coluna_ref] = df_promo[coluna_ref].astype(str).str.strip()
    linha_produto = df_promo[df_promo[coluna_ref] == ref_limpa]
    
    if linha_produto.empty:
        linha_produto = df_promo[df_promo[coluna_ref].str.contains(ref_limpa, case=False, na=False)]
        if linha_produto.empty:
            return None
    
    uf_upper = uf.upper()
    if uf_upper == "SP":
        coluna_icms = "18%"
    elif uf_upper in ["MG", "RS", "SE", "PR", "RJ", "SC"]:
        coluna_icms = "12%"
    else:
        coluna_icms = "7%"
    
    coluna_preco = None
    for col in df_promo.columns:
        if str(col).strip() == coluna_icms:
            coluna_preco = col
            break
    
    if coluna_preco is None:
        return None
    
    valor = linha_produto.iloc[0][coluna_preco]
    
    if pd.isna(valor):
        return None
    
    if isinstance(valor, str):
        valor = valor.strip().replace('.', '').replace(',', '.')
        try:
            valor = float(valor)
        except:
            return None
    
    return float(valor) if not pd.isna(valor) else None

def buscar_ipi(ncm: str, df_st: pd.DataFrame) -> float:
    if df_st.empty or not ncm:
        return 0.0
    
    ncm_limpo = str(ncm).replace(".", "").strip()
    df_st['NCM_LIMPO'] = df_st.iloc[:, 1].astype(str).str.replace(".", "").str.strip()
    
    linha_ncm = df_st[df_st['NCM_LIMPO'] == ncm_limpo]
    if linha_ncm.empty:
        return 0.0
    
    valor_ipi = linha_ncm.iloc[0, 0]
    if pd.isna(valor_ipi):
        return 0.0
    
    if isinstance(valor_ipi, str):
        valor_ipi = valor_ipi.replace("%", "").replace(",", ".").strip()
    
    try:
        ipi = float(valor_ipi)
        if ipi > 1 and ipi <= 100:
            ipi = ipi / 100
        return ipi
    except:
        return 0.0

def determinar_icms_por_uf(uf: str) -> float:
    uf_upper = uf.upper()
    if uf_upper == "SP":
        return 18.0
    elif uf_upper in ["MG", "RS", "SE", "PR", "RJ", "SC"]:
        return 12.0
    else:
        return 7.0

def buscar_desconto(icms: float, forma_pagamento: str, df_desconto: pd.DataFrame) -> float:
    if df_desconto.empty or forma_pagamento == "PREÇO BASE":
        return 0.0
    
    df_temp = df_desconto.copy()
    df_temp['ICMS_LIMPO'] = df_temp['ICMS'].astype(str).str.replace('%', '').str.replace(',', '.').str.strip()
    df_temp['ICMS_LIMPO'] = pd.to_numeric(df_temp['ICMS_LIMPO'], errors='coerce')
    df_temp['FORMA_LIMPO'] = df_temp['FORMA'].apply(lambda x: str(x).strip() if pd.notna(x) else "")
    
    if forma_pagamento == "VISTA":
        forma_para_buscar = ""
    else:
        try:
            forma_numero = float(forma_pagamento)
            forma_para_buscar = f"{forma_numero:.1f}"
        except:
            forma_para_buscar = forma_pagamento
    
    df_filtrado = df_temp[
        (df_temp['ICMS_LIMPO'] == float(icms)) & 
        (df_temp['FORMA_LIMPO'] == forma_para_buscar)
    ]
    
    if not df_filtrado.empty:
        return converter_percentual_para_numero(df_filtrado.iloc[0]['DESCONTO'])
    return 0.0

def carregar_logo():
    url_drive = "https://drive.google.com/uc?export=download&id=1wiwp3txOXGsEMRrUgzdLFlxQL2188uTw"
    try:
        response = requests.get(url_drive, timeout=15)
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            if 'image' in content_type:
                return Image.open(BytesIO(response.content))
    except:
        pass
    return None

# ============================================
# BANNER PRINCIPAL
# ============================================
logo_img = carregar_logo()
if logo_img:
    buffered = BytesIO()
    logo_img.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode()
    st.markdown(f"""
    <div class='main-banner'>
        <div class='logo-container'>
            <img src='data:image/png;base64,{img_base64}' class='logo-img'>
        </div>
        <div class='banner-text'>
            <h1>Catálogo Virtual</h1>
            <p>Peças exclusivas em vidro e decoração</p>
        </div>
        <div style='width: 80px;'></div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown(f"""
    <div class='main-banner'>
        <div class='banner-text' style='width: 100%;'>
            <h1>Catálogo Virtual</h1>
            <p>Peças exclusivas em vidro e decoração</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("""
<div class='legal-banner'>
    ⚠️ <strong>AVISO LEGAL:</strong> Este é um ORÇAMENTO VIRTUAL, não uma compra finalizada. 
    Os valores são estimativas e sujeitos à confirmação de estoque e disponibilidade. 
    A venda será formalizada APENAS após contato e confirmação da nossa equipe via WhatsApp.
</div>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class='contato-central'>
    📍 Rua Caetano Rubio, 213 - Ferraz de Vasconcelos - SP &nbsp;|&nbsp;
    📞 (11) 4676-9000 &nbsp;|&nbsp;
    💬 (11) 93011-9335 &nbsp;|&nbsp;
    ✉️ sac@luvidarte.com.br
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# ============================================
# CONFIGURAÇÕES
# ============================================
ID_PLANILHA = "1DCmwFzQvbQYDBsQft17VO9szjixgq1Bp09dYTfu142w"
NOME_ABA = "base"
NOME_ABA_PROMO = "PROMO"
NOME_ABA_ST = "BASE_ST"
NOME_ABA_NORMAL = "NORMAL"
NOME_ABA_ISENTO = "ISENTO"

with st.spinner("🔄 Carregando produtos..."):
    dados = carregar_planilha(ID_PLANILHA, NOME_ABA)
    dados_promo = carregar_planilha_promo(ID_PLANILHA, NOME_ABA_PROMO)
    dados_st = carregar_base_st(ID_PLANILHA, NOME_ABA_ST)
    dados_normal = carregar_descontos_normal(ID_PLANILHA, NOME_ABA_NORMAL)
    dados_isento = carregar_descontos_isento(ID_PLANILHA, NOME_ABA_ISENTO)

if dados.empty:
    st.stop()

# ============================================
# SIDEBAR - FILTROS
# ============================================
st.sidebar.header("🔍 FILTRAR PRODUTOS")
st.sidebar.markdown(f"📊 **Total:** {len(dados)} produtos")

uf_selecionada = st.sidebar.selectbox(
    "📍 UF (ICMS)",
    options=["SP", "MG", "RS", "SE", "PR", "RJ", "SC", "MT", "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MS", "PA", "PB", "PE", "PI", "RN", "RO", "RR", "TO"],
    index=0
)

grupos = ["Todos"] + sorted(dados['GRUPO'].unique())
if "Promoção" not in grupos:
    grupos.insert(1, "Promoção")
grupo_escolhido = st.sidebar.selectbox("📦 Grupo", grupos)

busca_referencia = st.sidebar.text_input("🔎 Buscar Referência", placeholder="Ex: 510 P TR")

precos_validos = dados['Preço'].dropna()
if len(precos_validos) > 0:
    faixa_preco = st.sidebar.slider(
        "💰 Faixa de Preço",
        min_value=float(precos_validos.min()),
        max_value=float(precos_validos.max()),
        value=(float(precos_validos.min()), float(precos_validos.max()))
    )
else:
    faixa_preco = (0, 1000)

cliente_isento = st.sidebar.checkbox("🏷️ Cliente Isento", value=False)

forma_pagamento = st.sidebar.radio(
    "💳 Pagamento",
    options=["PREÇO BASE", "VISTA", "30", "45", "60"],
    index=0
)

# MONITORAR MUDANÇAS NOS FILTROS E RECALCULAR CARRINHO
filtros_atual = (uf_selecionada, cliente_isento, forma_pagamento)
if st.session_state.filtros_anteriores != filtros_atual:
    st.session_state.filtros_anteriores = filtros_atual
    if st.session_state.carrinho:
        recalcular_todo_carrinho(uf_selecionada, cliente_isento, forma_pagamento, dados_st, dados_promo, dados, dados_normal, dados_isento)
        st.rerun()

# ============================================
# HEADER COM TÍTULO E BOTÃO DO CARRINHO
# ============================================
resumo = calcular_resumo_carrinho()

col_header1, col_header2 = st.columns([3, 1])
with col_header1:
    st.markdown(f"## ✨ Produtos Encontrados: {total_encontrados if 'total_encontrados' in dir() else 0}")
with col_header2:
    if resumo['total_itens'] > 0:
        if st.button(f"🛒 Meu Carrinho  {resumo['total_itens']}  R$ {resumo['total_geral']:.2f}", key="cart_top_btn", use_container_width=True):
            st.session_state.carrinho_aberto = True
            st.rerun()
    else:
        st.button(f"🛒 Meu Carrinho (vazio)", key="cart_top_btn_empty", disabled=True, use_container_width=True)

st.markdown("---")

# ============================================
# TELA DO CARRINHO
# ============================================
if st.session_state.get('carrinho_aberto', False):
    st.markdown("# 🛒 Meu Orçamento Virtual")
    st.markdown("Revise os itens do seu orçamento antes de enviar.")
    
    if not st.session_state.carrinho:
        st.info("Seu orçamento está vazio. Adicione produtos para continuar.")
        if st.button("← Voltar aos produtos"):
            st.session_state.carrinho_aberto = False
            st.rerun()
        st.stop()
    
    total_geral = 0
    total_ipi_geral = 0
    total_st_geral = 0
    total_desconto_geral = 0
    total_bruto_geral = 0
    
    for idx, item in enumerate(st.session_state.carrinho):
        col1, col2, col3, col4 = st.columns([1, 3, 2, 1])
        
        with col1:
            imagem_url = item.get('imagem_url', '')
            if imagem_url and pd.notna(imagem_url) and str(imagem_url).strip():
                try:
                    st.image(imagem_url, width=80)
                except:
                    st.image("https://via.placeholder.com/80x80?text=Luvidarte", width=80)
            else:
                st.image("https://via.placeholder.com/80x80?text=Luvidarte", width=80)
        
        with col2:
            st.markdown(f"**{item['descricao']}**")
            st.markdown(f"🔖 REF: {item['referencia']}")
            st.markdown(f"📦 Grupo: {item['grupo']}")
            if item.get('medidas'):
                st.markdown(f"📐 {item['medidas']}")
        
        with col3:
            st.markdown(f"💰 **Preço Bruto:** R$ {item['preco_bruto']:.2f}")
            if item['desconto_percentual'] > 0:
                st.markdown(f"🎯 **Desconto:** {item['desconto_percentual']*100:.2f}% (R$ {item['valor_desconto']:.2f})")
                st.markdown(f"📉 **Valor com Desconto:** R$ {item['preco_com_desconto']:.2f}")
            st.markdown(f"💰 **Valor unitário:** R$ {item['preco_unitario']:.2f}")
            st.markdown(f"📊 **Quantidade:** {item['quantidade']}")
            st.markdown(f"💎 **Subtotal:** R$ {item['preco_total']:.2f}")
            if item.get('ipi_percentual', 0) > 0:
                st.markdown(f"🔷 IPI: {item['ipi_percentual']*100:.2f}% = R$ {item['ipi_total']:.2f}")
            if item.get('st_total', 0) > 0:
                st.markdown(f"🟣 ST: R$ {item['st_total']:.2f}")
        
        with col4:
            st.markdown(f"**Total Item**")
            st.markdown(f"### R$ {item['total_geral']:.2f}")
            if st.button(f"🗑️ Remover", key=f"remove_{idx}"):
                remover_do_carrinho(idx)
                st.rerun()
        
        st.markdown("---")
        total_geral += item['total_geral']
        total_ipi_geral += item['ipi_total']
        total_st_geral += item['st_total']
        total_desconto_geral += item['valor_desconto'] * item['quantidade']
        total_bruto_geral += item['preco_bruto'] * item['quantidade']
    
    # RESUMO DETALHADO DO ORÇAMENTO
    st.markdown("## 📋 Resumo do Orçamento")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"""
        <div class='resumo-card'>
            <div class='resumo-title'>📊 Resumo de Valores</div>
            <div class='resumo-line'>
                <span>💰 Valor Bruto Total:</span>
                <span><strong>R$ {total_bruto_geral:.2f}</strong></span>
            </div>
            <div class='resumo-line'>
                <span>🎯 Desconto Total:</span>
                <span><strong style="color: #D32F2F;">- R$ {total_desconto_geral:.2f}</strong></span>
            </div>
            <div class='resumo-line'>
                <span>📉 Valor com Desconto:</span>
                <span><strong>R$ {total_bruto_geral - total_desconto_geral:.2f}</strong></span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class='resumo-card'>
            <div class='resumo-title'>🏷️ Tributos</div>
            <div class='resumo-line'>
                <span>🔷 IPI Total:</span>
                <span><strong>R$ {total_ipi_geral:.2f}</strong></span>
            </div>
            <div class='resumo-line'>
                <span>🟣 ST Total:</span>
                <span><strong>R$ {total_st_geral:.2f}</strong></span>
            </div>
            <div class='resumo-line total'>
                <span>✅ TOTAL DO ORÇAMENTO:</span>
                <span><strong style="color: #D32F2F;">R$ {total_geral:.2f}</strong></span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # Botões de ação
    st.markdown("---")
    col_btn1, col_btn2, col_btn3 = st.columns(3)
    
    with col_btn1:
        if st.button("← Continuar comprando", use_container_width=True):
            st.session_state.carrinho_aberto = False
            st.rerun()
    
    with col_btn2:
        if st.button("🗑️ Limpar Carrinho", use_container_width=True):
            limpar_carrinho()
            st.rerun()
    
    with col_btn3:
        mensagem = formatar_mensagem_whatsapp(uf_selecionada, "ISENTO" if cliente_isento else "NORMAL", forma_pagamento)
        mensagem_codificada = urllib.parse.quote(mensagem)
        link_whatsapp = f"https://wa.me/5511930119335?text={mensagem_codificada}"
        st.markdown(f'<a href="{link_whatsapp}" target="_blank"><button style="width: 100%; background-color: #25D366; color: white; border: none; border-radius: 8px; padding: 10px; font-weight: bold; cursor: pointer;">📱 Enviar Orçamento via WhatsApp</button></a>', unsafe_allow_html=True)
    
    st.stop()

# ============================================
# APLICAR FILTROS PARA EXIBIÇÃO
# ============================================
icms_uf = determinar_icms_por_uf(uf_selecionada)
tabela_desconto = dados_isento if cliente_isento else dados_normal
tipo_cliente = "ISENTO" if cliente_isento else "NORMAL"

dados_filtrados = dados.copy()

if grupo_escolhido == "Promoção":
    dados_filtrados = dados_filtrados[dados_filtrados['Promo'].astype(str).str.upper().str.contains('SIM', na=False)]
elif grupo_escolhido != "Todos":
    dados_filtrados = dados_filtrados[dados_filtrados['GRUPO'] == grupo_escolhido]

if len(precos_validos) > 0:
    dados_filtrados = dados_filtrados[
        (dados_filtrados['Preço'].isna()) | 
        ((dados_filtrados['Preço'] >= faixa_preco[0]) & (dados_filtrados['Preço'] <= faixa_preco[1]))
    ]

if busca_referencia:
    dados_filtrados = dados_filtrados[dados_filtrados['Referência'].str.contains(busca_referencia, case=False, na=False)]

total_encontrados = len(dados_filtrados)

# ============================================
# PAGINAÇÃO
# ============================================
ITENS_POR_PAGINA = 9
total_paginas = max(1, (total_encontrados + ITENS_POR_PAGINA - 1) // ITENS_POR_PAGINA)

if st.session_state.pagina_atual > total_paginas:
    st.session_state.pagina_atual = total_paginas

indice_inicio = (st.session_state.pagina_atual - 1) * ITENS_POR_PAGINA
indice_fim = min(indice_inicio + ITENS_POR_PAGINA, total_encontrados)
dados_pagina = dados_filtrados.iloc[indice_inicio:indice_fim]

# ============================================
# EXIBIR PRODUTOS
# ============================================
col_info1, col_info2, col_info3, col_info4 = st.columns(4)
with col_info1:
    st.info(f"🏢 **UF:** {uf_selecionada} (ICMS {icms_uf}%)")
with col_info2:
    st.info(f"📋 **Cliente:** {tipo_cliente}")
with col_info3:
    if forma_pagamento == "PREÇO BASE":
        st.warning(f"💰 **Condição:** {forma_pagamento}")
    else:
        st.success(f"💰 **Condição:** {forma_pagamento} dias")
with col_info4:
    if grupo_escolhido == "Promoção":
        st.success(f"🏷️ **Grupo:** {grupo_escolhido} - Ofertas!")
    else:
        st.info(f"📦 **Grupo:** {grupo_escolhido}")

st.markdown("---")

if dados_filtrados.empty:
    st.warning("😕 Nenhum produto encontrado.")
else:
    colunas = st.columns(3)
    
    for posicao, (indice, produto) in enumerate(dados_pagina.iterrows()):
        is_promo = 'SIM' in str(produto.get('Promo', '')).strip().upper()
        preco_promo = None
        
        if is_promo and not dados_promo.empty:
            preco_promo = buscar_preco_promo(produto['Referência'], uf_selecionada, dados_promo)
        
        # CÁLCULO CORRETO
        if is_promo and preco_promo is not None and preco_promo > 0:
            preco_bruto = preco_promo
            desconto_percentual = 0
            valor_desconto = 0
            preco_com_desconto = preco_bruto
            if cliente_isento:
                preco_com_desconto = preco_com_desconto * 1.10
            preco_final = preco_com_desconto
        else:
            preco_bruto = produto['Preço'] if pd.notna(produto['Preço']) and produto['Preço'] > 0 else 0
            if forma_pagamento != "PREÇO BASE":
                desconto_percentual = buscar_desconto(icms_uf, forma_pagamento, tabela_desconto)
                valor_desconto = preco_bruto * desconto_percentual
                preco_com_desconto = preco_bruto - valor_desconto
            else:
                desconto_percentual = 0
                valor_desconto = 0
                preco_com_desconto = preco_bruto
            if cliente_isento:
                preco_com_desconto = preco_com_desconto * 1.10
            preco_final = preco_com_desconto
        
        ncm_produto = produto.get('NCM', '')
        ipi_percentual = buscar_ipi(ncm_produto, dados_st)
        valor_ipi = preco_final * ipi_percentual
        
        aliquota_st = buscar_aliquota_st(ncm_produto, uf_selecionada, dados_st)
        if cliente_isento:
            valor_st = 0
        else:
            valor_st = preco_final * aliquota_st
        
        valor_total = preco_final + valor_ipi + valor_st
        
        produto_carrinho = {
            'Referência': produto['Referência'],
            'Descrição': produto['Descrição'],
            'GRUPO': produto['GRUPO'],
            'Medidas': produto.get('Medidas', ''),
            'ml': produto.get('ml', ''),
            'imagem_url': produto.get('imagem_url', '')
        }
        
        with colunas[posicao % 3]:
            card_class = "product-card promo-card" if is_promo else "product-card normal-card"
            
            st.markdown(f"""
            <div class='{card_class}'>
                <span class='ref'>🔖 REF: {produto['Referência']}</span>
                <div class='product-name'>{produto['Descrição']}</div>
                <div class='product-category'>{produto['GRUPO']}</div>
            """, unsafe_allow_html=True)
            
            if is_promo:
                st.markdown(f"<div class='promo-badge'>🔥 PROMOÇÃO</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='tabela-badge'>📋 TABELA</div>", unsafe_allow_html=True)
            
            st.markdown("</div>", unsafe_allow_html=True)
            
            # Imagem
            if pd.notna(produto.get('imagem_url')) and produto.get('imagem_url'):
                try:
                    st.image(produto['imagem_url'], use_container_width=True)
                except:
                    st.image("https://via.placeholder.com/300x200?text=Sem+Imagem", use_container_width=True)
            else:
                st.image("https://via.placeholder.com/300x200?text=Sem+Imagem", use_container_width=True)
            
            # ML
            if 'ml' in produto:
                ml_formatado = formatar_ml(produto.get('ml'))
                if ml_formatado:
                    st.markdown(f'<div class="product-detail">📏 <strong>{ml_formatado}</strong></div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="product-detail">📏 <strong>--</strong></div>', unsafe_allow_html=True)
            
            # Medidas
            if pd.notna(produto.get('Medidas')) and str(produto['Medidas']).strip():
                st.markdown(f'<div class="product-detail">📐 {produto["Medidas"]}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="product-detail">📐 <strong>--</strong></div>', unsafe_allow_html=True)
            
            # DETALHAMENTO COMPLETO DOS PREÇOS
            st.markdown(f"💰 **Preço Bruto:** R$ {preco_bruto:.2f}")
            
            if desconto_percentual > 0:
                st.markdown(f"🎯 **Desconto:** {desconto_percentual*100:.2f}% (R$ {valor_desconto:.2f})")
                st.markdown(f"📉 **Valor com Desconto:** R$ {preco_com_desconto:.2f}")
            
            if cliente_isento and desconto_percentual > 0:
                st.markdown(f"✨ **+10% Cliente Isento:** R$ {preco_com_desconto:.2f} → R$ {preco_final:.2f}")
            elif cliente_isento:
                st.markdown(f"✨ **+10% Cliente Isento:** R$ {preco_bruto:.2f} → R$ {preco_final:.2f}")
            
            if ipi_percentual > 0:
                st.markdown(f"🔷 **IPI:** {ipi_percentual*100:.2f}% = R$ {valor_ipi:.2f}")
            else:
                st.markdown(f"🔷 **IPI:** Não aplicável")
            
            if cliente_isento:
                st.markdown(f"🟣 **ST ({uf_selecionada}):** Cliente Isento - ST não aplicada")
                st.markdown(f"✅ **TOTAL COM IPI:** R$ {preco_final + valor_ipi:.2f}")
            elif aliquota_st > 0:
                st.markdown(f"🟣 **Alíq. ST ({uf_selecionada}):** {aliquota_st*100:.2f}%")
                st.markdown(f"📊 **Valor ST:** R$ {valor_st:.2f}")
                st.markdown(f"✅ **TOTAL COM IPI + ST:** R$ {valor_total:.2f}")
            else:
                st.markdown(f"🟣 **ST ({uf_selecionada}):** Não aplicável")
                st.markdown(f"✅ **TOTAL COM IPI:** R$ {preco_final + valor_ipi:.2f}")
            
            st.markdown("---")
            
            # Seletor de quantidade
            qtd_key = f"qtd_{indice}"
            if qtd_key not in st.session_state:
                st.session_state[qtd_key] = 1
            
            col_menos, col_valor, col_mais, col_add = st.columns([1, 1, 1, 2])
            
            with col_menos:
                if st.button("−", key=f"menos_{indice}", help="Diminuir quantidade"):
                    if st.session_state[qtd_key] > 1:
                        st.session_state[qtd_key] -= 1
                        st.rerun()
            
            with col_valor:
                st.markdown(f'<div style="text-align: center; font-size: 18px; font-weight: bold; padding-top: 5px;">{st.session_state[qtd_key]}</div>', unsafe_allow_html=True)
            
            with col_mais:
                if st.button("+", key=f"mais_{indice}", help="Aumentar quantidade"):
                    if st.session_state[qtd_key] < 999:
                        st.session_state[qtd_key] += 1
                        st.rerun()
            
            with col_add:
                quantidade = st.session_state[qtd_key]
                if st.button(f"🛒 Adicionar", key=f"add_{indice}", use_container_width=True):
                    adicionar_ao_carrinho(produto_carrinho, quantidade, preco_bruto, desconto_percentual, valor_desconto, preco_com_desconto, preco_final, valor_ipi, valor_st, ipi_percentual, aliquota_st, valor_total)
                    st.success(f"✅ Produto adicionado ao orçamento!", icon="✅")
                    time.sleep(0.5)
                    st.rerun()
            
            st.markdown("---")
    
    # Paginação
    if total_paginas > 1:
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown('<div style="text-align: center; padding: 20px; background: #fafafa; border-radius: 12px;">', unsafe_allow_html=True)
            
            pagina_selecionada = st.selectbox(
                "📄 Página",
                options=list(range(1, total_paginas + 1)),
                index=st.session_state.pagina_atual - 1,
                key="pagina_select"
            )
            
            if pagina_selecionada != st.session_state.pagina_atual:
                st.session_state.pagina_atual = pagina_selecionada
                st.rerun()
            
            st.markdown(f'<div style="text-align: center; font-size: 12px;">Mostrando {indice_inicio + 1} - {min(indice_fim, total_encontrados)} de {total_encontrados}</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
        
        st.progress(st.session_state.pagina_atual / total_paginas, text=f"Página {st.session_state.pagina_atual} de {total_paginas}")

# ============================================
# RODAPÉ
# ============================================
st.markdown("---")

st.markdown("""
<div class='horario-atendimento'>
    <span class='horario-label'>🕒 Horário:</span>
    <span class='horario-text'> Segunda a Quinta: 07:00 às 17:00 | Sexta: 07:00 às 16:00</span>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class='social-links-container'>
    <div class='social-title'>Siga nossas redes sociais:</div>
    <div class='social-links'>
        <a href='https://www.facebook.com/luvidarte' target='_blank' class='social-link' style='color: #3b5998;'>Facebook</a>
        <a href='https://www.instagram.com/luvidartevidros/' target='_blank' class='social-link' style='color: #E4405F;'>Instagram</a>
        <a href='https://www.linkedin.com/company/luvidarte/' target='_blank' class='social-link' style='color: #0077b5;'>LinkedIn</a>
        <a href='https://www.youtube.com/@luvidartevidros7291' target='_blank' class='social-link' style='color: #ff0000;'>YouTube</a>
        <a href='https://wa.me/5511930119335?text=Olá! Gostaria de informações sobre os produtos Luvidarte' target='_blank' class='social-link' style='color: #25D366;'>WhatsApp</a>
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class='contact-footer'>
    📞 (11) 4676-9000 | 💬 (11) 93011-9335 | ✉️ sac@luvidarte.com.br
</div>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class='footer-bottom'>
    © 2026 Luvidarte - Catálogo Virtual | *Os valores são estimativas e sujeitos à confirmação*
</div>
""", unsafe_allow_html=True)

# ============================================
# WHATSAPP FLUTUANTE
# ============================================
st.markdown("""
<div class="whatsapp-float-fixed">
    <a href="https://wa.me/5511930119335?text=Olá! Gostaria de informações sobre os produtos Luvidarte" target="_blank" class="whatsapp-float">
        <span>💬</span>
        <span>WhatsApp (11) 93011-9335</span>
    </a>
</div>
""", unsafe_allow_html=True)