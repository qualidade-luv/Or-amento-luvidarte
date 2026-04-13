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
# FUNÇÃO PARA FORMATAR MOEDA (PADRÃO BRASILEIRO)
# ============================================
def formatar_moeda(valor):
    """Formata valor para moeda brasileira: R$ 49.984,56"""
    if valor is None or valor == 0:
        return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

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
if 'quantidades' not in st.session_state:
    st.session_state.quantidades = {}

# ============================================
# FUNÇÕES PARA CONTROLAR CARRINHO
# ============================================
def abrir_carrinho():
    st.session_state.carrinho_aberto = True
    st.rerun()

def fechar_carrinho():
    st.session_state.carrinho_aberto = False
    st.rerun()

# ============================================
# FUNÇÃO PARA ATUALIZAR QUANTIDADE NO CARRINHO
# ============================================
def atualizar_quantidade_carrinho(indice, nova_quantidade):
    """Atualiza a quantidade de um item no carrinho e recalcula os totais"""
    if 0 <= indice < len(st.session_state.carrinho):
        item = st.session_state.carrinho[indice]
        item['quantidade'] = nova_quantidade
        item['preco_total'] = item['preco_final'] * nova_quantidade
        item['ipi_total'] = item['valor_ipi'] * nova_quantidade
        item['st_total'] = item['valor_st'] * nova_quantidade
        item['total_geral'] = (item['preco_final'] + item['valor_ipi'] + item['valor_st']) * nova_quantidade
        return True
    return False

# ============================================
# DESCONTO POR VOLUME
# ============================================
def calcular_desconto_volume(total_bruto):
    if total_bruto >= 4000:
        percentual = 0.15
    elif total_bruto >= 2500:
        percentual = 0.10
    else:
        percentual = 0.0
    return percentual, total_bruto * percentual

# ============================================
# FUNÇÃO PARA BUSCAR ALIQUOTA ST
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
# RECALCULAR TODO O CARRINHO
# ============================================
def recalcular_todo_carrinho(uf, cliente_isento, forma_pagamento,
                              dados_st, dados_promo, dados, dados_normal, dados_isento):
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
            desconto_percentual = 0.0
            valor_desconto = 0.0
            preco_com_desconto = preco_bruto
            # Para promoção: aplicar +10% se cliente isento
            if cliente_isento:
                preco_final = preco_com_desconto * 1.10
            else:
                preco_final = preco_com_desconto
        else:
            preco_bruto = produto['Preço'] if pd.notna(produto['Preço']) and produto['Preço'] > 0 else 0
            if forma_pagamento != "PREÇO BASE":
                desconto_percentual = buscar_desconto(icms_uf, forma_pagamento, tabela_desconto)
                valor_desconto = preco_bruto * desconto_percentual
                preco_com_desconto = preco_bruto - valor_desconto
            else:
                desconto_percentual = 0.0
                valor_desconto = 0.0
                preco_com_desconto = preco_bruto
            # Para produto normal: NÃO aplicar acréscimo para isento
            preco_final = preco_com_desconto
        
        ncm_produto = produto.get('NCM', '')
        ipi_percentual = buscar_ipi(ncm_produto, dados_st)
        valor_ipi = preco_final * ipi_percentual
        aliquota_st = buscar_aliquota_st(ncm_produto, uf, dados_st)
        valor_st = 0.0 if cliente_isento else preco_final * aliquota_st
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
def adicionar_ao_carrinho(produto, quantidade, preco_bruto, desconto_percentual,
                           valor_desconto, preco_com_desconto, preco_final,
                           valor_ipi, valor_st, ipi_percentual, aliquota_st, valor_total):
    # Verificar se o produto já existe no carrinho
    for item in st.session_state.carrinho:
        if item['referencia'] == produto['Referência']:
            item['quantidade'] += quantidade
            item['preco_total'] = item['preco_final'] * item['quantidade']
            item['ipi_total'] = item['valor_ipi'] * item['quantidade']
            item['st_total'] = item['valor_st'] * item['quantidade']
            item['total_geral'] = (item['preco_final'] + item['valor_ipi'] + item['valor_st']) * item['quantidade']
            return True
    # Se não existir, adicionar novo item
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
        'total_geral': (preco_final + valor_ipi + valor_st) * quantidade,
        'medidas': produto.get('Medidas', ''),
        'ml': produto.get('ml', ''),
        'imagem_url': produto.get('imagem_url', '')
    })
    return True

def remover_do_carrinho(indice):
    if 0 <= indice < len(st.session_state.carrinho):
        st.session_state.carrinho.pop(indice)

def limpar_carrinho():
    st.session_state.carrinho = []

def calcular_resumo_carrinho():
    if not st.session_state.carrinho:
        return {'total_itens': 0, 'total_geral': 0.0, 'total_ipi': 0.0,
                'total_st': 0.0, 'total_desconto': 0.0, 'total_bruto': 0.0}
    return {
        'total_itens': sum(i['quantidade'] for i in st.session_state.carrinho),
        'total_geral': sum(i['total_geral'] for i in st.session_state.carrinho),
        'total_ipi': sum(i['ipi_total'] for i in st.session_state.carrinho),
        'total_st': sum(i['st_total'] for i in st.session_state.carrinho),
        'total_desconto': sum(i['valor_desconto'] * i['quantidade'] for i in st.session_state.carrinho),
        'total_bruto': sum(i['preco_bruto'] * i['quantidade'] for i in st.session_state.carrinho),
    }

def formatar_mensagem_whatsapp(uf, tipo_cliente, forma_pagamento):
    if not st.session_state.carrinho:
        return "Olá! Gostaria de solicitar um orçamento."
    total_sem_vol = sum(i['total_geral'] for i in st.session_state.carrinho)
    dvol_pct, dvol_val = calcular_desconto_volume(total_sem_vol)
    total_final_msg = total_sem_vol - dvol_val
    msg = "🛍️ *ORÇAMENTO LUVidarte* 🛍️\n\n"
    msg += f"📅 Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
    msg += f"📍 UF: {uf}\n👤 Cliente: {tipo_cliente}\n💳 Pagamento: {forma_pagamento}\n\n"
    msg += "─" * 30 + "\n\n"
    for item in st.session_state.carrinho:
        msg += f"📦 *{item['descricao']}*\n🔖 REF: {item['referencia']}\n"
        msg += f"📊 Quantidade: {item['quantidade']}\n"
        if item.get('medidas'):
            msg += f"📐 Medidas: {item['medidas']}\n"
        msg += f"💰 Valor unitário: {formatar_moeda(item['preco_unitario'])}\n"
        if item.get('ipi_percentual', 0) > 0:
            msg += f"🔷 IPI: {item['ipi_percentual']*100:.2f}%\n"
        msg += f"✅ Subtotal: {formatar_moeda(item['preco_total'])}\n"
        if item.get('ipi_total', 0) > 0:
            msg += f"   + IPI: {formatar_moeda(item['ipi_total'])}\n"
        if item.get('st_total', 0) > 0:
            msg += f"   + ST: {formatar_moeda(item['st_total'])}\n"
        msg += "━" * 22 + "\n"
        msg += f"💎 Total item: {formatar_moeda(item['total_geral'])}\n\n"
    msg += "─" * 30 + "\n\n"
    msg += f"💰 Subtotal: {formatar_moeda(total_sem_vol)}\n"
    if dvol_pct > 0:
        msg += f"🎉 Desconto Volume ({int(dvol_pct*100)}%): - {formatar_moeda(dvol_val)}\n"
        msg += f"✅ *TOTAL COM DESCONTO: {formatar_moeda(total_final_msg)}*\n\n"
    else:
        msg += f"💰 *TOTAL DO ORÇAMENTO: {formatar_moeda(total_sem_vol)}*\n\n"
    msg += "─" * 30 + "\n\n"
    msg += "📋 *OBSERVAÇÕES IMPORTANTES:*\n"
    msg += "• Este é um ORÇAMENTO VIRTUAL, não uma compra finalizada\n"
    msg += "• Valores sujeitos à confirmação de estoque\n"
    msg += "• Prazos e condições serão informados por nossa equipe\n\n"
    msg += "✨ Aguardo confirmação da equipe Luvidarte! ✨"
    return msg

# ============================================
# FUNÇÕES AUXILIARES
# ============================================
def converter_moeda_para_numero(valor):
    if pd.isna(valor) or valor == '' or valor is None:
        return np.nan
    s = str(valor).replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
    s = re.sub(r'[^0-9.]', '', s)
    try:
        return float(s)
    except:
        return np.nan

def converter_percentual_para_numero(valor):
    if pd.isna(valor) or valor == '' or valor is None:
        return 0.0
    s = str(valor).strip().replace('%', '').replace(',', '.')
    try:
        p = float(s)
        if p > 1 and p <= 100:
            p = p / 100
        return p
    except:
        return 0.0

def formatar_ml(valor):
    if pd.isna(valor) or valor == 0 or valor is None or valor == '':
        return None
    try:
        v = float(valor)
        if v >= 1000:
            return f"{v/1000:.3f} L"
        return f"{int(v)} ml" if v == int(v) else f"{v:.3f}".rstrip('0').rstrip('.') + " ml"
    except:
        return None

# ============================================
# CARREGAMENTO DE DADOS
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
    except Exception as e:
        st.error(f"❌ Erro ao carregar a planilha: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=600)
def carregar_planilha_promo(id_planilha, nome_aba="PROMO"):
    try:
        url = f"https://docs.google.com/spreadsheets/d/{id_planilha}/gviz/tq?tqx=out:csv&sheet={nome_aba}"
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def carregar_base_st(id_planilha_st, nome_aba_st="BASE_ST"):
    try:
        url = f"https://docs.google.com/spreadsheets/d/{id_planilha_st}/gviz/tq?tqx=out:csv&sheet={nome_aba_st}"
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def carregar_descontos_normal(id_planilha, nome_aba="NORMAL"):
    try:
        url = f"https://docs.google.com/spreadsheets/d/{id_planilha}/gviz/tq?tqx=out:csv&sheet={nome_aba}"
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def carregar_descontos_isento(id_planilha, nome_aba="ISENTO"):
    try:
        url = f"https://docs.google.com/spreadsheets/d/{id_planilha}/gviz/tq?tqx=out:csv&sheet={nome_aba}"
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()
        return df
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
    linha = df_promo[df_promo[coluna_ref] == ref_limpa]
    if linha.empty:
        linha = df_promo[df_promo[coluna_ref].str.contains(ref_limpa, case=False, na=False)]
        if linha.empty:
            return None
    uf_upper = uf.upper()
    if uf_upper == "SP":
        col_icms = "18%"
    elif uf_upper in ["MG", "RS", "SE", "PR", "RJ", "SC"]:
        col_icms = "12%"
    else:
        col_icms = "7%"
    col_preco = next((c for c in df_promo.columns if str(c).strip() == col_icms), None)
    if col_preco is None:
        return None
    valor = linha.iloc[0][col_preco]
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
    linha = df_st[df_st['NCM_LIMPO'] == ncm_limpo]
    if linha.empty:
        return 0.0
    v = linha.iloc[0, 0]
    if pd.isna(v):
        return 0.0
    if isinstance(v, str):
        v = v.replace("%", "").replace(",", ".").strip()
    try:
        ipi = float(v)
        if ipi > 1 and ipi <= 100:
            ipi = ipi / 100
        return ipi
    except:
        return 0.0

def determinar_icms_por_uf(uf: str) -> float:
    u = uf.upper()
    if u == "SP":
        return 18.0
    elif u in ["MG", "RS", "SE", "PR", "RJ", "SC"]:
        return 12.0
    return 7.0

def buscar_desconto(icms: float, forma_pagamento: str, df_desconto: pd.DataFrame) -> float:
    if df_desconto.empty or forma_pagamento == "PREÇO BASE":
        return 0.0
    df_temp = df_desconto.copy()
    df_temp['ICMS_LIMPO'] = pd.to_numeric(
        df_temp['ICMS'].astype(str).str.replace('%', '').str.replace(',', '.').str.strip(),
        errors='coerce'
    )
    df_temp['FORMA_LIMPO'] = df_temp['FORMA'].apply(lambda x: str(x).strip() if pd.notna(x) else "")
    forma_para_buscar = "" if forma_pagamento == "VISTA" else f"{float(forma_pagamento):.1f}"
    df_f = df_temp[(df_temp['ICMS_LIMPO'] == float(icms)) & (df_temp['FORMA_LIMPO'] == forma_para_buscar)]
    if not df_f.empty:
        return converter_percentual_para_numero(df_f.iloc[0]['DESCONTO'])
    return 0.0

def carregar_logo():
    url_drive = "https://drive.google.com/uc?export=download&id=1wiwp3txOXGsEMRrUgzdLFlxQL2188uTw"
    try:
        r = requests.get(url_drive, timeout=15)
        if r.status_code == 200 and 'image' in r.headers.get('content-type', ''):
            return Image.open(BytesIO(r.content))
    except:
        pass
    return None

# ============================================
# CSS GLOBAL
# ============================================
st.markdown("""
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
.stDecoration { display: none; }
.stAppDeployButton { display: none !important; }
.main > div { padding-top: 0.5rem; }
.stApp { background-color: #F7F7F7; }

.main-banner {
    background-color: #FFF; border-radius: 16px; padding: 15px 20px;
    margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    display: flex; align-items: center; justify-content: space-between;
    gap: 15px; min-height: 90px; border: 1px solid #E0E0E0; flex-wrap: wrap;
}
.logo-img { max-height: 60px; width: auto; object-fit: contain; }
.banner-text { flex-grow: 1; text-align: center; }
.banner-text h1 { font-size: clamp(20px,5vw,38px); margin: 0; font-weight: bold; color: #000; }
.banner-text p { font-size: clamp(11px,3vw,15px); margin: 5px 0 0 0; color: #333; }

.legal-banner {
    background-color: #FFF9E6; border-left: 4px solid #C9A03D;
    border-radius: 8px; padding: 10px 15px; margin: 10px 0; font-size: 12px; color: #666;
}
.contato-central {
    text-align: center; margin: 10px 0 20px 0; padding: 10px;
    font-size: clamp(11px,3vw,13px); color: #666; background-color: #FFF;
    border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); border: 1px solid #E8E8E8;
}

/* LINK DO CARRINHO NO TOPO */
.cart-link-top {
    text-align: right;
}
.cart-link-button {
    background: none !important;
    border: none !important;
    color: #2E7D32 !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    display: inline-flex !important;
    align-items: center !important;
    gap: 8px !important;
    cursor: pointer !important;
    padding: 0 !important;
    white-space: nowrap;
    text-decoration: none !important;
}
.cart-link-button:hover {
    color: #1B5E20 !important;
    text-decoration: underline !important;
}
.cart-link-badge {
    background: #D32F2F;
    color: white;
    border-radius: 50%;
    min-width: 20px;
    height: 20px;
    font-size: 11px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-weight: bold;
    padding: 0 4px;
}

/* WHATSAPP FLUTUANTE */
.whatsapp-float-fixed { position: fixed; bottom: 20px; right: 20px; z-index: 99990; }
.whatsapp-float {
    background-color: #25D366; color: white; border-radius: 50px;
    padding: 10px 18px; font-size: 13px; font-weight: bold;
    box-shadow: 0 4px 12px rgba(0,0,0,0.25); display: flex;
    align-items: center; gap: 8px; text-decoration: none; transition: all 0.3s ease;
}
.whatsapp-float:hover { transform: scale(1.05); background-color: #075E54; }

/* PRODUTOS */
.product-card {
    background-color: #FFF; border-radius: 12px; padding: 16px; margin: 10px 0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08); transition: all 0.2s ease; position: relative;
}
.product-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
.product-card.promo-card { border: 1.5px solid #D32F2F; box-shadow: 0 2px 8px rgba(211,47,47,0.15); }
.product-card.normal-card { border: 1px solid #E0E0E0; }
.promo-badge {
    position: absolute; top: -8px; right: 10px;
    background: linear-gradient(135deg,#D32F2F,#B71C1C);
    color: white; font-size: 10px; font-weight: bold;
    padding: 4px 10px; border-radius: 20px; box-shadow: 0 2px 6px rgba(0,0,0,0.2); z-index: 10;
}
.tabela-badge {
    position: absolute; top: -8px; right: 10px;
    background: linear-gradient(135deg,#666,#444);
    color: white; font-size: 10px; font-weight: bold;
    padding: 4px 10px; border-radius: 20px; box-shadow: 0 2px 6px rgba(0,0,0,0.2); z-index: 10;
}
.ref { color: #666; font-size: 11px; font-weight: 500; text-transform: uppercase; display: block; }
.product-name { color: #000; font-size: 17px; font-weight: 600; margin: 8px 0 4px 0; }
.product-category { color: #666; font-size: 12px; margin-bottom: 12px; }
.product-detail { font-size: 13px; margin: 5px 0; min-height: 24px; }

/* RESUMO CARRINHO */
.resumo-card {
    background-color: #FFF; border-radius: 12px; padding: 16px; margin: 10px 0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08); border: 1px solid #E0E0E0;
}
.resumo-title {
    font-size: 16px; font-weight: bold; color: #2E7D32; margin-bottom: 10px;
    border-bottom: 2px solid #C9A03D; display: inline-block; padding-bottom: 5px;
}
.resumo-line { display: flex; justify-content: space-between; padding: 5px 0; font-size: 13px; }
.resumo-line.total {
    font-weight: bold; font-size: 16px; border-top: 1px solid #E0E0E0;
    margin-top: 8px; padding-top: 8px; color: #D32F2F;
}
.desconto-vol-banner {
    background: linear-gradient(135deg,#E8F5E9,#C8E6C9); border: 2px solid #4CAF50;
    border-radius: 10px; padding: 12px 16px; margin: 12px 0;
    text-align: center; font-weight: bold; color: #1B5E20; font-size: 15px;
}
.prox-desconto-hint {
    background: linear-gradient(135deg,#E8F5E9,#C8E6C9); border: 1px solid #A5D6A7;
    border-radius: 8px; padding: 8px 12px; margin: 8px 0 12px 0;
    font-size: 12px; color: #2E7D32; text-align: center;
}

/* RODAPE */
.social-links-container { text-align: center; margin: 15px 0; }
.social-title { color: #C9A03D; font-weight: bold; font-size: 14px; }
.social-links { display: flex; justify-content: center; gap: 25px; margin: 10px 0; flex-wrap: wrap; }
.social-link { text-decoration: none; font-size: 14px; font-weight: 500; padding: 5px 0; }
.contact-footer { text-align: center; font-size: 13px; color: #555; }
.footer-bottom {
    text-align: center; font-size: 12px; color: #666;
    padding: 15px 0;
    margin-top: 20px;
}
.horario-atendimento { text-align: center; margin: 10px 0; font-size: 13px; }
.horario-label { color: #C9A03D; font-weight: bold; }
.horario-text { color: #555; }

@media (max-width: 768px) {
    .whatsapp-float-fixed { bottom: 15px; right: 15px; }
    .cart-link-button { font-size: 12px !important; white-space: normal; }
}
</style>
""", unsafe_allow_html=True)

# ============================================
# BANNER PRINCIPAL
# ============================================
logo_img = carregar_logo()
if logo_img:
    buffered = BytesIO()
    logo_img.save(buffered, format="PNG")
    img_b64 = base64.b64encode(buffered.getvalue()).decode()
    st.markdown(f"""
    <div class='main-banner'>
        <div><img src='data:image/png;base64,{img_b64}' class='logo-img'></div>
        <div class='banner-text'>
            <h1>Catálogo Virtual</h1>
            <p>Peças exclusivas em vidro e decoração</p>
        </div>
        <div style='width:80px;'></div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div class='main-banner'>
        <div class='banner-text' style='width:100%;'>
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

st.markdown("""
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
ID_PLANILHA     = "1DCmwFzQvbQYDBsQft17VO9szjixgq1Bp09dYTfu142w"
NOME_ABA        = "base"
NOME_ABA_PROMO  = "PROMO"
NOME_ABA_ST     = "BASE_ST"
NOME_ABA_NORMAL = "NORMAL"
NOME_ABA_ISENTO = "ISENTO"

with st.spinner("🔄 Carregando produtos..."):
    dados        = carregar_planilha(ID_PLANILHA, NOME_ABA)
    dados_promo  = carregar_planilha_promo(ID_PLANILHA, NOME_ABA_PROMO)
    dados_st     = carregar_base_st(ID_PLANILHA, NOME_ABA_ST)
    dados_normal = carregar_descontos_normal(ID_PLANILHA, NOME_ABA_NORMAL)
    dados_isento = carregar_descontos_isento(ID_PLANILHA, NOME_ABA_ISENTO)

if dados.empty:
    st.stop()

# ============================================
# SIDEBAR
# ============================================
st.sidebar.header("🔍 FILTRAR PRODUTOS")
st.sidebar.markdown(f"📊 **Total:** {len(dados)} produtos")

uf_selecionada = st.sidebar.selectbox(
    "📍 UF (ICMS)",
    options=["SP","MG","RS","SE","PR","RJ","SC","MT","AC","AL","AP","AM",
             "BA","CE","DF","ES","GO","MA","MS","PA","PB","PE","PI","RN","RO","RR","TO"],
    index=0
)

grupos = ["Todos"] + sorted(dados['GRUPO'].unique().tolist())
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

cliente_isento  = st.sidebar.checkbox("🏷️ Cliente Isento", value=False)
forma_pagamento = st.sidebar.radio("💳 Pagamento",
                                   options=["PREÇO BASE","VISTA","30","45","60"], index=0)

# Indicador de desconto por volume na sidebar
st.sidebar.markdown("---")
res_sb  = calcular_resumo_carrinho()
tot_sb  = res_sb['total_geral']
if tot_sb == 0:
    st.sidebar.markdown("""
    <div style='background:#E8F5E9;border-radius:8px;padding:10px;font-size:12px;
                color:#2E7D32;text-align:center;border:1px solid #A5D6A7;'>
        🎉 <strong>Desconto por Volume</strong><br>
        Acima de R$ 2.500 → <strong>10% OFF</strong><br>
        Acima de R$ 4.000 → <strong>15% OFF</strong>
    </div>""", unsafe_allow_html=True)
elif tot_sb < 2500:
    st.sidebar.markdown(f"""
    <div style='background:#E8F5E9;border-radius:8px;padding:10px;font-size:12px;
                color:#2E7D32;text-align:center;border:1px solid #A5D6A7;'>
        🎯 Faltam <strong>{formatar_moeda(2500-tot_sb)}</strong> para<br>
        ganhar <strong>10% de desconto</strong>!
    </div>""", unsafe_allow_html=True)
elif tot_sb < 4000:
    st.sidebar.markdown(f"""
    <div style='background:#E8F5E9;border-radius:8px;padding:10px;font-size:12px;
                color:#2E7D32;text-align:center;border:1px solid #A5D6A7;'>
        ✅ <strong>10% de desconto</strong> ativo!<br>
        Faltam <strong>{formatar_moeda(4000-tot_sb)}</strong> para <strong>15% OFF</strong>
    </div>""", unsafe_allow_html=True)
else:
    st.sidebar.markdown("""
    <div style='background:#C8E6C9;border-radius:8px;padding:10px;font-size:12px;
                color:#1B5E20;text-align:center;border:1px solid #66BB6A;font-weight:bold;'>
        🏆 <strong>15% de desconto</strong> ativo!
    </div>""", unsafe_allow_html=True)

# Monitorar mudanças nos filtros
filtros_atual = (uf_selecionada, cliente_isento, forma_pagamento)
if st.session_state.filtros_anteriores != filtros_atual:
    st.session_state.filtros_anteriores = filtros_atual
    if st.session_state.carrinho:
        recalcular_todo_carrinho(uf_selecionada, cliente_isento, forma_pagamento,
                                 dados_st, dados_promo, dados, dados_normal, dados_isento)
        st.rerun()

# ============================================
# TELA DO CARRINHO (COM EDIÇÃO DE QUANTIDADE)
# ============================================
if st.session_state.get('carrinho_aberto', False):

    st.markdown("# 🛒 Meu Orçamento Virtual")
    st.markdown("Revise os itens do seu orçamento antes de enviar.")

    if st.button("← Voltar aos produtos"):
        fechar_carrinho()

    if not st.session_state.carrinho:
        st.info("Seu orçamento está vazio. Adicione produtos para continuar.")
        st.stop()

    total_geral = total_ipi_geral = total_st_geral = total_desconto_geral = total_bruto_geral = 0.0

    for idx, item in enumerate(st.session_state.carrinho):
        c1, c2, c3, c4 = st.columns([1, 3, 2, 1])
        with c1:
            img_url = item.get('imagem_url', '')
            if img_url and pd.notna(img_url) and str(img_url).strip():
                try:
                    st.image(img_url, width=80)
                except:
                    st.image("https://via.placeholder.com/80x80?text=Luvidarte", width=80)
            else:
                st.image("https://via.placeholder.com/80x80?text=Luvidarte", width=80)
        with c2:
            st.markdown(f"**{item['descricao']}**")
            st.markdown(f"🔖 REF: {item['referencia']}")
            st.markdown(f"📦 Grupo: {item['grupo']}")
            if item.get('medidas'):
                st.markdown(f"📐 {item['medidas']}")
        with c3:
            st.markdown(f"💰 **Preço Bruto:** {formatar_moeda(item['preco_bruto'])}")
            if item['desconto_percentual'] > 0:
                st.markdown(f"🎯 **Desconto:** {item['desconto_percentual']*100:.2f}% ({formatar_moeda(item['valor_desconto'])})")
                st.markdown(f"📉 **Valor c/ Desconto:** {formatar_moeda(item['preco_com_desconto'])}")
            st.markdown(f"💰 **Valor unitário:** {formatar_moeda(item['preco_unitario'])}")
            
            # Campo para editar quantidade
            col_qtd1, col_qtd2 = st.columns([1, 2])
            with col_qtd1:
                nova_qtd = st.number_input(
                    "Quantidade",
                    min_value=1,
                    max_value=999,
                    value=int(item['quantidade']),
                    step=1,
                    key=f"edit_qtd_{idx}",
                    label_visibility="collapsed"
                )
                if nova_qtd != item['quantidade']:
                    atualizar_quantidade_carrinho(idx, nova_qtd)
                    st.rerun()
            
            with col_qtd2:
                st.markdown(f"💎 **Subtotal:** {formatar_moeda(item['preco_total'])}")
            
            if item.get('ipi_percentual', 0) > 0:
                st.markdown(f"🔷 IPI: {item['ipi_percentual']*100:.2f}% = {formatar_moeda(item['ipi_total'])}")
            if item.get('st_total', 0) > 0:
                st.markdown(f"🟣 ST: {formatar_moeda(item['st_total'])}")
        with c4:
            st.markdown("**Total Item**")
            st.markdown(f"### {formatar_moeda(item['total_geral'])}")
            if st.button("🗑️ Remover", key=f"remove_{idx}"):
                remover_do_carrinho(idx)
                st.rerun()
        st.markdown("---")
        total_geral        += item['total_geral']
        total_ipi_geral    += item['ipi_total']
        total_st_geral     += item['st_total']
        total_desconto_geral += item['valor_desconto'] * item['quantidade']
        total_bruto_geral  += item['preco_bruto'] * item['quantidade']

    dvol_pct, dvol_val   = calcular_desconto_volume(total_geral)
    total_final_com_vol  = total_geral - dvol_val

    if dvol_pct > 0:
        st.markdown(f"""
        <div class='desconto-vol-banner'>
            🎉 Parabéns! Você ganhou <strong>{int(dvol_pct*100)}% de desconto</strong> por volume!<br>
            Economia de <strong>{formatar_moeda(dvol_val)}</strong> aplicada automaticamente.
        </div>""", unsafe_allow_html=True)
    elif 2500 - total_geral > 0:
        st.markdown(f"""
        <div class='prox-desconto-hint'>
            💡 Adicione mais <strong>{formatar_moeda(2500-total_geral)}</strong> e ganhe <strong>10% de desconto</strong> no total!
        </div>""", unsafe_allow_html=True)

    st.markdown("## 📋 Resumo do Orçamento")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"""
        <div class='resumo-card'>
            <div class='resumo-title'>📊 Resumo de Valores</div>
            <div class='resumo-line'>
                <span>💰 Valor Bruto Total:</span>
                <span><strong>{formatar_moeda(total_bruto_geral)}</strong></span>
            </div>
            <div class='resumo-line'>
                <span>🎯 Desconto (condição pagto):</span>
                <span><strong style='color:#D32F2F;'>- {formatar_moeda(total_desconto_geral)}</strong></span>
            </div>
            <div class='resumo-line'>
                <span>📉 Valor com Desconto:</span>
                <span><strong>{formatar_moeda(total_bruto_geral - total_desconto_geral)}</strong></span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class='resumo-card'>
            <div class='resumo-title'>🏷️ Tributos e Total Final</div>
            <div class='resumo-line'>
                <span>🔷 IPI Total:</span>
                <span><strong>{formatar_moeda(total_ipi_geral)}</strong></span>
            </div>
            <div class='resumo-line'>
                <span>🟣 ST Total:</span>
                <span><strong>{formatar_moeda(total_st_geral)}</strong></span>
            </div>
            <div class='resumo-line'>
                <span>📦 Subtotal (c/ IPI + ST):</span>
                <span><strong>{formatar_moeda(total_geral)}</strong></span>
            </div>
            <div class='resumo-line total'>
                <span>✅ TOTAL DO ORÇAMENTO:</span>
                <span><strong style='color:#D32F2F;'>{formatar_moeda(total_final_com_vol)}</strong></span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    cb1, cb2, cb3 = st.columns(3)
    with cb1:
        if st.button("← Continuar comprando", use_container_width=True):
            fechar_carrinho()
    with cb2:
        if st.button("🗑️ Limpar Carrinho", use_container_width=True):
            limpar_carrinho()
            st.rerun()
    with cb3:
        tipo_cl  = "ISENTO" if cliente_isento else "NORMAL"
        msg_wpp  = formatar_mensagem_whatsapp(uf_selecionada, tipo_cl, forma_pagamento)
        msg_cod  = urllib.parse.quote(msg_wpp)
        link_wpp = f"https://wa.me/5511930119335?text={msg_cod}"
        st.markdown(
            f'<a href="{link_wpp}" target="_blank">'
            f'<button style="width:100%;background-color:#25D366;color:white;border:none;'
            f'border-radius:8px;padding:10px;font-weight:bold;cursor:pointer;font-size:14px;">'
            f'📱 Enviar Orçamento via WhatsApp</button></a>',
            unsafe_allow_html=True
        )
    st.stop()

# ============================================
# FILTROS
# ============================================
icms_uf         = determinar_icms_por_uf(uf_selecionada)
tabela_desconto = dados_isento if cliente_isento else dados_normal
tipo_cliente    = "ISENTO" if cliente_isento else "NORMAL"

dados_filtrados = dados.copy()
if grupo_escolhido == "Promoção":
    dados_filtrados = dados_filtrados[
        dados_filtrados['Promo'].astype(str).str.upper().str.contains('SIM', na=False)]
elif grupo_escolhido != "Todos":
    dados_filtrados = dados_filtrados[dados_filtrados['GRUPO'] == grupo_escolhido]
if len(precos_validos) > 0:
    dados_filtrados = dados_filtrados[
        (dados_filtrados['Preço'].isna()) |
        ((dados_filtrados['Preço'] >= faixa_preco[0]) & (dados_filtrados['Preço'] <= faixa_preco[1]))
    ]
if busca_referencia:
    dados_filtrados = dados_filtrados[
        dados_filtrados['Referência'].str.contains(busca_referencia, case=False, na=False)]

total_encontrados = len(dados_filtrados)

# ============================================
# HEADER COM LINK DO CARRINHO
# ============================================
resumo_header = calcular_resumo_carrinho()

col_titulo, col_link = st.columns([3, 1])

with col_titulo:
    st.markdown(f"## ✨ Produtos Encontrados: {total_encontrados}")

with col_link:
    if resumo_header['total_itens'] > 0:
        dvol_pct, dvol_val = calcular_desconto_volume(resumo_header['total_geral'])
        total_exibir_header = resumo_header['total_geral'] - dvol_val
        total_fmt_header = formatar_moeda(total_exibir_header)
        if st.button(
            f"🛒 Acessar meu carrinho ({resumo_header['total_itens']}) {total_fmt_header}",
            key="cart_link_top"
        ):
            abrir_carrinho()
    else:
        st.markdown(
            f'<div style="text-align:right; color:#2E7D32; opacity:0.6; font-size:14px;">'
            f'🛒 Acessar meu carrinho (0) R$ 0,00</div>',
            unsafe_allow_html=True
        )

st.markdown("---")

# ============================================
# PAGINAÇÃO
# ============================================
ITENS_POR_PAGINA = 9
total_paginas = max(1, (total_encontrados + ITENS_POR_PAGINA - 1) // ITENS_POR_PAGINA)
if st.session_state.pagina_atual > total_paginas:
    st.session_state.pagina_atual = total_paginas
indice_inicio = (st.session_state.pagina_atual - 1) * ITENS_POR_PAGINA
indice_fim    = min(indice_inicio + ITENS_POR_PAGINA, total_encontrados)
dados_pagina  = dados_filtrados.iloc[indice_inicio:indice_fim]

# ============================================
# INFO RÁPIDA
# ============================================
ci1, ci2, ci3, ci4 = st.columns(4)
with ci1:
    st.info(f"🏢 **UF:** {uf_selecionada} (ICMS {icms_uf}%)")
with ci2:
    st.info(f"📋 **Cliente:** {tipo_cliente}")
with ci3:
    if forma_pagamento == "PREÇO BASE":
        st.warning(f"💰 **Condição:** {forma_pagamento}")
    else:
        st.success(f"💰 **Condição:** {forma_pagamento} dias")
with ci4:
    if grupo_escolhido == "Promoção":
        st.success(f"🏷️ **Grupo:** {grupo_escolhido} - Ofertas!")
    else:
        st.info(f"📦 **Grupo:** {grupo_escolhido}")

st.markdown("---")

# ============================================
# GRID DE PRODUTOS
# ============================================
if dados_filtrados.empty:
    st.warning("😕 Nenhum produto encontrado.")
else:
    colunas = st.columns(3)

    for posicao, (indice, produto) in enumerate(dados_pagina.iterrows()):
        is_promo    = 'SIM' in str(produto.get('Promo', '')).strip().upper()
        preco_promo = None
        if is_promo and not dados_promo.empty:
            preco_promo = buscar_preco_promo(produto['Referência'], uf_selecionada, dados_promo)

        if is_promo and preco_promo is not None and preco_promo > 0:
            preco_bruto = preco_promo
            desconto_percentual = 0.0
            valor_desconto = 0.0
            preco_com_desconto = preco_bruto
            # CORREÇÃO: Para cliente isento em promoção: aplicar +10%
            if cliente_isento:
                preco_final = preco_com_desconto * 1.10
            else:
                preco_final = preco_com_desconto
        else:
            preco_bruto = produto['Preço'] if pd.notna(produto['Preço']) and produto['Preço'] > 0 else 0
            if forma_pagamento != "PREÇO BASE":
                desconto_percentual = buscar_desconto(icms_uf, forma_pagamento, tabela_desconto)
                valor_desconto = preco_bruto * desconto_percentual
                preco_com_desconto = preco_bruto - valor_desconto
            else:
                desconto_percentual = 0.0
                valor_desconto = 0.0
                preco_com_desconto = preco_bruto
            # Para produto normal: NÃO aplicar acréscimo para isento
            preco_final = preco_com_desconto

        ncm_produto = produto.get('NCM', '')
        ipi_percentual = buscar_ipi(ncm_produto, dados_st)
        valor_ipi = preco_final * ipi_percentual
        aliquota_st = buscar_aliquota_st(ncm_produto, uf_selecionada, dados_st)
        valor_st = 0.0 if cliente_isento else preco_final * aliquota_st
        valor_total = preco_final + valor_ipi + valor_st

        produto_carrinho = {
            'Referência': produto['Referência'],
            'Descrição':  produto['Descrição'],
            'GRUPO':      produto['GRUPO'],
            'Medidas':    produto.get('Medidas', ''),
            'ml':         produto.get('ml', ''),
            'imagem_url': produto.get('imagem_url', '')
        }

        with colunas[posicao % 3]:
            card_class = "product-card promo-card" if is_promo else "product-card normal-card"

            badge_html = (
                "<div class='promo-badge'>🔥 PROMOÇÃO</div>"
                if is_promo else
                "<div class='tabela-badge'>📋 TABELA</div>"
            )
            st.markdown(
                f"<div class='{card_class}'>"
                f"{badge_html}"
                f"<span class='ref'>🔖 REF: {produto['Referência']}</span>"
                f"<div class='product-name'>{produto['Descrição']}</div>"
                f"<div class='product-category'>{produto['GRUPO']}</div>"
                f"</div>",
                unsafe_allow_html=True
            )

            # Imagem
            img_url = str(produto.get('imagem_url', '')).strip()
            if img_url and pd.notna(produto.get('imagem_url')):
                try:
                    st.image(img_url, use_container_width=True)
                except:
                    st.image("https://via.placeholder.com/300x200?text=Sem+Imagem", use_container_width=True)
            else:
                st.image("https://via.placeholder.com/300x200?text=Sem+Imagem", use_container_width=True)

            # ML
            ml_fmt = formatar_ml(produto.get('ml'))
            st.markdown(
                f'<div class="product-detail">📏 <strong>{ml_fmt if ml_fmt else "--"}</strong></div>',
                unsafe_allow_html=True
            )

            # Medidas
            med = produto.get('Medidas', '')
            if pd.notna(med) and str(med).strip():
                st.markdown(f'<div class="product-detail">📐 {med}</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="product-detail">📐 <strong>--</strong></div>', unsafe_allow_html=True)

            # Preços - PARA PROMOÇÃO
            if is_promo and preco_promo is not None and preco_promo > 0:
                st.markdown(f"🏷️ **Preço Promocional:** {formatar_moeda(preco_bruto)}")
                if cliente_isento:
                    st.caption("✨ +10% (Cliente Isento)")
                    st.markdown(f"💰 **Preço com acréscimo:** {formatar_moeda(preco_final)}")
                
                if forma_pagamento == "VISTA":
                    desconto_vista = 0.04
                    valor_com_desconto_vista = preco_final * (1 - desconto_vista)
                    st.markdown(f"🎯 **Desconto à vista:** 4%")
                    st.markdown(f"💰 **Valor com desconto:** {formatar_moeda(valor_com_desconto_vista)}")
                    preco_final = valor_com_desconto_vista
                    valor_ipi = preco_final * ipi_percentual
                    valor_total = preco_final + valor_ipi + valor_st
                else:
                    if forma_pagamento != "PREÇO BASE":
                        st.markdown(f"🎯 **Desconto:** Não aplicável em promoção")
                
                if ipi_percentual > 0:
                    st.markdown(f"🔷 **IPI:** {ipi_percentual*100:.2f}% = {formatar_moeda(valor_ipi)}")
                else:
                    st.markdown("🔷 **IPI:** Não aplicável")
                
                if cliente_isento:
                    st.markdown(f"🟣 **ST ({uf_selecionada}):** Cliente Isento — ST não aplicada")
                    st.markdown(f"✅ **TOTAL COM IPI:** {formatar_moeda(preco_final + valor_ipi)}")
                elif aliquota_st > 0:
                    st.markdown(f"🟣 **Alíq. ST ({uf_selecionada}):** {aliquota_st*100:.2f}%")
                    st.markdown(f"📊 **Valor ST:** {formatar_moeda(valor_st)}")
                    st.markdown(f"✅ **TOTAL COM IPI + ST:** {formatar_moeda(valor_total)}")
                else:
                    st.markdown(f"🟣 **ST ({uf_selecionada}):** Não aplicável")
                    st.markdown(f"✅ **TOTAL COM IPI:** {formatar_moeda(preco_final + valor_ipi)}")
            
            else:
                # Preços - PARA PRODUTO NORMAL
                st.markdown(f"💰 **Preço Bruto:** {formatar_moeda(preco_bruto)}")
                if desconto_percentual > 0:
                    st.markdown(f"🎯 **Desconto:** {desconto_percentual*100:.2f}% ({formatar_moeda(valor_desconto)})")
                    st.markdown(f"📉 **Valor c/ Desconto:** {formatar_moeda(preco_com_desconto)}")
                
                if ipi_percentual > 0:
                    st.markdown(f"🔷 **IPI:** {ipi_percentual*100:.2f}% = {formatar_moeda(valor_ipi)}")
                else:
                    st.markdown("🔷 **IPI:** Não aplicável")
                
                if cliente_isento:
                    st.markdown(f"🟣 **ST ({uf_selecionada}):** Cliente Isento — ST não aplicada")
                    st.markdown(f"✅ **TOTAL COM IPI:** {formatar_moeda(preco_final + valor_ipi)}")
                elif aliquota_st > 0:
                    st.markdown(f"🟣 **Alíq. ST ({uf_selecionada}):** {aliquota_st*100:.2f}%")
                    st.markdown(f"📊 **Valor ST:** {formatar_moeda(valor_st)}")
                    st.markdown(f"✅ **TOTAL COM IPI + ST:** {formatar_moeda(valor_total)}")
                else:
                    st.markdown(f"🟣 **ST ({uf_selecionada}):** Não aplicável")
                    st.markdown(f"✅ **TOTAL COM IPI:** {formatar_moeda(preco_final + valor_ipi)}")

            st.markdown("---")

            # Seletor de quantidade
            qtd_key = f"qtd_{indice}"
            if qtd_key not in st.session_state.quantidades:
                st.session_state.quantidades[qtd_key] = 1

            col_qtd, col_btn = st.columns([1, 2])

            with col_qtd:
                nova_qtd = st.number_input(
                    "Quantidade",
                    min_value=1,
                    max_value=999,
                    value=st.session_state.quantidades[qtd_key],
                    step=1,
                    key=f"num_{indice}",
                    label_visibility="collapsed"
                )
                if nova_qtd != st.session_state.quantidades[qtd_key]:
                    st.session_state.quantidades[qtd_key] = nova_qtd

            with col_btn:
                qtd_atual = st.session_state.quantidades[qtd_key]
                if st.button("🛒 Adicionar", key=f"add_{indice}", use_container_width=True):
                    sucesso = adicionar_ao_carrinho(
                        produto_carrinho, qtd_atual,
                        preco_bruto, desconto_percentual, valor_desconto,
                        preco_com_desconto, preco_final, valor_ipi, valor_st,
                        ipi_percentual, aliquota_st, valor_total
                    )
                    if sucesso:
                        st.success(f"✅ Produto adicionado ao orçamento! Quantidade: {qtd_atual}")
                        time.sleep(0.5)
                        st.rerun()

            st.markdown("---")

    # Paginação
    if total_paginas > 1:
        st.markdown("---")
        _, cpag, _ = st.columns([1, 2, 1])
        with cpag:
            pag_sel = st.selectbox(
                "📄 Página",
                options=list(range(1, total_paginas + 1)),
                index=st.session_state.pagina_atual - 1,
                key="pagina_select"
            )
            if pag_sel != st.session_state.pagina_atual:
                st.session_state.pagina_atual = pag_sel
                st.rerun()
            st.markdown(
                f'<div style="text-align:center;font-size:12px;">'
                f'Mostrando {indice_inicio+1}–{min(indice_fim,total_encontrados)} '
                f'de {total_encontrados}</div>',
                unsafe_allow_html=True
            )
        st.progress(
            st.session_state.pagina_atual / total_paginas,
            text=f"Página {st.session_state.pagina_atual} de {total_paginas}"
        )

# ============================================
# RODAPÉ
# ============================================
st.markdown("---")
st.markdown("""
<div class='horario-atendimento'>
    <span class='horario-label'>🕒 Horário:</span>
    <span class='horario-text'> Segunda a Quinta: 07:00 às 17:00 | Sexta: 07:00 às 16:00</span>
</div>""", unsafe_allow_html=True)

st.markdown("""
<div class='social-links-container'>
    <div class='social-title'>Siga nossas redes sociais:</div>
    <div class='social-links'>
        <a href='https://www.facebook.com/luvidarte' target='_blank'
           class='social-link' style='color:#3b5998;'>Facebook</a>
        <a href='https://www.instagram.com/luvidartevidros/' target='_blank'
           class='social-link' style='color:#E4405F;'>Instagram</a>
        <a href='https://www.linkedin.com/company/luvidarte/' target='_blank'
           class='social-link' style='color:#0077b5;'>LinkedIn</a>
        <a href='https://www.youtube.com/@luvidartevidros7291' target='_blank'
           class='social-link' style='color:#ff0000;'>YouTube</a>
        <a href='https://wa.me/5511930119335?text=Olá! Gostaria de informações sobre os produtos Luvidarte'
           target='_blank' class='social-link' style='color:#25D366;'>WhatsApp</a>
    </div>
</div>""", unsafe_allow_html=True)

st.markdown("""
<div class='contact-footer'>
    📞 (11) 4676-9000 | 💬 (11) 93011-9335 | ✉️ sac@luvidarte.com.br
</div>""", unsafe_allow_html=True)

st.markdown("""
<div class='footer-bottom'>
    © 2026 Luvidarte - Catálogo Virtual |
    <em>Os valores são estimativas e sujeitos à confirmação</em>
</div>
""", unsafe_allow_html=True)

# ============================================
# WHATSAPP FLUTUANTE
# ============================================
st.markdown("""
<div class="whatsapp-float-fixed">
    <a href="https://wa.me/5511930119335?text=Olá! Gostaria de informações sobre os produtos Luvidarte"
       target="_blank" class="whatsapp-float">
        💬 WhatsApp (11) 93011-9335
    </a>
</div>
""", unsafe_allow_html=True)
