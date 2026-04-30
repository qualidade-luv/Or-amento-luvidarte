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
import hashlib
import secrets
import socket
import urllib3
import pytz
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

# ============================================
# CONFIGURAÇÕES DE SEGURANÇA E PRIVACIDADE
# ============================================

# Desabilitar warnings de SSL (se necessário)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configurar timeout global
socket.setdefaulttimeout(30)

# Configurações de sessão - tempo limite (em segundos)
SESSION_TIMEOUT = 1800  # 30 minutos

# Configurar timezone do Brasil
TIMEZONE_BR = pytz.timezone('America/Sao_Paulo')

# ============================================
# CONFIGURAÇÃO DO GOOGLE SHEETS
# ============================================

# ID da planilha de cadastro
ID_PLANILHA_CADASTRO = "1_s01QhZJni2dYoJwkWflEtdrKzSZ5yt7mpZvASPlFxk"

# Escopos necessários para o Google Sheets API
ESCOPOS = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

def conectar_google_sheets():
    """Conecta ao Google Sheets usando credenciais (local ou secrets)"""
    try:
        credenciais_dict = None
        
        # 1. TENTAR STREAMLIT SECRETS (para produção/nuvem)
        try:
            if hasattr(st, 'secrets') and 'google' in st.secrets:
                credenciais_dict = {
                    "type": st.secrets["google"].get("type", "service_account"),
                    "project_id": st.secrets["google"].get("project_id", ""),
                    "private_key_id": st.secrets["google"].get("private_key_id", ""),
                    "private_key": st.secrets["google"].get("private_key", ""),
                    "client_email": st.secrets["google"].get("client_email", ""),
                    "client_id": st.secrets["google"].get("client_id", ""),
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "client_x509_cert_url": st.secrets["google"].get("client_x509_cert_url", "")
                }
                credenciais_dict = {k: v for k, v in credenciais_dict.items() if v}
                if credenciais_dict.get('private_key'):
                    st.info("🔐 Usando credenciais do Streamlit Secrets")
        except Exception as e:
            pass
        
        # 2. TENTAR ARQUIVO LOCAL (para desenvolvimento)
        if not credenciais_dict or not credenciais_dict.get('private_key'):
            try:
                with open('credentials.json', 'r') as f:
                    credenciais_dict = json.load(f)
                st.info("📁 Usando credenciais do arquivo credentials.json")
            except FileNotFoundError:
                pass
            except Exception as e:
                st.warning(f"⚠️ Erro ao ler credentials.json: {str(e)[:100]}")
        
        # 3. VERIFICAR SE TEM CREDENCIAIS
        if not credenciais_dict or not credenciais_dict.get('private_key'):
            st.error("❌ Credenciais não encontradas!")
            st.info("""
            **Para resolver:**
            - Coloque o arquivo `credentials.json` na mesma pasta do app.py
            """)
            return None
        
        # 4. CONECTAR
        creds = ServiceAccountCredentials.from_json_keyfile_dict(credenciais_dict, ESCOPOS)
        cliente = gspread.authorize(creds)
        
        # 5. TESTAR CONEXÃO
        try:
            test_planilha = cliente.open_by_key(ID_PLANILHA_CADASTRO)
            st.success(f"✅ Conectado à planilha: {test_planilha.title}")
            return cliente
        except Exception as e:
            st.error(f"❌ Erro ao acessar planilha: {str(e)}")
            st.info("Verifique se a planilha foi compartilhada com o e-mail da service account")
            return None
        
    except Exception as e:
        st.error(f"❌ Erro na conexão: {str(e)}")
        return None


def salvar_cadastro_cliente(dados_cliente):
    """Salva os dados do cliente na planilha Cadastro_Virtual (aba Cadastro)"""
    try:
        cliente = conectar_google_sheets()
        if not cliente:
            st.warning("⚠️ Não foi possível conectar. Cadastro NÃO salvo.")
            return False
        
        # Abrir a planilha
        planilha = cliente.open_by_key(ID_PLANILHA_CADASTRO)
        
        # Selecionar a aba Cadastro
        try:
            aba_cadastro = planilha.worksheet("Cadastro")
        except:
            # Se a aba não existir, criar
            aba_cadastro = planilha.add_worksheet(title="Cadastro", rows="1000", cols="20")
            cabecalho = ["RAZÃO SOCIAL", "CNPJ", "INSCRIÇÃO ESTADUAL", "ENDEREÇO", "E-MAIL", 
                        "NÚMERO", "BAIRRO", "CEP", "TEL/CONTATO", "UF", "DATA_CADASTRO", "HORA_CADASTRO"]
            aba_cadastro.append_row(cabecalho)
        
        # Limpar o CNPJ para busca (apenas números)
        cnpj_limpo = re.sub(r'[^0-9]', '', dados_cliente.get('cnpj', ''))
        
        # Buscar se CNPJ já existe
        todas_linhas = aba_cadastro.get_all_values()
        linha_encontrada = None
        
        for i, linha in enumerate(todas_linhas):
            if i == 0:  # Pular cabeçalho
                continue
            if len(linha) > 1:
                cnpj_linha = re.sub(r'[^0-9]', '', str(linha[1]))
                if cnpj_linha == cnpj_limpo:
                    linha_encontrada = i + 1  # +1 porque o índice 0 é linha 1
                    break
        
        data_atual = formatar_data_brasil().split()[0]
        hora_atual = formatar_data_brasil().split()[1]
        
        # Preparar dados para salvar
        nova_linha = [
            dados_cliente.get('razao_social', ''),
            dados_cliente.get('cnpj', ''),
            dados_cliente.get('inscricao_estadual', ''),
            dados_cliente.get('endereco', ''),
            dados_cliente.get('email', ''),
            dados_cliente.get('numero', ''),
            dados_cliente.get('bairro', ''),
            dados_cliente.get('cep', ''),
            dados_cliente.get('telefone', ''),
            dados_cliente.get('uf', ''),
            data_atual,
            hora_atual
        ]
        
        if linha_encontrada:
            # Atualizar linha existente
            for col, valor in enumerate(nova_linha, start=1):
                try:
                    aba_cadastro.update_cell(linha_encontrada, col, valor)
                except:
                    pass
            st.success(f"✅ Cadastro ATUALIZADO: {dados_cliente.get('razao_social', '')}")
        else:
            # Adicionar nova linha
            aba_cadastro.append_row(nova_linha)
            st.success(f"✅ Novo CADASTRO salvo: {dados_cliente.get('razao_social', '')}")
        
        return True
        
    except Exception as e:
        st.error(f"❌ Erro ao salvar cadastro: {str(e)}")
        import traceback
        st.error(f"Detalhes: {traceback.format_exc()}")
        return False


def salvar_historico_orcamento(dados_cliente, uf, valor_total, forma_pagamento, itens_resumo):
    """Salva o histórico do orçamento na planilha (aba Historico)"""
    try:
        cliente = conectar_google_sheets()
        if not cliente:
            st.warning("⚠️ Não foi possível conectar. Histórico NÃO salvo.")
            return False
        
        # Abrir a planilha
        planilha = cliente.open_by_key(ID_PLANILHA_CADASTRO)
        
        # Selecionar a aba Historico
        try:
            aba_historico = planilha.worksheet("Historico")
        except:
            # Se a aba não existir, criar
            aba_historico = planilha.add_worksheet(title="Historico", rows="10000", cols="20")
            cabecalho = ["DATA", "HORA", "CNPJ", "RAZÃO SOCIAL", "UF", "E-MAIL", "VALOR", 
                        "FORMA_PAGAMENTO", "QTD_ITENS", "TIPO_CLIENTE", "DATA_HORA_COMPLETA"]
            aba_historico.append_row(cabecalho)
        
        data_atual = formatar_data_brasil().split()[0]
        hora_atual = formatar_data_brasil().split()[1]
        data_hora_completa = formatar_data_brasil()
        
        # Contar quantidade de itens no carrinho
        qtd_itens = sum(item['quantidade'] for item in st.session_state.carrinho)
        
        tipo_cliente_str = "NÃO CONTRIBUINTE" if st.session_state.get('cliente_isento', False) else "NORMAL"
        
        nova_linha = [
            data_atual,
            hora_atual,
            dados_cliente.get('cnpj', ''),
            dados_cliente.get('razao_social', ''),
            uf,
            dados_cliente.get('email', ''),
            f"R$ {valor_total:,.2f}".replace('.', ','),
            forma_pagamento,
            qtd_itens,
            tipo_cliente_str,
            data_hora_completa
        ]
        
        aba_historico.append_row(nova_linha)
        st.success(f"✅ Histórico salvo! Orçamento registrado em {data_hora_completa}")
        return True
        
    except Exception as e:
        st.error(f"❌ Erro ao salvar histórico: {str(e)}")
        import traceback
        st.error(f"Detalhes: {traceback.format_exc()}")
        return False


def buscar_cadastro_por_cnpj(cnpj):
    """Busca cadastro do cliente pelo CNPJ na planilha"""
    try:
        cliente = conectar_google_sheets()
        if not cliente:
            return None
        
        planilha = cliente.open_by_key(ID_PLANILHA_CADASTRO)
        
        try:
            aba_cadastro = planilha.worksheet("Cadastro")
        except:
            return None
        
        # Limpar CNPJ para busca
        cnpj_limpo = re.sub(r'[^0-9]', '', cnpj)
        
        # Buscar em todas as linhas
        todas_linhas = aba_cadastro.get_all_values()
        
        for i, linha in enumerate(todas_linhas):
            if i == 0:  # Pular cabeçalho
                continue
            if len(linha) > 1:
                cnpj_linha = re.sub(r'[^0-9]', '', str(linha[1]))
                if cnpj_linha == cnpj_limpo:
                    return {
                        'razao_social': linha[0] if len(linha) > 0 else '',
                        'cnpj': linha[1] if len(linha) > 1 else '',
                        'inscricao_estadual': linha[2] if len(linha) > 2 else '',
                        'endereco': linha[3] if len(linha) > 3 else '',
                        'email': linha[4] if len(linha) > 4 else '',
                        'numero': linha[5] if len(linha) > 5 else '',
                        'bairro': linha[6] if len(linha) > 6 else '',
                        'cep': linha[7] if len(linha) > 7 else '',
                        'telefone': linha[8] if len(linha) > 8 else '',
                        'uf': linha[9] if len(linha) > 9 else ''
                    }
        return None
    except Exception as e:
        st.warning(f"⚠️ Erro ao buscar cadastro: {str(e)}")
        return None

# ============================================
# FUNÇÕES DE SEGURANÇA
# ============================================

def gerar_id_sessao() -> str:
    """Gera um ID de sessão único e seguro"""
    return secrets.token_hex(16)

def mascarar_dados_sensiveis(texto: str, tipo: str = 'email') -> str:
    """Mascara dados sensíveis para logs"""
    if not texto:
        return ''
    if tipo == 'email':
        partes = texto.split('@')
        if len(partes) == 2:
            return f"{partes[0][:3]}***@{partes[1]}"
    elif tipo == 'telefone':
        if len(texto) >= 10:
            return f"{texto[:2]}*****{texto[-3:]}"
    elif tipo == 'cnpj':
        if len(texto) >= 14:
            return f"{texto[:3]}***{texto[-3:]}"
    return '***'

def limpar_dados_sensiveis():
    """Limpa dados sensíveis do session_state após timeout"""
    if 'ultimo_acesso' in st.session_state:
        tempo_decorrido = (datetime.now() - st.session_state.ultimo_acesso).total_seconds()
        if tempo_decorrido > SESSION_TIMEOUT:
            # Limpar dados do cliente
            st.session_state.dados_cliente = {}
            st.session_state.form_data = {
                'razao_social': '',
                'cnpj': '',
                'inscricao_estadual': '',
                'email': '',
                'telefone': '',
                'endereco': '',
                'numero': '',
                'bairro': '',
                'cep': ''
            }
            st.session_state.carrinho = []
            st.warning("🔒 Sessão expirada por segurança. Seus dados foram removidos.")
            return True
    st.session_state.ultimo_acesso = datetime.now()
    return False

# ============================================
# FUNÇÃO PARA OBTER HORÁRIO LOCAL DO BRASIL
# ============================================
def get_horario_brasil():
    """Retorna a data e hora atual no fuso horário do Brasil"""
    return datetime.now(TIMEZONE_BR)

def formatar_data_brasil():
    """Formata a data e hora atual no padrão brasileiro"""
    agora = get_horario_brasil()
    return agora.strftime('%d/%m/%Y %H:%M:%S')

# ============================================
# FUNÇÃO PARA VALIDAR CNPJ
# ============================================
def validar_cnpj(cnpj):
    """Valida se o CNPJ é válido"""
    cnpj = re.sub(r'[^0-9]', '', str(cnpj))
    if len(cnpj) != 14:
        return False
    
    # Verificar se todos os dígitos são iguais
    if len(set(cnpj)) == 1:
        return False
    
    # Calcular primeiro dígito verificador
    peso1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma1 = sum(int(cnpj[i]) * peso1[i] for i in range(12))
    digito1 = 11 - (soma1 % 11)
    if digito1 >= 10:
        digito1 = 0
    
    # Calcular segundo dígito verificador
    peso2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma2 = sum(int(cnpj[i]) * peso2[i] for i in range(13))
    digito2 = 11 - (soma2 % 11)
    if digito2 >= 10:
        digito2 = 0
    
    return int(cnpj[12]) == digito1 and int(cnpj[13]) == digito2

# ============================================
# FUNÇÃO PARA VALIDAR EMAIL
# ============================================
def validar_email(email):
    """Valida se o email tem formato correto"""
    padrao = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(padrao, email) is not None

# ============================================
# FUNÇÃO PARA VALIDAR TELEFONE
# ============================================
def validar_telefone(telefone):
    """Valida se o telefone tem formato correto"""
    telefone = re.sub(r'[^0-9]', '', str(telefone))
    return len(telefone) >= 10 and len(telefone) <= 11

# ============================================
# FUNÇÃO PARA VALIDAR CEP
# ============================================
def validar_cep(cep):
    """Valida se o CEP tem formato correto"""
    cep = re.sub(r'[^0-9]', '', str(cep))
    return len(cep) == 8

# ============================================
# TELA DE VALIDAÇÃO INICIAL (PESSOA FÍSICA vs JURÍDICA)
# ============================================
def verificar_tipo_cliente_inicial():
    """Verifica se o usuário já selecionou o tipo de cliente"""
    
    # Carregar imagem de fundo
    img_fundo_base64 = ""
    try:
        with open("Frontpage.jpeg", "rb") as f:
            img_fundo_base64 = base64.b64encode(f.read()).decode()
    except:
        pass
    
    if img_fundo_base64:
        st.markdown(f"""
        <style>
        .stApp {{
            background: url('data:image/jpeg;base64,{img_fundo_base64}') no-repeat center center fixed;
            background-size: cover;
        }}
        .stApp::before {{
            content: '';
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(255, 255, 255, 0.88);
            z-index: 0;
            pointer-events: none;
        }}
        .main {{
            position: relative;
            z-index: 1;
        }}
        </style>
        """, unsafe_allow_html=True)
    
    st.markdown("""
    <div style='text-align: center; padding: 40px 20px;'>
        <h1 style='color: #2E7D32;'>Catálogo Interativo Virtual</h1>
        <p style='font-size: 18px; color: #555; margin-top: 10px;'>
        Peças exclusivas em vidro e decoração
        </p>
        <hr style='margin: 30px auto; width: 50%;'>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div style='max-width: 600px; margin: 0 auto; padding: 20px;'>
        <h3 style='color: #333; text-align: center;'>🔐 Identificação do Perfil</h3>
        <p style='text-align: center; color: #666; margin-bottom: 30px;'>
        Para acessar nosso catálogo, precisamos confirmar seu perfil de acordo com a LGPD.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("👤 Pessoa Física", use_container_width=True, type="primary"):
            st.session_state.tipo_pessoa = "FISICA"
            st.session_state.pessoa_fisica_recusada = True
            st.rerun()
    
    with col2:
        if st.button("🏢 Pessoa Jurídica", use_container_width=True, type="primary"):
            st.session_state.tipo_pessoa = "JURIDICA"
            st.session_state.aguardando_cnpj = True
            st.rerun()
    
    # Se for Pessoa Física, mostrar mensagem de bloqueio
    if st.session_state.get('pessoa_fisica_recusada', False):
        st.markdown("---")
        st.markdown("""
        <div style='background-color: #FFEBEE; border-left: 4px solid #D32F2F; 
                    padding: 20px; border-radius: 8px; margin-top: 20px;'>
            <h3 style='color: #D32F2F; margin-bottom: 15px;'>⛔ Acesso Restrito</h3>
            <p style='color: #333; font-size: 16px;'>
            <strong>Este catálogo é exclusivo para PESSOAS JURÍDICAS (CNPJ).</strong>
            </p>
            <p style='color: #555; margin-top: 15px;'>
            A LUVidarte atende exclusivamente empresas, revendedores e profissionais do setor.
            </p>
            <p style='color: #555; margin-top: 15px;'>
            Caso você seja uma pessoa física e tenha interesse em nossos produtos, 
            entre em contato conosco através dos canais abaixo:
            </p>
            <div style='margin-top: 20px; padding: 15px; background-color: #FFF; border-radius: 8px;'>
                <p>📞 <strong>Telefone:</strong> (11) 4676-9000</p>
                <p>💬 <strong>WhatsApp:</strong> (11) 93011-9335</p>
                <p>✉️ <strong>E-mail:</strong> sac@luvidarte.com.br</p>
                <p>📍 <strong>Endereço:</strong> Rua Caetano Rubio, 213 - Ferraz de Vasconcelos - SP</p>
            </div>
            <p style='color: #666; margin-top: 20px; font-size: 14px;'>
            Nossa equipe terá prazer em atendê-lo e apresentar nossas soluções personalizadas.
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("◀ Voltar e Selecionar Pessoa Jurídica", use_container_width=True):
            st.session_state.pessoa_fisica_recusada = False
            st.rerun()
        
        st.stop()
    
    # Se estiver aguardando CNPJ
    if st.session_state.get('aguardando_cnpj', False):
        st.markdown("---")
        st.markdown("""
        <div style='max-width: 600px; margin: 0 auto;'>
            <h3 style='color: #2E7D32; text-align: center;'>📋 Validação de Pessoa Jurídica</h3>
            <p style='text-align: center; color: #666; margin-bottom: 20px;'>
            Conforme a Lei Geral de Proteção de Dados (LGPD - Lei 13.709/2018), 
            solicitamos a confirmação do seu CNPJ para acesso ao catálogo.
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        with st.form(key="form_validacao_cnpj"):
            cnpj_input = st.text_input(
                "CNPJ da Empresa *",
                placeholder="99.999.999/9999-99",
                help="Digite apenas números ou utilize máscara"
            )
            
            st.caption("🔒 **LGPD - Proteção de Dados:**")
            st.caption("• Seu CNPJ será utilizado apenas para validação de acesso")
            st.caption("• Seus dados serão armazenados conforme consentimento LGPD")
            st.caption("• Você pode solicitar a exclusão dos seus dados a qualquer momento")
            st.caption("• DPO para questões LGPD: sac@luvidarte.com.br")
            
            # Botão para buscar cadastro existente
            if cnpj_input:
                cnpj_limpo = re.sub(r'[^0-9]', '', cnpj_input)
                if len(cnpj_limpo) == 14:
                    cadastro_existente = buscar_cadastro_por_cnpj(cnpj_limpo)
                    if cadastro_existente:
                        st.info("✅ CNPJ já cadastrado! Os dados serão carregados automaticamente.")
            
            col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])
            
            with col_btn2:
                enviar = st.form_submit_button("✅ Validar e Continuar", use_container_width=True)
            
            with col_btn1:
                if st.form_submit_button("◀ Voltar", use_container_width=True):
                    st.session_state.aguardando_cnpj = False
                    st.session_state.tipo_pessoa = None
                    st.rerun()
            
            if enviar:
                cnpj_limpo = re.sub(r'[^0-9]', '', cnpj_input)
                if len(cnpj_limpo) == 14 and validar_cnpj(cnpj_limpo):
                    st.session_state.cnpj_validado = cnpj_limpo
                    st.session_state.cnpj_validado_data = formatar_data_brasil()
                    st.session_state.acesso_autorizado = True
                    st.session_state.mostrar_lgpd = True
                    
                    # Buscar cadastro existente para pré-preencher
                    cadastro = buscar_cadastro_por_cnpj(cnpj_limpo)
                    if cadastro:
                        st.session_state.cadastro_precarregado = cadastro
                    else:
                        st.session_state.cadastro_precarregado = None
                    
                    st.rerun()
                else:
                    st.error("❌ CNPJ inválido. Verifique os dígitos e tente novamente.")
        
        st.stop()
    
    # Primeira vez, apenas mostrar tela inicial
    if 'acesso_autorizado' not in st.session_state:
        st.stop()
    
    return True

# ============================================
# PASSOS DO SISTEMA
# ============================================
def mostrar_passo_a_passo():
    """Exibe um tutorial passo a passo do sistema"""
    with st.sidebar.expander("📖 PASSO A PASSO - Como usar", expanded=False):
        st.markdown("""
        ### 🎯 Guia Rápido do Sistema - Catálogo Interativo Virtual
        
        ---
        
        #### 📌 **PASSO 1: Validação de CNPJ**
        - Informe seu CNPJ válido para acesso ao catálogo
        - Conforme LGPD, seus dados são tratados com confidencialidade
        - ⚠️ *Catálogo exclusivo para Pessoa Jurídica*
        
        ---
        
        #### 🔍 **PASSO 2: Configure os Filtros (Sidebar Esquerda)**
        - **📍 UF (ICMS):** Selecione o estado de entrega
        - **📦 Família de Produtos:** Escolha categoria do produto
        - **🔎 Buscar Referência:** Pesquise por código
        - **💰 Faixa de Preço:** Ajuste o slider
        - **🏷️ Cliente Não Contribuinte:** Marque se for Não Contribuinte
        - **💳 Pagamento:** Escolha a condição (Vista ou Prazo)
        
        ---
        
        #### 🛍️ **PASSO 3: Adicione Produtos**
        - Navegue pelos produtos na página principal
        - Defina a **quantidade** desejada
        - Clique em **"🛒 Adicionar"**
        
        ---
        
        #### 📊 **PASSO 4: Revise o Carrinho**
        - Clique em **"🛒 Acessar meu carrinho"**
        - Verifique os valores, quantidades e descontos
        
        ---
        
        #### 📝 **PASSO 5: Preencha os Dados do Cliente**
        - No carrinho, clique em **"📋 Solicitar Orçamento"**
        - Seus dados serão salvos na planilha de cadastro
        - Aceite os termos da LGPD
        
        ---
        
        #### 📤 **PASSO 6: Finalize o Orçamento**
        - Baixe o orçamento em HTML
        - Envie via WhatsApp
        - O histórico é salvo automaticamente
        
        ---
        
        #### 📞 **Suporte**
        - WhatsApp: (11) 93011-9335
        - E-mail: sac@luvidarte.com.br
        """)
        
        st.markdown("---")
        if st.button("✅ Já entendi, vamos começar!", use_container_width=True):
            st.session_state.passo_a_passo_visto = True
            st.rerun()

def mostrar_politica_privacidade():
    """Exibe a política de privacidade com imagem de fundo - VERSÃO LGPD COMPLETA"""
    
    # Carregar imagem para fundo da LGPD
    img_fundo_base64 = ""
    try:
        with open("Frontpage.jpeg", "rb") as f:
            img_fundo_base64 = base64.b64encode(f.read()).decode()
    except:
        pass
    
    # Adicionar fundo na tela LGPD
    if img_fundo_base64:
        st.markdown(f"""
        <style>
        .stApp {{
            background: url('data:image/jpeg;base64,{img_fundo_base64}') no-repeat center center fixed;
            background-size: cover;
        }}
        .stApp::before {{
            content: '';
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(255, 255, 255, 0.88);
            z-index: 0;
            pointer-events: none;
        }}
        .main {{
            position: relative;
            z-index: 1;
        }}
        </style>
        """, unsafe_allow_html=True)
    
    # Mostrar CNPJ validado
    if st.session_state.get('cnpj_validado'):
        cnpj_mascarado = f"{st.session_state.cnpj_validado[:3]}.***.***/****-{st.session_state.cnpj_validado[-2:]}"
        st.success(f"✅ CNPJ Validado: {cnpj_mascarado} | Data: {st.session_state.cnpj_validado_data}")
    
    with st.expander("📋 POLÍTICA DE PRIVACIDADE - LGPD (Lei 13.709/2018)", expanded=True):
        st.markdown("""
        ### 🔒 POLÍTICA DE PRIVACIDADE LUVidarte
        
        ---
        
        #### **1. QUAIS DADOS COLETAMOS E PARA QUE SERVEM?**
        
        | Dado Coletado | Finalidade Específica |
        |---------------|------------------------|
        | **Razão Social** | Identificação para emissão do orçamento e nota fiscal |
        | **CNPJ** | Obrigatório para emissão de nota fiscal (Lei 8.846/94) |
        | **Inscrição Estadual** | Necessário para cálculo correto de ICMS e ST |
        | **Endereço completo** | Calcular frete e verificar ICMS por UF |
        | **E-mail** | Enviar o orçamento e comunicar novidades (se autorizado) |
        | **Telefone/WhatsApp** | Contato comercial para finalizar o pedido |
        | **Histórico de orçamentos** | Agilizar futuras cotações e melhorar atendimento |
        
        ---
        
        #### **2. SEUS DIREITOS (Art. 18º da LGPD)**
        
        Você pode solicitar a qualquer momento, SEM CUSTO:
        - ✅ **Confirmar** se seus dados estão armazenados
        - ✅ **Acessar** todos os seus dados
        - ✅ **Corrigir** dados incompletos ou errados
        - ✅ **Excluir** seus dados (exceto quando lei exigir)
        - ✅ **Revogar** seu consentimento
        
        **📧 Canal exclusivo:** `lgpd@luvidarte.com.br`
        **Prazo de resposta:** Até 15 dias úteis
        
        ---
        
        #### **3. POR QUANTO TEMPO GUARDAMOS SEUS DADOS?**
        
        | Tipo de Dado | Prazo de Retenção |
        |--------------|-------------------|
        | Dados cadastrais | **2 anos** sem novo orçamento |
        | Histórico de orçamentos | **2 anos** |
        | Dados fiscais (CNPJ, IE) | **5 anos** (exigido pela Receita Federal) |
        
        ---
        
        #### **4. QUEM PODE VER SEUS DADOS?**
        
        Seus dados são acessíveis APENAS para:
        - 👥 Equipe comercial da LUVidarte
        - 👥 Equipe fiscal (para emissão de notas)
        - 🔒 Google (servidor criptografado)
        
        **NUNCA compartilhamos** com empresas de marketing ou terceiros.
        
        ---
        
        #### **5. ENCARREGADO (DPO)**
        
        | Canal | Contato |
        |-------|---------|
        | **E-mail** | `dpo@luvidarte.com.br` |
        | **Telefone** | (11) 4676-9000 |
        
        ---
        
        <div style='background-color: #E8F5E9; padding: 15px; border-radius: 8px; margin-top: 15px;'>
        <strong>✅ PARA ACEITAR ESTA POLÍTICA, VOCÊ CONCORDA QUE:</strong><br><br>
        • Leu e compreendeu todas as cláusulas acima<br>
        • Autoriza a coleta e armazenamento dos seus dados conforme descrito<br>
        • Conhece seus direitos de acesso, correção e exclusão<br><br>
        <small>Data da última atualização: 30/04/2026 - Versão 2.0 (LGPD)</small>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("✅ ACEITO E CONCORDO COM A POLÍTICA DE PRIVACIDADE", key="aceitar_privacidade", use_container_width=True):
            st.session_state.privacidade_aceita = True
            st.session_state.consentimento_data = formatar_data_brasil()
            st.session_state.mostrar_lgpd = False
            st.rerun()

def mostrar_termos_uso():
    """Exibe os termos de uso"""
    with st.expander("📜 Termos de Uso - Orçamento Virtual"):
        st.markdown("""
        ### TERMOS DE USO - CATÁLOGO INTERATIVO VIRTUAL LUVidarte
        
        **1. NATUREZA DO ORÇAMENTO**
        - Este é um ORÇAMENTO VIRTUAL, NÃO uma compra finalizada
        - Os valores são ESTIMATIVAS sujeitas à confirmação
        
        **2. ARMAZENAMENTO DE DADOS**
        - Seus dados serão armazenados para agilizar futuros atendimentos
        - O histórico de orçamentos é mantido para consulta
        
        **3. PÚBLICO-ALVO**
        - Este catálogo é exclusivo para PESSOAS JURÍDICAS
        
        **4. CANCELAMENTO DE DADOS**
        - Solicite a exclusão dos seus dados via e-mail: sac@luvidarte.com.br
        
        **5. DISPOSIÇÕES GERAIS**
        - A LUVidarte se reserva o direito de recusar pedidos
        
        ---
        📞 **Dúvidas:** (11) 4676-9000 | sac@luvidarte.com.br
        """)

# ============================================
# CONSENTIMENTO LGPD
# ============================================

def obter_consentimento_lgpd() -> bool:
    """Verifica se o usuário já consentiu com a LGPD"""
    
    if st.session_state.get('mostrar_lgpd', True) and 'privacidade_aceita' not in st.session_state:
        st.session_state.privacidade_aceita = False
    
    if not st.session_state.get('privacidade_aceita', False):
        mostrar_politica_privacidade()
        mostrar_termos_uso()
        return False
    
    # Após aceitar, restaurar o fundo normal
    img_fundo_base64 = ""
    try:
        with open("Frontpage.jpeg", "rb") as f:
            img_fundo_base64 = base64.b64encode(f.read()).decode()
    except:
        pass
    
    if img_fundo_base64:
        st.markdown(f"""
        <style>
        .stApp {{
            background: url('data:image/jpeg;base64,{img_fundo_base64}') no-repeat center center fixed;
            background-size: cover;
        }}
        .stApp::before {{
            content: '';
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(255, 255, 255, 0.88);
            z-index: 0;
            pointer-events: none;
        }}
        </style>
        """, unsafe_allow_html=True)
    
    return True

# ============================================
# FUNÇÃO PARA FORMATAR MOEDA (PADRÃO BRASILEIRO)
# ============================================
def formatar_moeda(valor):
    """Formata valor para moeda brasileira: R$ 49.984,56"""
    if valor is None or valor == 0:
        return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ============================================
# FUNÇÃO PARA CALCULAR DESCONTO POR VOLUME
# ============================================
def calcular_desconto_volume(valor_base):
    """Calcula o percentual de desconto por volume baseado no valor base"""
    if valor_base >= 4000:
        return 0.15
    elif valor_base >= 2500:
        return 0.10
    else:
        return 0.0

def calcular_faltante_para_desconto(valor_base):
    """Calcula o valor faltante para o próximo desconto"""
    if valor_base < 2500:
        return 2500 - valor_base, 10
    elif valor_base < 4000:
        return 4000 - valor_base, 15
    else:
        return 0, 0

def gerar_botao_desconto_flutuante():
    """Gera o HTML/CSS para o botão flutuante de desconto"""
    
    # Calcular valores atuais do carrinho
    if st.session_state.carrinho:
        valor_base_total = sum(item['preco_final'] * item['quantidade'] for item in st.session_state.carrinho)
        desconto_percentual = calcular_desconto_volume(valor_base_total)
        faltante, prox_desconto = calcular_faltante_para_desconto(valor_base_total)
        
        if desconto_percentual == 0.15:
            mensagem = f"🏆 PARABÉNS! Você atingiu 15% de desconto máximo!"
            cor = "#FF9800"
            icone = "🏆"
            texto_desconto = "15% OFF"
        elif desconto_percentual == 0.10:
            mensagem = f"✅ Você já tem 10% de desconto! Faltam {formatar_moeda(faltante)} para 15%"
            cor = "#4CAF50"
            icone = "🎯"
            texto_desconto = "10% OFF"
        else:
            if faltante > 0:
                mensagem = f"📈 Adicione mais {formatar_moeda(faltante)} e ganhe {prox_desconto}% de desconto!"
            else:
                mensagem = f"💰 Adicione produtos para ganhar desconto por volume!"
            cor = "#2196F3"
            icone = "📈"
            texto_desconto = "0% OFF"
        
        # Calcular barra de progresso
        if valor_base_total >= 4000:
            progresso = 100
        elif valor_base_total >= 2500:
            progresso = 75 + ((valor_base_total - 2500) / 1500) * 25
        else:
            progresso = (valor_base_total / 2500) * 75
        
        progresso = min(100, max(0, progresso))
        
    else:
        mensagem = "💰 Adicione produtos para ganhar desconto por volume!"
        faltante = 2500
        prox_desconto = 10
        cor = "#9E9E9E"
        icone = "💰"
        texto_desconto = "0% OFF"
        progresso = 0
    
    # HTML do botão flutuante
    html = f"""
    <style>
    @keyframes slideInRight {{
        from {{ transform: translateX(100%); opacity: 0; }}
        to {{ transform: translateX(0); opacity: 1; }}
    }}
    
    @keyframes pulse {{
        0% {{ transform: scale(1); }}
        50% {{ transform: scale(1.05); }}
        100% {{ transform: scale(1); }}
    }}
    
    .desconto-float {{
        position: fixed;
        bottom: 100px;
        right: 20px;
        z-index: 99999;
        animation: slideInRight 0.5s ease-out;
        cursor: pointer;
    }}
    
    .desconto-card {{
        background: linear-gradient(135deg, #FFF, #F5F5F5);
        border-radius: 16px;
        padding: 12px 18px;
        box-shadow: 0 8px 20px rgba(0,0,0,0.15);
        border-left: 4px solid {cor};
        min-width: 280px;
        max-width: 320px;
        transition: all 0.3s ease;
    }}
    
    .desconto-card:hover {{
        transform: translateY(-5px);
        box-shadow: 0 12px 28px rgba(0,0,0,0.2);
    }}
    
    .desconto-header {{
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 10px;
    }}
    
    .desconto-icon {{
        font-size: 28px;
        animation: pulse 2s infinite;
    }}
    
    .desconto-title {{
        font-size: 14px;
        font-weight: bold;
        color: #333;
        margin: 0;
    }}
    
    .desconto-message {{
        font-size: 12px;
        color: #555;
        margin: 8px 0;
        line-height: 1.4;
    }}
    
    .desconto-value {{
        font-size: 18px;
        font-weight: bold;
        color: {cor};
        margin: 5px 0;
    }}
    
    .progress-bar-container {{
        background-color: #E0E0E0;
        border-radius: 10px;
        height: 8px;
        margin: 10px 0;
        overflow: hidden;
    }}
    
    .progress-bar-fill {{
        background: linear-gradient(90deg, {cor}, #FF9800);
        width: {progresso}%;
        height: 100%;
        border-radius: 10px;
        transition: width 0.5s ease;
    }}
    
    .progress-labels {{
        display: flex;
        justify-content: space-between;
        font-size: 9px;
        color: #666;
        margin-top: 5px;
    }}
    
    .close-btn {{
        position: absolute;
        top: 5px;
        right: 10px;
        background: none;
        border: none;
        font-size: 16px;
        cursor: pointer;
        color: #999;
        transition: color 0.2s;
    }}
    
    .close-btn:hover {{
        color: #333;
    }}
    
    @media (max-width: 768px) {{
        .desconto-card {{
            min-width: 260px;
            padding: 10px 15px;
        }}
        .desconto-float {{
            bottom: 90px;
            right: 10px;
        }}
    }}
    </style>
    
    <div class="desconto-float" id="descontoFloat">
        <div class="desconto-card">
            <button class="close-btn" onclick="document.getElementById('descontoFloat').style.display='none'">✕</button>
            <div class="desconto-header">
                <div class="desconto-icon">{icone}</div>
                <div>
                    <div class="desconto-title">💎 DESCONTO POR VOLUME</div>
                    <div class="desconto-value">{texto_desconto}</div>
                </div>
            </div>
            <div class="desconto-message">{mensagem}</div>
            <div class="progress-bar-container">
                <div class="progress-bar-fill"></div>
            </div>
            <div class="progress-labels">
                <span>💰 R$ 0</span>
                <span>🎯 10% (R$ 2.500)</span>
                <span>🏆 15% (R$ 4.000)</span>
            </div>
        </div>
    </div>
    """
    
    return html

# ============================================
# FUNÇÃO PARA RECALCULAR ITEM COM DESCONTO POR VOLUME
# ============================================
def recalcular_item_com_desconto_volume(item, desconto_volume_percentual):
    """Aplica o desconto por volume no item e recalcula IPI e ST proporcionalmente"""
    # Valor base do item (preço final com desconto da condição de pagamento)
    valor_base_item = item['preco_final']
    
    # Aplicar desconto por volume no valor base
    valor_com_desconto_volume = valor_base_item * (1 - desconto_volume_percentual)
    
    # Recalcular IPI e ST proporcionalmente ao novo valor base
    # Manter a mesma alíquota efetiva
    novo_valor_ipi = valor_com_desconto_volume * item['ipi_percentual']
    novo_valor_st = valor_com_desconto_volume * item['st_aliquota']
    
    # Novo total do item
    novo_total_geral = valor_com_desconto_volume + novo_valor_ipi + novo_valor_st
    
    return {
        'preco_final_com_desconto': valor_com_desconto_volume,
        'valor_ipi': novo_valor_ipi,
        'valor_st': novo_valor_st,
        'total_geral': novo_total_geral
    }

# ============================================
# FUNÇÃO PARA GERAR HTML DO ORÇAMENTO
# ============================================
def gerar_html_orcamento(dados_cliente, itens_carrinho, uf, tipo_cliente, forma_pagamento, 
                         desconto_volume_percentual, valor_base_total, valor_desconto_volume,
                         total_final, total_ipi, total_st):
    """Gera um HTML com o orçamento detalhado"""
    
    novo_valor_base = valor_base_total - valor_desconto_volume
    
    # Calcular fator de proporcionalidade para IPI e ST
    if valor_base_total > 0:
        fator_ipi_st = novo_valor_base / valor_base_total
    else:
        fator_ipi_st = 0
    
    # Adicionar aviso de confidencialidade
    data_geracao = formatar_data_brasil()  # USAR HORÁRIO LOCAL BRASIL
    id_documento = hashlib.sha256(f"{dados_cliente.get('cnpj', '')}{data_geracao}".encode()).hexdigest()[:8]
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Orçamento LUVidarte - Confidencial</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .header {{ text-align: center; margin-bottom: 30px; }}
            .header h1 {{ color: #2E7D32; }}
            .section {{ margin-bottom: 20px; }}
            .section-title {{ color: #2E7D32; border-bottom: 2px solid #C9A03D; padding-bottom: 5px; }}
            table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #2E7D32; color: white; }}
            .total {{ font-weight: bold; font-size: 18px; color: #D32F2F; text-align: right; }}
            .footer {{ margin-top: 30px; font-size: 12px; text-align: center; color: #666; }}
            .lgpd-notice {{ background-color: #FFF9E6; border-left: 4px solid #C9A03D; 
                           padding: 10px; margin: 20px 0; font-size: 11px; }}
            .confidencial {{ background-color: #FFEBEE; border-left: 4px solid #D32F2F;
                           padding: 10px; margin: 20px 0; font-size: 11px; }}
            .alert-uf {{ background-color: #FFE0B2; border-left: 4px solid #FF9800;
                        padding: 10px; margin: 20px 0; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="confidencial">
            🔒 <strong>DOCUMENTO CONFIDENCIAL</strong> - ID: {id_documento}<br>
            Gerado em: {data_geracao}<br>
            Este orçamento contém informações comerciais privilegiadas. 
            O compartilhamento não autorizado é proibido nos termos da LGPD.
        </div>
        
        <div class="alert-uf">
            ⚠️ <strong>CONFIRMAÇÃO DE LOCALIDADE:</strong><br>
            Este orçamento foi calculado com base na UF <strong>{uf}</strong> (ICMS conforme legislação).<br>
            O endereço de entrega informado está de acordo com esta localidade.
        </div>
        
        <div class="header">
            <h1>LUVidarte - Catálogo Interativo Virtual</h1>
        </div>
        
        <div class="section">
            <h2 class="section-title">DADOS DO CLIENTE</h2>
            <p><strong>Razão Social:</strong> {dados_cliente.get('razao_social', '')}</p>
            <p><strong>CNPJ/CPF:</strong> {dados_cliente.get('cnpj', '')}</p>
            <p><strong>Inscrição Estadual:</strong> {dados_cliente.get('inscricao_estadual', '')}</p>
            <p><strong>E-mail:</strong> {dados_cliente.get('email', '')}</p>
            <p><strong>Telefone:</strong> {dados_cliente.get('telefone', '')}</p>
            <p><strong>Endereço:</strong> {dados_cliente.get('endereco', '')}, {dados_cliente.get('numero', '')}</p>
            <p><strong>Bairro:</strong> {dados_cliente.get('bairro', '')}</p>
            <p><strong>CEP:</strong> {dados_cliente.get('cep', '')}</p>
            <p><strong>UF (ICMS calculado):</strong> {uf}</p>
        </div>
        
        <div class="section">
            <h2 class="section-title">INFORMAÇÕES DO ORÇAMENTO</h2>
            <p><strong>Data de Geração:</strong> {data_geracao}</p>
            <p><strong>ID do Documento:</strong> {id_documento}</p>
            <p><strong>Tipo de Cliente:</strong> {tipo_cliente}</p>
            <p><strong>Condição de Pagamento:</strong> {forma_pagamento}</p>
            <p><strong>Validade do Orçamento:</strong> 7 dias corridos</p>
        </div>
        
        <div class="section">
            <h2 class="section-title">ITENS DO ORÇAMENTO</h2>
            <table>
                <thead>
                    <tr>
                        <th>Código</th>
                        <th>Descrição</th>
                        <th>Qtd</th>
                        <th>Valor Unit.</th>
                        <th>Subtotal</th>
                        <th>IPI</th>
                        <th>ST</th>
                        <th>Total</th>
                    </tr>
                </thead>
                <tbody>
    """
    
    total_ipi_exibido = 0
    total_st_exibido = 0
    total_geral_exibido = 0
    
    for item in itens_carrinho:
        # Valor base do item (já com desconto da condição de pagamento)
        valor_base_item = item['preco_final']
        
        # Aplicar desconto por volume no valor base do item
        valor_com_desconto_item = valor_base_item * (1 - desconto_volume_percentual)
        
        # Recalcular IPI e ST de cada item proporcionalmente
        aliquota_ipi_item = item['valor_ipi'] / valor_base_item if valor_base_item > 0 else 0
        aliquota_st_item = item['valor_st'] / valor_base_item if valor_base_item > 0 else 0
        
        # Aplicar as alíquotas sobre o novo valor base
        novo_ipi_unitario = valor_com_desconto_item * aliquota_ipi_item
        novo_st_unitario = valor_com_desconto_item * aliquota_st_item
        
        # Totais do item
        subtotal_item = valor_com_desconto_item * item['quantidade']
        ipi_total_item = novo_ipi_unitario * item['quantidade']
        st_total_item = novo_st_unitario * item['quantidade']
        total_item = (valor_com_desconto_item + novo_ipi_unitario + novo_st_unitario) * item['quantidade']
        
        # Acumular para verificação
        total_ipi_exibido += ipi_total_item
        total_st_exibido += st_total_item
        total_geral_exibido += total_item
        
        html_content += f"""
                    <tr>
                        <td>{item['referencia']}</td>
                        <td>{item['descricao'][:50]}</td>
                        <td style="text-align:center">{item['quantidade']}</td>
                        <td style="text-align:right">{formatar_moeda(valor_com_desconto_item)}</td>
                        <td style="text-align:right">{formatar_moeda(subtotal_item)}</td>
                        <td style="text-align:right">{formatar_moeda(ipi_total_item) if ipi_total_item > 0 else '-'}</td>
                        <td style="text-align:right">{formatar_moeda(st_total_item) if st_total_item > 0 else '-'}</td>
                        <td style="text-align:right">{formatar_moeda(total_item)}</td>
                    </tr>
        """
    
    html_content += f"""
                </tbody>
            </table>
        </div>
        
        <div class="section">
            <h2 class="section-title">RESUMO FINAL</h2>
            <p><strong>Valor Base Original:</strong> {formatar_moeda(valor_base_total)}</p>
            <p><strong>Desconto por Volume ({int(desconto_volume_percentual*100)}%):</strong> -{formatar_moeda(valor_desconto_volume)}</p>
            <p><strong>Novo Valor Base:</strong> {formatar_moeda(novo_valor_base)}</p>
            <p><strong>IPI Total:</strong> {formatar_moeda(total_ipi_exibido)}</p>
            <p><strong>ST Total:</strong> {formatar_moeda(total_st_exibido)}</p>
            <p class="total"><strong>TOTAL GERAL DO ORÇAMENTO:</strong> {formatar_moeda(total_geral_exibido)}</p>
        </div>
        
        <div class="lgpd-notice">
            🔒 <strong>LGPD - LEI GERAL DE PROTEÇÃO DE DADOS (Lei 13.709/2018)</strong><br><br>
            • Seus dados são tratados com confidencialidade e armazenados conforme consentimento<br>
            • Base legal: Execução de contrato e legítimo interesse (Art. 7º, V e IX)<br>
            • Você pode solicitar a exclusão dos seus dados a qualquer momento<br>
            • Este documento é de uso exclusivo da LUVidarte e do cliente<br><br>
            <strong>Seus direitos LGPD (Art. 18):</strong><br>
            • Acesso, correção e eliminação de dados<br>
            • Revogação do consentimento<br>
            • Portabilidade de dados<br><br>
            <strong>Encarregado (DPO):</strong> sac@luvidarte.com.br | (11) 4676-9000
        </div>
        
        <div class="footer">
            <p><strong>LUVidarte - Peças exclusivas em vidro e decoração</strong></p>
            <p>Rua Caetano Rubio, 213 - Ferraz de Vasconcelos - SP | CEP: 08533-060</p>
            <p>Tel: (11) 4676-9000 | WhatsApp: (11) 93011-9335 | E-mail: sac@luvidarte.com.br</p>
            <p>---</p>
            <p>⚠️ <strong>AVISO IMPORTANTE:</strong> Este é um ORÇAMENTO VIRTUAL, não uma compra finalizada.</p>
            <p>Os valores são estimativas e sujeitos à confirmação de estoque e disponibilidade.</p>
            <p>A venda será formalizada APENAS após contato e confirmação da nossa equipe via WhatsApp.</p>
            <p><strong>Validade do orçamento: 7 (sete) dias corridos.</strong></p>
            <p>---</p>
            <p>© 2026 LUVidarte - Todos os direitos reservados | Versão 1.0</p>
        </div>
    </body>
    </html>
    """
    
    return html_content.encode('utf-8')

# ============================================
# FUNÇÃO PARA FORMATAR MENSAGEM WHATSAPP
# ============================================
def formatar_mensagem_whatsapp(dados_cliente, uf, tipo_cliente, forma_pagamento, total_final,
                                desconto_volume_percentual, valor_desconto_volume, valor_base_total,
                                total_ipi, total_st):
    """Formata a mensagem para WhatsApp com resumo do orçamento e aviso LGPD"""
    
    msg = "🛍️ NOVO ORÇAMENTO LUVidarte 🛍️\n\n"
    msg += "━" * 30 + "\n\n"
    msg += "DADOS DO CLIENTE\n"
    msg += f"🏢 Razão Social: {dados_cliente.get('razao_social', '')}\n"
    msg += f"📄 CNPJ/CPF: {dados_cliente.get('cnpj', '')}\n"
    msg += f"🔢 IE: {dados_cliente.get('inscricao_estadual', '')}\n"
    msg += f"📧 E-mail: {dados_cliente.get('email', '')}\n"
    msg += f"📞 Telefone: {dados_cliente.get('telefone', '')}\n"
    msg += f"📍 Endereço: {dados_cliente.get('endereco', '')}, {dados_cliente.get('numero', '')}\n"
    msg += f"🏘️ Bairro: {dados_cliente.get('bairro', '')}\n"
    msg += f"📮 CEP: {dados_cliente.get('cep', '')}\n"
    msg += f"🗺️ UF (ICMS calculado): {uf}\n\n"
    msg += "━" * 30 + "\n\n"
    msg += "RESUMO DO ORÇAMENTO\n"
    msg += f"📅 Data: {formatar_data_brasil()}\n"
    msg += f"👤 Tipo Cliente: {tipo_cliente}\n"
    msg += f"💳 Pagamento: {forma_pagamento}\n"
    
    if desconto_volume_percentual > 0:
        novo_valor_base = valor_base_total - valor_desconto_volume
        msg += f"🎉 DESCONTO POR VOLUME: {int(desconto_volume_percentual*100)}%\n"
        msg += f"💰 Valor Base Original: {formatar_moeda(valor_base_total)}\n"
        msg += f"💰 Desconto: {formatar_moeda(valor_desconto_volume)}\n"
        msg += f"💰 Novo Valor Base: {formatar_moeda(novo_valor_base)}\n"
        msg += f"🔷 IPI Total: {formatar_moeda(total_ipi)}\n"
        msg += f"🟣 ST Total: {formatar_moeda(total_st)}\n\n"
    else:
        msg += "\n"
    
    # Lista resumida dos itens
    msg += "ITENS SOLICITADOS\n"
    for item in st.session_state.carrinho:
        # Mostrar preço com desconto por volume se aplicável
        valor_base_item = item['preco_final']
        valor_com_desconto = valor_base_item * (1 - desconto_volume_percentual)
        msg += f"• {item['quantidade']}x {item['descricao'][:50]}\n"
        msg += f"  REF: {item['referencia']} - Valor unit: {formatar_moeda(valor_com_desconto)}\n"
    
    msg += "\n━" * 30 + "\n\n"
    msg += f"💰 TOTAL DO ORÇAMENTO: {formatar_moeda(total_final)}\n\n"
    msg += "📋 Próximos passos:\n"
    msg += "1️⃣ Aguarde o contato da nossa equipe\n"
    msg += "2️⃣ Confirmaremos disponibilidade dos produtos\n"
    msg += "3️⃣ Enviaremos as condições de pagamento e frete\n\n"
    msg += "🔒 LGPD: Seus dados são tratados com confidencialidade conforme Lei 13.709/2018\n"
    msg += "📧 DPO: sac@luvidarte.com.br\n\n"
    msg += "✨ Agradecemos a preferência! ✨"
    
    return msg

# ============================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================

# PRIMEIRO: Verificar tipo de cliente (Pessoa Física vs Jurídica)
# Isso deve ser executado ANTES de qualquer outra validação
if 'acesso_autorizado' not in st.session_state:
    verificar_tipo_cliente_inicial()
    st.stop()

# Verificar consentimento LGPD depois de validar CNPJ
if not obter_consentimento_lgpd():
    st.stop()

# Restaurar padding normal após aceitar LGPD
st.markdown("""
<style>
.main {
    padding: 1rem !important;
}
.stApp > header {
    display: block !important;
}
</style>
""", unsafe_allow_html=True)

# Verificar timeout da sessão
limpar_dados_sensiveis()

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
        page_title="Luvidarte - Catálogo Interativo Virtual",
        page_icon=favicon,
        layout="wide"
    )
else:
    st.set_page_config(
        page_title="Luvidarte - Catálogo Interativo Virtual",
        page_icon="📦",
        layout="wide"
    )

# Mostrar CNPJ validado no topo
if st.session_state.get('cnpj_validado'):
    cnpj_mascarado = f"{st.session_state.cnpj_validado[:3]}.***.***/****-{st.session_state.cnpj_validado[-2:]}"
    st.sidebar.success(f"✅ CNPJ: {cnpj_mascarado}")

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
if 'dados_cliente' not in st.session_state:
    st.session_state.dados_cliente = {}
if 'mostrar_formulario_cliente' not in st.session_state:
    st.session_state.mostrar_formulario_cliente = False
if 'form_data' not in st.session_state:
    # Pré-preencher com dados do cadastro se existir
    if st.session_state.get('cadastro_precarregado'):
        st.session_state.form_data = st.session_state.cadastro_precarregado
    else:
        st.session_state.form_data = {
            'razao_social': '',
            'cnpj': st.session_state.get('cnpj_validado', ''),
            'inscricao_estadual': '',
            'email': '',
            'telefone': '',
            'endereco': '',
            'numero': '',
            'bairro': '',
            'cep': ''
        }
if 'mostrar_botoes_envio' not in st.session_state:
    st.session_state.mostrar_botoes_envio = False
if 'html_bytes' not in st.session_state:
    st.session_state.html_bytes = None
if 'ultimo_acesso' not in st.session_state:
    st.session_state.ultimo_acesso = datetime.now()
if 'consentimento_data' not in st.session_state:
    st.session_state.consentimento_data = None
if 'passo_a_passo_visto' not in st.session_state:
    st.session_state.passo_a_passo_visto = False
if 'cliente_isento' not in st.session_state:
    st.session_state.cliente_isento = False

# ============================================
# FUNÇÕES PARA CONTROLAR CARRINHO
# ============================================
def abrir_carrinho():
    st.session_state.carrinho_aberto = True
    st.rerun()

def fechar_carrinho():
    st.session_state.carrinho_aberto = False
    st.rerun()

def mostrar_formulario():
    st.session_state.mostrar_formulario_cliente = True
    st.rerun()

def cancelar_formulario():
    st.session_state.mostrar_formulario_cliente = False
    st.session_state.mostrar_botoes_envio = False
    st.session_state.html_bytes = None
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
    for item in st.session_state.carrinho:
        if item['referencia'] == produto['Referência']:
            item['quantidade'] += quantidade
            item['preco_total'] = item['preco_final'] * item['quantidade']
            item['ipi_total'] = item['valor_ipi'] * item['quantidade']
            item['st_total'] = item['valor_st'] * item['quantidade']
            item['total_geral'] = (item['preco_final'] + item['valor_ipi'] + item['valor_st']) * item['quantidade']
            return True
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
    st.session_state.mostrar_formulario_cliente = False
    st.session_state.mostrar_botoes_envio = False
    st.session_state.html_bytes = None

def calcular_resumo_carrinho():
    if not st.session_state.carrinho:
        return {'total_itens': 0, 'total_geral': 0.0, 'total_ipi': 0.0,
                'total_st': 0.0, 'total_desconto': 0.0, 'total_bruto': 0.0}
    
    # Calcular valor base total para desconto volume
    valor_base_total = sum(item['preco_final'] * item['quantidade'] for item in st.session_state.carrinho)
    desconto_vol = calcular_desconto_volume(valor_base_total)
    
    total_com_desconto = 0
    total_ipi = 0
    total_st = 0
    
    for item in st.session_state.carrinho:
        item_com_desconto = recalcular_item_com_desconto_volume(item, desconto_vol)
        total_com_desconto += item_com_desconto['total_geral'] * item['quantidade']
        total_ipi += item['valor_ipi'] * item['quantidade']  # IPI original
        total_st += item['valor_st'] * item['quantidade']    # ST original
    
    return {
        'total_itens': sum(i['quantidade'] for i in st.session_state.carrinho),
        'total_geral': total_com_desconto,
        'total_ipi': total_ipi,
        'total_st': total_st,
        'total_desconto': sum(i['valor_desconto'] * i['quantidade'] for i in st.session_state.carrinho),
        'total_bruto': sum(i['preco_bruto'] * i['quantidade'] for i in st.session_state.carrinho),
        'desconto_volume_percentual': desconto_vol,
        'valor_base_total': valor_base_total,
        'valor_desconto_volume': valor_base_total * desconto_vol,
        'novo_valor_base': valor_base_total * (1 - desconto_vol)
    }

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
# CSS GLOBAL COMPLETO COM IMAGEM DE FUNDO
# ============================================

# Função para carregar imagem de fundo
def carregar_imagem_fundo_base64():
    """Carrega a imagem Frontpage.jpeg e retorna em base64"""
    try:
        with open("Frontpage.jpeg", "rb") as f:
            return base64.b64encode(f.read()).decode()
    except FileNotFoundError:
        try:
            import os
            current_dir = os.path.dirname(os.path.abspath(__file__))
            file_path = os.path.join(current_dir, "Frontpage.jpeg")
            with open(file_path, "rb") as f:
                return base64.b64encode(f.read()).decode()
        except:
            return None

# Carregar imagem
img_fundo_base64 = carregar_imagem_fundo_base64()

# CSS Base (comum para ambos os casos)
css_base = """
* { margin: 0; padding: 0; box-sizing: border-box; }
.stDecoration { display: none; }
.stAppDeployButton { display: none !important; }
.main > div { padding-top: 0.5rem; }

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

.cart-link-top { text-align: right; }
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
.cart-link-button:hover { color: #1B5E20 !important; text-decoration: underline !important; }
.cart-link-badge {
    background: #D32F2F; color: white; border-radius: 50%;
    min-width: 20px; height: 20px; font-size: 11px;
    display: inline-flex; align-items: center; justify-content: center;
    font-weight: bold; padding: 0 4px;
}

.filtro-sidebar {
    font-weight: bold; font-size: 16px; padding: 10px;
    background: linear-gradient(135deg, #2E7D32, #1B5E20);
    color: white; border-radius: 8px; text-align: center; margin-bottom: 15px;
}

.whatsapp-float-fixed { position: fixed; bottom: 20px; right: 20px; z-index: 99990; }
.whatsapp-float {
    background-color: #25D366; color: white; border-radius: 50px;
    padding: 10px 18px; font-size: 13px; font-weight: bold;
    box-shadow: 0 4px 12px rgba(0,0,0,0.25); display: flex;
    align-items: center; gap: 8px; text-decoration: none; transition: all 0.3s ease;
}
.whatsapp-float:hover { transform: scale(1.05); background-color: #075E54; }

.formulario-cliente {
    background-color: #FFF; border-radius: 16px; padding: 25px;
    margin: 20px 0; box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    border: 1px solid #E0E0E0;
}
.formulario-titulo {
    color: #2E7D32; font-size: 20px; font-weight: bold;
    margin-bottom: 20px; border-bottom: 2px solid #C9A03D;
    display: inline-block; padding-bottom: 5px;
}
.campo-obrigatorio { color: #D32F2F; font-size: 12px; margin-left: 5px; }

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

.resumo-card {
    background-color: #FFF; border-radius: 12px; padding: 16px; margin: 10px 0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08); border: 1px solid #E0E0E0;
}
.resumo-title {
    font-size: 16px; font-weight: bold; color: #2E7D32;
    margin-bottom: 10px; border-bottom: 2px solid #C9A03D;
    display: inline-block; padding-bottom: 5px;
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

.social-links-container { text-align: center; margin: 15px 0; }
.social-title { color: #C9A03D; font-weight: bold; font-size: 14px; }
.social-links { display: flex; justify-content: center; gap: 25px; margin: 10px 0; flex-wrap: wrap; }
.social-link { text-decoration: none; font-size: 14px; font-weight: 500; padding: 5px 0; }
.contact-footer { text-align: center; font-size: 13px; color: #555; }
.footer-bottom {
    text-align: center; font-size: 12px; color: #666;
    padding: 15px 0; margin-top: 20px;
}
.horario-atendimento { text-align: center; margin: 10px 0; font-size: 13px; }
.horario-label { color: #C9A03D; font-weight: bold; }
.horario-text { color: #555; }

@media (max-width: 768px) {
    .whatsapp-float-fixed { bottom: 15px; right: 15px; }
    .cart-link-button { font-size: 12px !important; white-space: normal; }
}

.alert-uf-consistente {
    background-color: #FFF3E0; border-left: 4px solid #FF9800;
    border-radius: 8px; padding: 12px; margin: 10px 0; font-size: 13px;
}
.uf-bloqueada-info {
    background-color: #E8F5E9; border-left: 4px solid #4CAF50;
    border-radius: 8px; padding: 12px; margin: 10px 0;
    font-size: 13px; color: #2E7D32;
}
"""

# Aplicar CSS com ou sem imagem de fundo
if img_fundo_base64:
    css_fundo = f"""
    /* Imagem de fundo */
    .stApp {{
        background: url('data:image/jpeg;base64,{img_fundo_base64}') no-repeat center center fixed;
        background-size: cover;
    }}
    
    /* Overlay para legibilidade */
    .stApp::before {{
        content: '';
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(255, 255, 255, 0.88);
        z-index: 0;
        pointer-events: none;
    }}
    
    .main {{
        position: relative;
        z-index: 1;
    }}
    """
    st.markdown(f"<style>{css_fundo}{css_base}</style>", unsafe_allow_html=True)
else:
    css_sem_fundo = ".stApp { background-color: #F7F7F7; }"
    st.markdown(f"<style>{css_sem_fundo}{css_base}</style>", unsafe_allow_html=True)

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
            <h1>Catálogo Interativo Virtual</h1>
            <p>Peças exclusivas em vidro e decoração</p>
        </div>
        <div style='width:80px;'></div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div class='main-banner'>
        <div class='banner-text' style='width:100%;'>
            <h1>Catálogo Interativo Virtual</h1>
            <p>Peças exclusivas em vidro e decoração</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("""
<div class='legal-banner'>
    ⚠️ <strong>AVISO LEGAL:</strong> Este é um ORÇAMENTO VIRTUAL, não uma compra finalizada.
    Os valores são estimativas e sujeitos à confirmação de estoque e disponibilidade.
    A venda será formalizada APENAS após contato e confirmação da nossa equipe via WhatsApp.
    Conforme LGPD (Lei 13.709/2018), seus dados são tratados com confidencialidade.
</div>
""", unsafe_allow_html=True)


st.markdown("---")

# ============================================
# SIDEBAR COM TÍTULO "FILTROS"
# ============================================
st.sidebar.markdown('<div class="filtro-sidebar">🔍 FILTROS</div>', unsafe_allow_html=True)

# Adicionar botão "Passo a Passo" no topo do sidebar
if st.sidebar.button("📖 Ver Passo a Passo do Sistema", use_container_width=True):
    mostrar_passo_a_passo()

st.sidebar.markdown("---")

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
    st.error("""
    ❌ **Não foi possível carregar os produtos!**
    
    Verifique sua conexão com a internet e tente novamente.
    
    Se o problema persistir, entre em contato com nossa equipe:
    📞 (11) 4676-9000 | 💬 (11) 93011-9335
    """)
    
    if st.button("🔄 Tentar recarregar"):
        st.cache_data.clear()
        st.rerun()
    
    st.stop()

# ============================================
# FILTROS SIDEBAR
# ============================================
st.sidebar.subheader("📍 Localização e Tributos")

uf_selecionada = st.sidebar.selectbox(
    "UF (ICMS) - *Importante para cálculo dos tributos*",
    options=["SP","MG","RS","SE","PR","RJ","SC","MT","AC","AL","AP","AM",
             "BA","CE","DF","ES","GO","MA","MS","PA","PB","PE","PI","RN","RO","RR","TO"],
    index=0,
    help="Selecione o estado de entrega. O formulário usará automaticamente esta UF!"
)

st.sidebar.markdown("---")
st.sidebar.subheader("📦 Família de Produtos")

grupos = ["Todos"] + sorted(dados['GRUPO'].unique().tolist())
if "Promoção" not in grupos:
    grupos.insert(1, "Promoção")
grupo_escolhido = st.sidebar.selectbox("Família de Produtos", grupos)

st.sidebar.subheader("🔎 Busca")
busca_referencia = st.sidebar.text_input("Referência do Produto", placeholder="Ex: 510 P TR")

precos_validos = dados['Preço'].dropna()
if len(precos_validos) > 0:
    st.sidebar.subheader("💰 Faixa de Preço")
    faixa_preco = st.sidebar.slider(
        "Valores",
        min_value=float(precos_validos.min()),
        max_value=float(precos_validos.max()),
        value=(float(precos_validos.min()), float(precos_validos.max()))
    )
else:
    faixa_preco = (0, 1000)

st.sidebar.markdown("---")
st.sidebar.subheader("🏷️ Condições Comerciais")

cliente_isento  = st.sidebar.checkbox("Cliente Não Contribuinte", value=False, help="Marque se for Não Contribuinte (MEI/Isento)")
st.session_state.cliente_isento = cliente_isento
forma_pagamento = st.sidebar.radio("Condição de Pagamento",
                                   options=["PREÇO BASE","VISTA","30","45","60"], index=0)

# Monitorar mudanças nos filtros
filtros_atual = (uf_selecionada, cliente_isento, forma_pagamento)
if st.session_state.filtros_anteriores != filtros_atual:
    st.session_state.filtros_anteriores = filtros_atual
    if st.session_state.carrinho:
        recalcular_todo_carrinho(uf_selecionada, cliente_isento, forma_pagamento,
                                 dados_st, dados_promo, dados, dados_normal, dados_isento)
        st.rerun()

# ============================================
# TELA DO CARRINHO
# ============================================
if st.session_state.get('carrinho_aberto', False):

    st.markdown("# 🛒 Meu Orçamento Virtual")
    st.markdown("Revise os itens do seu orçamento antes de enviar.")

    if st.button("← Voltar aos produtos"):
        fechar_carrinho()

    if not st.session_state.carrinho:
        st.info("Seu orçamento está vazio. Adicione produtos para continuar.")
        st.stop()

    # Calcular valor base total (soma dos preços finais sem IPI/ST)
    valor_base_total = sum(item['preco_final'] * item['quantidade'] for item in st.session_state.carrinho)
    
    # Calcular desconto por volume sobre o valor base
    desconto_volume_percentual = calcular_desconto_volume(valor_base_total)
    valor_desconto_volume = valor_base_total * desconto_volume_percentual
    novo_valor_base = valor_base_total - valor_desconto_volume

    # Variáveis para totais
    total_ipi_recalculado = 0
    total_st_recalculado = 0
    total_geral_recalculado = 0
    total_desconto_geral = 0
    total_bruto_geral = 0

    for idx, item in enumerate(st.session_state.carrinho):
        # Recalcular IPI e ST proporcionalmente ao novo valor base
        ipi_aliquota_efetiva = item['valor_ipi'] / item['preco_final'] if item['preco_final'] > 0 else 0
        st_aliquota_efetiva = item['valor_st'] / item['preco_final'] if item['preco_final'] > 0 else 0
        
        valor_base_item_original = item['preco_final']
        valor_base_item_com_desconto = valor_base_item_original * (1 - desconto_volume_percentual)
        
        novo_ipi_item = valor_base_item_com_desconto * ipi_aliquota_efetiva
        novo_st_item = valor_base_item_com_desconto * st_aliquota_efetiva
        novo_total_item = (valor_base_item_com_desconto + novo_ipi_item + novo_st_item) * item['quantidade']
        
        total_ipi_recalculado += novo_ipi_item * item['quantidade']
        total_st_recalculado += novo_st_item * item['quantidade']
        total_geral_recalculado += novo_total_item
        total_desconto_geral += item['valor_desconto'] * item['quantidade']
        total_bruto_geral += item['preco_bruto'] * item['quantidade']
        
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
            st.markdown(f"*{item['descricao']}*")
            st.markdown(f"🔖 REF: {item['referencia']}")
            st.markdown(f"📦 Família: {item['grupo']}")
            if item.get('medidas'):
                st.markdown(f"📐 {item['medidas']}")
        with c3:
            st.markdown(f"💰 *Preço Bruto:* {formatar_moeda(item['preco_bruto'])}")
            if item['desconto_percentual'] > 0:
                st.markdown(f"🎯 *Desconto:* {item['desconto_percentual']*100:.2f}% ({formatar_moeda(item['valor_desconto'])})")
                st.markdown(f"📉 *Valor c/ Desconto:* {formatar_moeda(item['preco_com_desconto'])}")
            
            valor_unitario_exibido = valor_base_item_com_desconto
            st.markdown(f"💰 *Valor unitário:* {formatar_moeda(valor_unitario_exibido)}")
            if desconto_volume_percentual > 0:
                st.caption(f"🎉 *Inclui {int(desconto_volume_percentual*100)}% desconto por volume*")
            
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
                subtotal_item = valor_base_item_com_desconto * item['quantidade']
                st.markdown(f"💎 *Subtotal:* {formatar_moeda(subtotal_item)}")
            
            if item.get('ipi_percentual', 0) > 0:
                ipi_total_item = novo_ipi_item * item['quantidade']
                st.markdown(f"🔷 IPI: {item['ipi_percentual']*100:.2f}% = {formatar_moeda(ipi_total_item)}")
            
            if item.get('st_total', 0) > 0:
                st_total_item = novo_st_item * item['quantidade']
                st.markdown(f"🟣 ST: {formatar_moeda(st_total_item)}")
        with c4:
            st.markdown("*Total Item*")
            st.markdown(f"### {formatar_moeda(novo_total_item)}")
            if st.button("🗑️ Remover", key=f"remove_{idx}"):
                remover_do_carrinho(idx)
                st.rerun()
        st.markdown("---")

    total_final_com_vol = novo_valor_base + total_ipi_recalculado + total_st_recalculado

    if desconto_volume_percentual > 0:
        st.markdown(f"""
        <div class='desconto-vol-banner'>
            🎉 Parabéns! Você ganhou <strong>{int(desconto_volume_percentual*100)}% de desconto</strong> por volume!<br>
            Economia de <strong>{formatar_moeda(valor_desconto_volume)}</strong> aplicada sobre o valor base.<br>
            <small>IPI e ST recalculados proporcionalmente sobre o novo valor base.</small>
        </div>""", unsafe_allow_html=True)
    elif 2500 - valor_base_total > 0:
        st.markdown(f"""
        <div class='prox-desconto-hint'>
            💡 Adicione mais <strong>{formatar_moeda(2500-valor_base_total)}</strong> em valor base e ganhe <strong>10% de desconto</strong>!
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
                <span>📉 Valor com Desconto (base):</span>
                <span><strong>{formatar_moeda(total_bruto_geral - total_desconto_geral)}</strong></span>
            </div>
            <div class='resumo-line'>
                <span>📊 Valor Base (p/ desconto volume):</span>
                <span><strong>{formatar_moeda(valor_base_total)}</strong></span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class='resumo-card'>
            <div class='resumo-title'>🏷️ Tributos (Recalculados)</div>
            <div class='resumo-line'>
                <span>🔷 IPI Total Original:</span>
                <span><strong>{formatar_moeda(sum(item['valor_ipi'] * item['quantidade'] for item in st.session_state.carrinho))}</strong></span>
            </div>
            <div class='resumo-line'>
                <span>🔷 IPI Total (com desconto vol):</span>
                <span><strong style='color:#2E7D32;'>{formatar_moeda(total_ipi_recalculado)}</strong></span>
            </div>
            <div class='resumo-line'>
                <span>🟣 ST Total Original:</span>
                <span><strong>{formatar_moeda(sum(item['valor_st'] * item['quantidade'] for item in st.session_state.carrinho))}</strong></span>
            </div>
            <div class='resumo-line'>
                <span>🟣 ST Total (com desconto vol):</span>
                <span><strong style='color:#2E7D32;'>{formatar_moeda(total_st_recalculado)}</strong></span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown(f"""
    <div class='resumo-card'>
        <div class='resumo-title'>🎯 VALORES COM DESCONTO VOLUME</div>
        <div class='resumo-line' style='color:#2E7D32;'>
            <span>💰 Novo Valor Base (com {int(desconto_volume_percentual*100)}% OFF):</span>
            <span><strong>{formatar_moeda(novo_valor_base)}</strong></span>
        </div>
        <div class='resumo-line' style='color:#2E7D32;'>
            <span>🔷 IPI Total (recalculado):</span>
            <span><strong>{formatar_moeda(total_ipi_recalculado)}</strong></span>
        </div>
        <div class='resumo-line' style='color:#2E7D32;'>
            <span>🟣 ST Total (recalculado):</span>
            <span><strong>{formatar_moeda(total_st_recalculado)}</strong></span>
        </div>
        <div class='resumo-line total'>
            <span>✅ TOTAL FINAL DO ORÇAMENTO:</span>
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
        if st.button("📋 Solicitar Orçamento", use_container_width=True):
            mostrar_formulario()
    
    if st.session_state.mostrar_formulario_cliente and not st.session_state.mostrar_botoes_envio:
        st.markdown("---")
        st.markdown('<div class="formulario-cliente">', unsafe_allow_html=True)
        st.markdown('<div class="formulario-titulo">📝 Dados do Cliente</div>', unsafe_allow_html=True)
        st.markdown('<p style="color:#D32F2F; font-size:12px; margin-bottom:15px;">* Campos obrigatórios</p>', unsafe_allow_html=True)
        
        # INFORMAÇÃO DA UF BLOQUEADA
        st.markdown(f"""
        <div class='uf-bloqueada-info'>
            🔒 <strong>UF Bloqueada para Edição:</strong> A UF foi definida como <strong>{uf_selecionada}</strong> no filtro do sistema.<br>
            Este valor será usado automaticamente no cálculo dos tributos (ICMS/ST).<br>
            <small>Para alterar a UF, modifique no filtro da barra lateral esquerda.</small>
        </div>
        """, unsafe_allow_html=True)
        
        with st.form(key="form_cliente"):
            col1, col2 = st.columns(2)
            with col1:
                razao_social = st.text_input("Razão Social *", value=st.session_state.form_data.get('razao_social', ''))
                cnpj = st.text_input("CNPJ/CPF *", value=st.session_state.form_data.get('cnpj', st.session_state.get('cnpj_validado', '')), help="Digite apenas números")
                inscricao_estadual = st.text_input("Inscrição Estadual", value=st.session_state.form_data.get('inscricao_estadual', ''))
                email = st.text_input("E-mail *", value=st.session_state.form_data.get('email', ''))
                telefone = st.text_input("Telefone/Contato *", value=st.session_state.form_data.get('telefone', ''), help="Com DDD")
            
            with col2:
                endereco = st.text_input("Endereço *", value=st.session_state.form_data.get('endereco', ''))
                numero = st.text_input("Número *", value=st.session_state.form_data.get('numero', ''))
                bairro = st.text_input("Bairro *", value=st.session_state.form_data.get('bairro', ''))
                cep = st.text_input("CEP *", value=st.session_state.form_data.get('cep', ''), help="Digite apenas números")
                # Campo UF do cliente - DESABILITADO e com valor fixo do filtro
                uf_cliente = st.text_input("UF do Endereço *", value=uf_selecionada, disabled=True, 
                                          help="A UF é definida pelos filtros do sistema e não pode ser alterada aqui")
            
            enviar = st.form_submit_button("📤 Enviar Orçamento", use_container_width=True)
            
            if enviar:
                st.session_state.form_data = {
                    'razao_social': razao_social,
                    'cnpj': cnpj,
                    'inscricao_estadual': inscricao_estadual,
                    'email': email,
                    'telefone': telefone,
                    'endereco': endereco,
                    'numero': numero,
                    'bairro': bairro,
                    'cep': cep
                }
                
                erros = []
                if not razao_social:
                    erros.append("Razão Social")
                if not cnpj:
                    erros.append("CNPJ/CPF")
                elif not validar_cnpj(cnpj) and len(cnpj) != 11:
                    erros.append("CNPJ/CPF inválido")
                if not email:
                    erros.append("E-mail")
                elif not validar_email(email):
                    erros.append("E-mail inválido")
                if not telefone:
                    erros.append("Telefone")
                elif not validar_telefone(telefone):
                    erros.append("Telefone inválido")
                if not endereco:
                    erros.append("Endereço")
                if not numero:
                    erros.append("Número")
                if not bairro:
                    erros.append("Bairro")
                if not cep:
                    erros.append("CEP")
                elif not validar_cep(cep):
                    erros.append("CEP inválido")
                
                if erros:
                    st.error(f"❌ Por favor, corrija os seguintes erros:\n\n- " + "\n- ".join(erros))
                else:
                    dados_cliente = {
                        'razao_social': razao_social,
                        'cnpj': cnpj,
                        'inscricao_estadual': inscricao_estadual,
                        'email': email,
                        'telefone': telefone,
                        'endereco': endereco,
                        'numero': numero,
                        'bairro': bairro,
                        'cep': cep,
                        'uf': uf_selecionada
                    }
                    st.session_state.dados_cliente = dados_cliente
                    
                    # SALVAR CADASTRO NA PLANILHA
                    with st.spinner("💾 Salvando cadastro..."):
                        salvar_cadastro_cliente(dados_cliente)
                    
                    tipo_cliente_str = "NÃO CONTRIBUINTE" if cliente_isento else "NORMAL"
                    uf_para_calculo = uf_selecionada
                    
                    html_bytes = gerar_html_orcamento(dados_cliente, st.session_state.carrinho, 
                                                      uf_para_calculo, tipo_cliente_str, forma_pagamento,
                                                      desconto_volume_percentual, valor_base_total, valor_desconto_volume,
                                                      total_final_com_vol, total_ipi_recalculado, total_st_recalculado)
                    
                    if html_bytes:
                        st.session_state.html_bytes = html_bytes
                        st.session_state.mostrar_botoes_envio = True
                        
                        # SALVAR HISTÓRICO DO ORÇAMENTO
                        with st.spinner("💾 Salvando histórico..."):
                            salvar_historico_orcamento(dados_cliente, uf_selecionada, total_final_com_vol, 
                                                      forma_pagamento, st.session_state.carrinho)
                        
                        st.rerun()
                    else:
                        st.error("❌ Erro ao gerar o orçamento. Tente novamente.")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    if st.session_state.mostrar_botoes_envio and st.session_state.html_bytes:
        tipo_cliente_str = "NÃO CONTRIBUINTE" if cliente_isento else "NORMAL"
        
        msg_whatsapp = formatar_mensagem_whatsapp(st.session_state.dados_cliente, uf_selecionada, 
                                                   tipo_cliente_str, forma_pagamento, total_final_com_vol,
                                                   desconto_volume_percentual, valor_desconto_volume,
                                                   valor_base_total, total_ipi_recalculado, total_st_recalculado)
        msg_codificada = urllib.parse.quote(msg_whatsapp)
        link_whatsapp = f"https://wa.me/5511930119335?text={msg_codificada}"
        
        st.markdown("---")
        st.success("✅ Dados validados com sucesso! Orçamento gerado conforme LGPD.")
        st.info("💾 Cadastro e histórico salvos automaticamente na planilha!")
        
        col_html, col_wpp, col_voltar = st.columns([1, 1, 1])
        with col_html:
            st.download_button(
                label="📄 Baixar Orçamento (HTML)",
                data=st.session_state.html_bytes,
                file_name=f"orcamento_luvidarte_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
                mime="text/html",
                use_container_width=True
            )
        
        with col_wpp:
            st.markdown(f"""
            <a href="{link_whatsapp}" target="_blank" 
               style="background-color: #25D366; color: white; padding: 10px 20px; 
                      text-decoration: none; border-radius: 8px; font-weight: bold;
                      display: inline-flex; align-items: center; justify-content: center;
                      gap: 10px; width: 100%;">
                <span>💬</span> Enviar via WhatsApp
            </a>
            """, unsafe_allow_html=True)
        
        with col_voltar:
            if st.button("← Voltar ao carrinho", use_container_width=True):
                st.session_state.mostrar_botoes_envio = False
                st.session_state.mostrar_formulario_cliente = False
                st.rerun()
        
        st.caption("📎 *O orçamento completo está disponível para download. Conforme LGPD, seus dados são armazenados apenas para agilizar futuros atendimentos.*")

    st.stop()

# ============================================
# APLICAÇÃO DOS FILTROS
# ============================================
icms_uf         = determinar_icms_por_uf(uf_selecionada)
tabela_desconto = dados_isento if cliente_isento else dados_normal
tipo_cliente    = "NÃO CONTRIBUINTE" if cliente_isento else "NORMAL"

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
        total_fmt_header = formatar_moeda(resumo_header['total_geral'])
        
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
    st.info(f"🏢 *UF:* {uf_selecionada} (ICMS {icms_uf}%)")
with ci2:
    st.info(f"📋 *Cliente:* {tipo_cliente}")
with ci3:
    if forma_pagamento == "PREÇO BASE":
        st.warning(f"💰 *Condição:* {forma_pagamento}")
    else:
        st.success(f"💰 *Condição:* {forma_pagamento} dias")
with ci4:
    if grupo_escolhido == "Promoção":
        st.success(f"🏷️ *Família:* {grupo_escolhido} - Ofertas!")
    else:
        st.info(f"📦 *Família:* {grupo_escolhido}")

st.markdown("---")

# ============================================
# BOTÃO FLUTUANTE DE DESCONTO
# ============================================
st.markdown(gerar_botao_desconto_flutuante(), unsafe_allow_html=True)

# ============================================
# GRID DE PRODUTOS
# ============================================
if dados_filtrados.empty:
    st.warning("😕 Nenhum produto encontrado.")
else:
    desconto_volume_atual = 0
    valor_base_carrinho = 0
    if st.session_state.carrinho:
        valor_base_carrinho = sum(item['preco_final'] * item['quantidade'] for item in st.session_state.carrinho)
        desconto_volume_atual = calcular_desconto_volume(valor_base_carrinho)
    
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
            preco_final = preco_com_desconto

        ncm_produto = produto.get('NCM', '')
        ipi_percentual = buscar_ipi(ncm_produto, dados_st)
        valor_ipi = preco_final * ipi_percentual
        aliquota_st = buscar_aliquota_st(ncm_produto, uf_selecionada, dados_st)
        valor_st = 0.0 if cliente_isento else preco_final * aliquota_st
        valor_total = preco_final + valor_ipi + valor_st
        
        preco_com_desconto_volume = preco_final * (1 - desconto_volume_atual)

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

            img_url = str(produto.get('imagem_url', '')).strip()
            if img_url and pd.notna(produto.get('imagem_url')):
                try:
                    st.image(img_url, use_container_width=True)
                except:
                    st.image("https://via.placeholder.com/300x200?text=Sem+Imagem", use_container_width=True)
            else:
                st.image("https://via.placeholder.com/300x200?text=Sem+Imagem", use_container_width=True)

            ml_fmt = formatar_ml(produto.get('ml'))
            st.markdown(
                f'<div class="product-detail">📏 <strong>{ml_fmt if ml_fmt else "--"}</strong></div>',
                unsafe_allow_html=True
            )

            med = produto.get('Medidas', '')
            if pd.notna(med) and str(med).strip():
                st.markdown(f'<div class="product-detail">📐 {med}</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="product-detail">📐 <strong>--</strong></div>', unsafe_allow_html=True)

            if desconto_volume_atual > 0:
                st.markdown(f"💰 *Preço Bruto:* {formatar_moeda(preco_bruto)}")
                if desconto_percentual > 0:
                    st.markdown(f"🎯 *Desconto:* {desconto_percentual*100:.2f}% ({formatar_moeda(valor_desconto)})")
                    st.markdown(f"📉 *Valor c/ Desconto:* {formatar_moeda(preco_com_desconto)}")
                st.markdown(f"💰 *Valor unitário:* {formatar_moeda(preco_com_desconto_volume)}")
                st.caption(f"🎉 *Inclui {int(desconto_volume_atual*100)}% desconto por volume acumulado no carrinho*")
            else:
                st.markdown(f"💰 *Preço Bruto:* {formatar_moeda(preco_bruto)}")
                if desconto_percentual > 0:
                    st.markdown(f"🎯 *Desconto:* {desconto_percentual*100:.2f}% ({formatar_moeda(valor_desconto)})")
                    st.markdown(f"📉 *Valor c/ Desconto:* {formatar_moeda(preco_com_desconto)}")
                st.markdown(f"💰 *Valor unitário:* {formatar_moeda(preco_final)}")
            
            if ipi_percentual > 0:
                st.markdown(f"🔷 *IPI:* {ipi_percentual*100:.2f}% = {formatar_moeda(valor_ipi)}")
            else:
                st.markdown("🔷 *IPI:* Não aplicável")
            
            if cliente_isento:
                st.markdown(f"🟣 *ST ({uf_selecionada}):* Cliente Não Contribuinte — ST não aplicada")
                if desconto_volume_atual > 0:
                    novo_total_com_desconto = preco_com_desconto_volume + valor_ipi
                    st.markdown(f"✅ *TOTAL COM IPI:* {formatar_moeda(novo_total_com_desconto)}")
                else:
                    st.markdown(f"✅ *TOTAL COM IPI:* {formatar_moeda(preco_final + valor_ipi)}")
            elif aliquota_st > 0:
                st.markdown(f"🟣 *Alíq. ST ({uf_selecionada}):* {aliquota_st*100:.2f}%")
                if desconto_volume_atual > 0:
                    novo_total_com_desconto = preco_com_desconto_volume + valor_ipi + valor_st
                    st.markdown(f"📊 *Valor ST:* {formatar_moeda(valor_st)}")
                    st.markdown(f"✅ *TOTAL COM IPI + ST:* {formatar_moeda(novo_total_com_desconto)}")
                else:
                    st.markdown(f"📊 *Valor ST:* {formatar_moeda(valor_st)}")
                    st.markdown(f"✅ *TOTAL COM IPI + ST:* {formatar_moeda(valor_total)}")
            else:
                st.markdown(f"🟣 *ST ({uf_selecionada}):* Não aplicável")
                if desconto_volume_atual > 0:
                    novo_total_com_desconto = preco_com_desconto_volume + valor_ipi
                    st.markdown(f"✅ *TOTAL COM IPI:* {formatar_moeda(novo_total_com_desconto)}")
                else:
                    st.markdown(f"✅ *TOTAL COM IPI:* {formatar_moeda(preco_final + valor_ipi)}")

            st.markdown("---")

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
    📞 (11) 4676-9000 | 💬 (11) 93011-9335 | ✉️ sac@luvidarte.com.br | 🔒 DPO: dpo@luvidarte.com.br | 🔒 LGPD: lgpd@luvidarte.com.br
</div>""", unsafe_allow_html=True)

# NOVA SEÇÃO DE DIREITOS LGPD
st.markdown("""
<div style='text-align: center; padding: 15px; margin-top: 10px; border-top: 1px solid #ddd;'>
    <p style='font-size: 12px; color: #666;'>
        🔒 <strong>LGPD - Lei 13.709/2018</strong><br>
        Seus direitos: <strong>acesso, correção, exclusão e portabilidade</strong> dos dados<br>
        📧 Solicitações: <strong>lgpd@luvidarte.com.br</strong> | DPO: <strong>dpo@luvidarte.com.br</strong><br>
        ⏱️ Prazo de resposta: <strong>15 dias úteis</strong>
    </p>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class='footer-bottom'>
    © 2026 Luvidarte - Catálogo Interativo Virtual |
    <em>Os valores são estimativos e sujeitos à confirmação</em><br>
    <small>Conforme LGPD (Lei 13.709/2018), seus dados são tratados com confidencialidade e armazenados apenas para agilizar futuros atendimentos.</small>
</div>
""", unsafe_allow_html=True)

def mostrar_direitos_lgpd_rodape():
    st.markdown("""
    <div style='text-align: center; padding: 15px; margin-top: 20px; border-top: 1px solid #ddd;'>
        <p style='font-size: 12px; color: #666;'>
            🔒 <strong>LGPD - Lei 13.709/2018</strong><br>
            Seus direitos: <strong>acesso, correção, exclusão e portabilidade</strong> dos dados<br>
            📧 Solicitações: <strong>lgpd@luvidarte.com.br</strong> | DPO: <strong>dpo@luvidarte.com.br</strong><br>
            ⏱️ Prazo de resposta: <strong>15 dias úteis</strong>
        </p>
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
