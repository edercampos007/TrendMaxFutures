# =======================================================================================
# TrendMax-Futures
# NÃO REMOVER NENHUM IMPORT
# MANTER A ORIGINALIDADE INTACTA
# NÃO ALTERAR O CODIGO SEM PERMISÃO
# NÃO REMOVER COMENTÁRIOS E DOCUMENTAÇÃO (SEMPRE ATUALIZA-LOS E ACRESCENTAR ONDE NÃO TEM)
import json  # Manipulação de JSON
import logging  # Para gerenciamento de logs
import os  # Funções do sistema operacional
import sys  # Informações e funções do sistema
import threading  # Execução de threads para operações paralelas
import time  # Funções relacionadas a tempo
import tkinter.messagebox as messagebox  # Exibição de mensagens em janelas de diálogo (Tkinter)
import uuid  # Geração de identificadores únicos
import webbrowser  # Abrir URLs no navegador padrão
import winreg  # Manipulação do registro do Windows
from datetime import (datetime,  # Trabalhar com data/hora e fusos horários
                      timezone)
from email.utils import \
    parsedate_to_datetime  # Converter datas de e-mail para objetos datetime

import joblib
import requests  # Requisições HTTP
from colorama import Fore, Style, init  # Colorir a linhas dos logs
from indicators import calculate_adx  # Average Directional Index
from indicators import calculate_atr  # Average True Range
from indicators import calculate_jma  # Jurik Moving Average
from indicators import calculate_macd  # Moving Average Convergence Divergence
from indicators import calculate_rsi  # Relative Strength Index
from orderbook_utils import get_aggressive_volume  # Aggressive volume analysis
from orderbook_utils import (get_order_book, get_order_book_metrics,
                             get_total_volume)
from packaging import version  # Comparação de versões
from requests.auth import \
    HTTPBasicAuth  # Autenticação básica para requisições HTTP
# Para o treino inline
from xgboost import XGBClassifier

init(autoreset=True)

# lista global para todos os WebSocketApp criados
ws_apps: list = []

STOP_MSG = "Operação Encerrada!"


import re  # Módulo de expressões regulares
import tkinter as tk  # Para Irterface de busca de logs

import ccxt  # Integração com corretoras de criptomoedas
# =======================================================================================
# Importação de módulos para interface gráfica customizada e para a lógica de trading
import customtkinter as ctk  # Interface gráfica customizada
import numpy as np  # Operações numéricas
import pandas as pd  # Manipulação de dados (DataFrames)
import websocket  # Comunicação via WebSocket com a Binance
from binance.error import ClientError  # Tratamento de erros da Binance
from binance.lib.utils import \
    config_logging  # Configuração de logging para Binance
from binance.um_futures import \
    UMFutures  # Cliente para operar na Binance Futures (USDT-margem)
# ============================================================================
# ----------------- Import do pipeline de Machine Learning -------------------
from ml_pipeline import compute_features, fetch_historical_data, load_model
from train_model import \
    train_and_save  # Rotina de treino do Machine Learning (Pipeline e Train)

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")


def get_model_path(symbol):
    """
    Recebe 'BTC/USDT' e retorna
    '<caminho_para_pasta>/models/xgb_btcusdt_model.pkl'.
    """
    fname = f"xgb_{symbol.replace('/', '').lower()}_model.pkl"
    return os.path.join(MODELS_DIR, fname)


# ============================================================================
# ----------------------------- Variáveis Globais ----------------------------
live_price = None
last_roi = None  # Armazena o ROI calculado quando a posição está aberta
current_candle_main = None  # Candle do TIMEFRAME OPERACIONAL (WebSocket)
current_candle_conf = None  # Candle do TIMEFRAME DE CONFIRMAÇÃO (WebSocket)
current_candle_comp = None  # Candle do TIMEFRAME DE COMPARAÇÃO (WebSocket)
TELEGRAM_BOT_TOKEN = "7788593279:AAGinIYHEBUOXJEMpjDdqQ0VccoenPxrtwk"
TELEGRAM_ENABLED = True  # Checar se o recurso está habilitado
NOVOS_SINAIS_ENABLED = True  # Checar se o recurso está habilitado
REPOSICAO_ENABLED = True  # Checar se o recurso está habilitado

ws_new_candle_event = threading.Event()

# Mensagens personalizadas das formas de fechamentos de posição
DEFAULT_FECHAMENTO_MSG = {
    "roi_stop_loss": "Stop Loss: {symbol} fechado a {price:.4f} | Ordem ID: {order_id}",
    "roi_stop_win": "Stop Win: {symbol} fechado a {price:.4f} | Ordem ID: {order_id}",
    "barreira": "Barreira: {symbol} fechado a {price:.4f} | Ordem ID: {order_id}",
    "rsi_reversao": "RSI de Reversão: {symbol} fechado a {price:.4f} | Ordem ID: {order_id}",
    "reversao": "Reversão de Sinal: {symbol} fechado a {price:.4f} | Ordem ID: {order_id}",
    "manual": "Fechamento Manual Executado: {symbol} | Ordem ID: {order_id}",
}


# Zerar contadores ao iniciar antes de adotar a posição se caso existir
def reset_contadores():
    global last_position_qty, last_order_qty, last_entry_price
    global active_stop_gain_data, last_order_time, reposicao_count
    global signal_count, first_entry_done

    last_position_qty = None
    last_order_qty = None
    last_entry_price = None
    active_stop_gain_data = None
    last_order_time = 0
    reposicao_count = 0
    signal_count = 0
    first_entry_done = False
    logging.info("Contadores zerados.")


# ============================================================================
# Variáveis para informações de trading
last_entry_price = None
last_order_qty = None
last_position_qty = None
config_leverage = None
last_pnl = None
last_protected_qty = None
last_order_time = 0  # Intervalo mínimo entre ordens (em segundos)

# ============================================================================
# ------------------ Variáveis para proteção e integração --------------------
active_stop_gain_data = None
order_closed_notified = False


# ============================================================================
# ---------------------- Função para validar a posição -----------------------
def posicao_valida(pos, target):
    return (
        pos.get("symbol", "").upper() == target
        and float(pos.get("positionAmt", 0)) != 0
    )


# ============================================================================
# ------------------- Funções de Integração com o Telegram -------------------
def get_Telegram_Config_Futures_path():
    if getattr(sys, "frozen", False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(__file__)
    return os.path.join(base_path, "Telegram_Config_Futures.json")


def load_Telegram_Config_Futures():
    config_path = get_Telegram_Config_Futures_path()
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
                logging.info(
                    f"Telegram config carregado: chat_id={config.get('chat_id','')}"
                )
                return config
        except Exception as e:
            logging.exception(
                "Erro ao carregar configurações do Telegram: %s",
                e,
            )
    else:
        logging.info("ChatID não cadastrado")
    return {}


def send_telegram_message(message):
    if not TELEGRAM_ENABLED:
        return
    config = load_Telegram_Config_Futures()
    chat_id = config.get("chat_id", "")
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            logging.info("Mensagem Telegram enviada com sucesso.")
        else:
            logging.error(
                "Falha ao enviar mensagem Telegram. Resposta: %s", response.text
            )
    except Exception as e:
        logging.exception(
            "Erro ao enviar mensagem Telegram: %s",
            e,
        )


# ============================================================================
# ------------------- Função de Verificação de Nova Versão -------------------
LOCAL_VERSION = "1.0.0"


def check_for_new_version():
    try:
        response = requests.get(
            "https://api.trendmax.space/versao",
            auth=HTTPBasicAuth(USER_API, SENHA_API),
            timeout=5,
        )
        if response.status_code == 200:
            data = response.json()
            versao = data.get("versao")
            if versao and version.parse(versao) > version.parse(LOCAL_VERSION):
                return True, versao
        return False, LOCAL_VERSION
    except Exception as e:
        logging.exception(
            "Erro ao verificar versão: %s",
            e,
        )
        return False, LOCAL_VERSION


# ============================================================================
# ---------------------------- Backend de Licença ----------------------------
USER_API = "22trend09"
SENHA_API = "224589634788f9"
REG_CAMINHO = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Futures"
REG_NOME = "codigo_unico"


def obter_codigo_licenca():
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REG_CAMINHO, 0, winreg.KEY_READ
        ) as chave:
            codigo_unico, _ = winreg.QueryValueEx(chave, REG_NOME)
            if codigo_unico:
                return codigo_unico
    except FileNotFoundError:
        logging.warning("Código único não encontrado. Criando um novo...")
    novo_codigo = str(uuid.uuid4())
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_CAMINHO) as chave:
            winreg.SetValueEx(chave, REG_NOME, 0, winreg.REG_SZ, novo_codigo)
            logging.info("Novo código único gerado e salvo.")
    except Exception as e:
        logging.exception(
            "Erro ao criar código único: %s",
            e,
        )
        return None
    enviar_serv(novo_codigo)
    return novo_codigo


def enviar_serv(novo_codigo):
    API = "http://api.trendmax.space/cadastrar"
    data = {
        "codigo_unico": novo_codigo,
        "data_pagamento": None,
        "data_vencimento": None,
        "status": "inativo",
        "ip": "",
        "heartbeat": "",
    }
    try:
        response = requests.post(
            API, json=data, auth=HTTPBasicAuth(USER_API, SENHA_API)
        )
        if response.status_code == 201:
            logging.info("Código registrado com sucesso!")
        else:
            logging.error("Erro ao registrar código: %s", response.text)
    except Exception as e:
        logging.exception(
            "Erro de comunicação com o servidor: %s",
            e,
        )


def send_heartbeat(codigo_unico, current_ip):
    api_url = "https://api.trendmax.space/licencas/heartbeat"
    payload = {
        "codigo_unico": codigo_unico,
        "ip": current_ip,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        response = requests.post(
            api_url, json=payload, auth=HTTPBasicAuth(USER_API, SENHA_API), timeout=5
        )
        if response.status_code == 200:
            logging.info("Heartbeat enviado com sucesso para o IP: %s", current_ip)
        else:
            logging.error("Falha ao enviar heartbeat. Resposta: %s", response.text)
    except Exception as e:
        logging.exception(
            "Erro ao enviar heartbeat: %s",
            e,
        )


def get_public_ip():
    try:
        response = requests.get("https://api.ipify.org?format=json", timeout=5)
        if response.status_code == 200:
            return response.json().get("ip", None)
    except Exception as e:
        logging.exception(
            "Erro ao obter IP público: %s",
            e,
        )
    return None


def license_monitor(stop_event, status_callback, shutdown_callback, log_callback):
    license_check_interval = 900  # 15 minutos
    while not stop_event.is_set():
        time.sleep(license_check_interval)  # Usa o intervalo definido na variável
        current_validade = conexao_licenca()
        if current_validade != "Ativa":
            if log_callback:
                log_callback("Licença Expirada. Encerrando operação (monitor).")
            if status_callback:
                status_callback("Licença Expirada. Robo desligado (monitor).")
            if shutdown_callback:
                shutdown_callback("Licença Expirada. Robo desligado (monitor).")
            stop_event.set()
            break


def heartbeat_loop(codigo_unico, heartbeat_interval, stop_event):
    current_ip = get_public_ip()
    if current_ip is None:
        logging.error("Heartbeat: Não foi possível obter o IP público.")
        return
    logging.info("Heartbeat: IP público atual: %s", current_ip)
    while not stop_event.is_set():
        send_heartbeat(codigo_unico, current_ip)
        time.sleep(heartbeat_interval)


def conexao_licenca():
    api_url = "https://api.trendmax.space/licencas"
    try:
        response = requests.get(
            api_url, auth=HTTPBasicAuth(USER_API, SENHA_API), timeout=5
        )
        if response.status_code != 200:
            logging.error("Erro na conexão com API. Código: %s", response.status_code)
            return None
    except Exception as e:
        logging.exception(
            "API inacessível: %s",
            e,
        )
        return None
    time.sleep(0.1)  # Delay de 100 milissegundos para permitir processamentos
    codigo_unico = obter_codigo_licenca()
    if codigo_unico is None:
        logging.error("Licença não registrada.")
        return "Licença não Existente"
    try:
        licencas = response.json()
        licenca = next(
            (item for item in licencas if item["codigo_unico"] == codigo_unico), None
        )
        if not licenca:
            logging.error("Licença não encontrada na API.")
            return "Licença não Existente"
        status = licenca.get("status", "desconhecido").lower()
        data_vencimento = licenca.get("data_vencimento", None)
        if status == "ativo":
            if data_vencimento:
                vencimento = parsedate_to_datetime(data_vencimento)
                now = datetime.now(timezone.utc)
                dias_restantes = (vencimento - now).days
                logging.info(
                    "Licença ATIVA - Data de vencimento: %s - Dias restantes: %d",
                    vencimento.strftime("%a, %d %b %Y %H:%M GMT"),
                    dias_restantes,
                )
            return "Ativa"
        else:
            logging.error("Licença EXPIRADA")
            send_telegram_message("Licença EXPIRADA: Por favor verifique sua licença.")
            return "Expirada"
    except Exception as e:
        logging.exception(
            "Erro ao processar resposta da API: %s",
            e,
        )
        return None


def conexaoAPI():
    api_url = "https://api.trendmax.space/licencas"
    try:
        response = requests.get(
            api_url, auth=HTTPBasicAuth(USER_API, SENHA_API), timeout=5
        )
        if response.status_code == 200:
            logging.info("Conexao com API: OK")
        else:
            logging.error("Erro na conexao com API. Codigo: %s", response.status_code)
            return None
    except Exception as e:
        logging.exception(
            "API inacessível: %s",
            e,
        )
        return None
    time.sleep(0.1)  # Delay de 100 milissegundos para permitir processamentos
    return response.json()


# ============================================================================
# ------------------------------ Outras funções ------------------------------
RETRY_ATTEMPTS = 3
RETRY_DELAY = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S - ",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("Robo_Trading_Futures.log", encoding="utf-8"),
    ],
)

DEFAULT_FONT = ("Arial", 12)
SMALL_FONT = ("Arial", 12)


def get_credentials_path():
    if getattr(sys, "frozen", False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(__file__)
    return os.path.join(base_path, "Credentials_Futures.json")


def retry_operation(func, *args, retries=None, delay=None, **kwargs):
    if retries is None:
        retries = RETRY_ATTEMPTS
    if delay is None:
        delay = RETRY_DELAY

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_error = e
            # Só a mensagem, sem traceback
            logging.error(f"Tentativa {attempt} de {func.__name__}: {e}")
            time.sleep(delay)

    # Ao final, em vez de traceback, logamos e lançamos um erro simples
    error_msg = f"{func.__name__} falhou após {retries} tentativas: {last_error}"
    logging.error(error_msg)
    # se você quiser que execute_trade capture, use:
    raise RuntimeError(error_msg)


def set_leverage(symbol, leverage, exchange):
    try:
        market = exchange.market(symbol)
        response = exchange.fapiPrivatePostLeverage(
            {"symbol": market["id"], "leverage": leverage}
        )
        logging.info(
            "Alavancagem definida para %s: %s",
            symbol,
            response.get("leverage", leverage),
        )
    except Exception as e:
        logging.exception(
            "Erro ao definir alavancagem: %s",
            e,
        )


def set_margin_type(symbol, margin_type, exchange):
    try:
        market = exchange.market(symbol)
        # Mesmo response estando null o retorno será:
        # "Margem definida para BTC/USDT: CROSSED"
        response = exchange.fapiPrivatePostMarginType(
            {"symbol": market["id"], "marginType": margin_type}
        )
        logging.info("Margem definida para %s: %s", symbol, margin_type)
    except Exception as e:
        if "No need to change margin type" in str(e):
            logging.info("Margem já configurada para %s: %s", symbol, margin_type)
        else:
            logging.exception(
                "Erro ao definir margem: %s",
                e,
            )


def get_candles(exchange, symbol, timeframe, limit=500):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(
        ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def cancel_protection_orders(future_symbol, exchange):
    try:
        retry_operation(exchange.cancel_all_orders, future_symbol)
        logging.info("Ordens canceladas para %s.", future_symbol)
    except Exception as e:
        logging.exception(
            "Erro cancelando ordens: %s",
            e,
        )


# ============================================================================
# --------Função auxiliar para centralizar consulta de posição ativa----------
def _fetch_positions(client, time_offset):
    """
    Agora usamos o time_offset para ajustar o timestamp.
    """
    ts = int(time.time() * 1000 + time_offset)
    return client.get_position_risk(recvWindow=6000, timestamp=ts)


def get_open_position(config, future_symbol):
    """
    Busca a posição aberta para `future_symbol`, compensando o clock drift
    com o time_offset salvo em config['time_offset'].
    Retorna a posição (dict) ou None.
    """
    client = UMFutures(
        key=config["real_api_key"].strip(), secret=config["real_api_secret"].strip()
    )
    target = future_symbol.replace("/", "").upper()

    # aplica o time_offset guardado no config
    offset = config.get("time_offset", 0)
    try:
        # timestamp local em ms + offset
        adjusted_ts = int(time.time() * 1000) + offset
        positions = client.get_position_risk(recvWindow=6000, timestamp=adjusted_ts)
    except Exception as e:
        logging.error("Erro em get_open_position: %s", e)
        return None

    for pos in positions:
        if (
            pos.get("symbol", "").upper() == target
            and abs(float(pos.get("positionAmt", 0))) >= 1e-6
        ):
            return pos
    return None


# ============================================================================
# -----Função para aguardar o fechamento da posição e resetar contadores------
def wait_for_position_close(config, future_symbol, status_callback):
    timeout = 30
    start_wait = time.time()
    while time.time() - start_wait < timeout:
        if get_open_position(config, future_symbol) is None:
            break
        time.sleep(0.1)  # Delay de 100 milissegundos para permitir processamentos
    global last_position_qty, last_order_qty, last_entry_price, active_stop_gain_data, last_order_time, reposicao_count, signal_count
    last_position_qty = None
    last_order_qty = None
    last_entry_price = None
    signal_count = 0
    reposicao_count = 0
    active_stop_gain_data = None
    last_order_time = 0
    if status_callback:
        status_callback("Operando...")


# ============================================================================
# -------------------Funções de fechamento reduceOnly-------------------------
def send_account_balance(exchange):
    """
    Busca o saldo total de USDT na conta futures e envia ao Telegram.
    """
    try:
        bal = exchange.fetch_balance()
        # Em contas futures da Binance, o saldo disponível de USDT costuma vir em 'total' ou 'USDT'
        usdt_total = bal.get("total", {}).get("USDT") or bal.get("USDT", {}).get(
            "total"
        )
        if usdt_total is not None:
            send_telegram_message(f"Saldo Atual de USDT: {float(usdt_total):.2f}")
        else:
            send_telegram_message(
                "Saldo Atual: não foi possível obter o valor de USDT."
            )
    except Exception as e:
        logging.error("Erro ao buscar saldo da conta: %s", e)
        send_telegram_message("Erro ao obter saldo da conta.")


def fechar_posicao_por_roi_stop_loss(
    symbol, side, qty, last_entry_price, current_price, exchange, status_callback=None
):
    try:
        params = {"reduceOnly": True}
        order = exchange.create_order(symbol, "market", side, abs(qty), None, params)
        # usa 'or current_price' para garantir que sempre seja numérico
        fechamento_preco = order.get("average") or current_price
        # Mensagem centralizada
        msg = DEFAULT_FECHAMENTO_MSG["roi_stop_loss"].format(
            symbol=symbol, price=fechamento_preco, order_id=order.get("id", "N/A")
        )
        logging.info(msg)
        send_telegram_message(msg)

        pnl = (
            (fechamento_preco - last_entry_price) * qty
            if qty > 0
            else (last_entry_price - fechamento_preco) * abs(qty)
        )
        resultado_msg = (
            f"Resultado (Stop Loss): ROI = {last_roi:.2f}% | PnL = {pnl:.4f} USDT"
        )
        send_telegram_message(resultado_msg)

        if status_callback:
            status_callback(f"{msg} | {resultado_msg}")
        # 3) Envia saldo
        send_account_balance(exchange)
    except Exception as e:
        erro = f"Erro ao fechar posição por Stop Loss: {e}"
        logging.error(erro)
        if status_callback:
            status_callback(erro)


def fechar_posicao_por_roi_stop_win(
    symbol, side, qty, last_entry_price, current_price, exchange, status_callback=None
):
    try:
        params = {"reduceOnly": True}
        order = exchange.create_order(symbol, "market", side, abs(qty), None, params)
        # forçar fallback para current_price
        fechamento_preco = order.get("average") or current_price
        msg = DEFAULT_FECHAMENTO_MSG["roi_stop_win"].format(
            symbol=symbol, price=fechamento_preco, order_id=order.get("id", "N/A")
        )
        logging.info(msg)
        send_telegram_message(msg)

        pnl = (
            (fechamento_preco - last_entry_price) * qty
            if qty > 0
            else (last_entry_price - fechamento_preco) * abs(qty)
        )
        resultado_msg = (
            f"Resultado (Stop Win): ROI = {last_roi:.2f}% | PnL = {pnl:.4f} USDT"
        )
        send_telegram_message(resultado_msg)

        if status_callback:
            status_callback(f"{msg} | {resultado_msg}")
        # 3) Envia saldo
        send_account_balance(exchange)
    except Exception as e:
        erro = f"Erro ao fechar posição por Stop Win: {e}"
        logging.error(erro)
        if status_callback:
            status_callback(erro)


def fechar_posicao_por_barreira(
    symbol, side, qty, last_entry_price, current_price, exchange, status_callback=None
):
    try:
        params = {"reduceOnly": True}
        order = exchange.create_order(symbol, "market", side, abs(qty), None, params)
        # forçar fallback para current_price
        fechamento_preco = order.get("average") or current_price
        msg = DEFAULT_FECHAMENTO_MSG["barreira"].format(
            symbol=symbol, price=fechamento_preco, order_id=order.get("id", "N/A")
        )
        logging.info(msg)
        send_telegram_message(msg)

        pnl = (
            (fechamento_preco - last_entry_price) * qty
            if qty > 0
            else (last_entry_price - fechamento_preco) * abs(qty)
        )
        resultado_msg = (
            f"Resultado (Barreira): ROI = {last_roi:.2f}% | PnL = {pnl:.4f} USDT"
        )
        send_telegram_message(resultado_msg)

        if status_callback:
            status_callback(f"{msg} | {resultado_msg}")
        # 3) Envia saldo
        send_account_balance(exchange)
    except Exception as e:
        erro = f"Erro ao fechar posição por Barreira: {e}"
        logging.error(erro)
        if status_callback:
            status_callback(erro)


def fechar_posicao_por_rsi_reversao(
    symbol, side, qty, last_entry_price, current_price, exchange, status_callback=None
):
    try:
        params = {"reduceOnly": True}
        order = exchange.create_order(symbol, "market", side, abs(qty), None, params)
        # forçar fallback para current_price
        fechamento_preco = order.get("average") or current_price
        msg = DEFAULT_FECHAMENTO_MSG["rsi_reversao"].format(
            symbol=symbol, price=fechamento_preco, order_id=order.get("id", "N/A")
        )
        logging.info(msg)
        send_telegram_message(msg)

        pnl = (
            (fechamento_preco - last_entry_price) * qty
            if qty > 0
            else (last_entry_price - fechamento_preco) * abs(qty)
        )
        resultado_msg = (
            f"Resultado (RSI Reversão): ROI = {last_roi:.2f}% | PnL = {pnl:.4f} USDT"
        )
        send_telegram_message(resultado_msg)

        if status_callback:
            status_callback(f"{msg} | {resultado_msg}")
        # 3) Envia saldo
        send_account_balance(exchange)
    except Exception as e:
        erro = f"Erro ao fechar posição por RSI de Reversão: {e}"
        logging.error(erro)
        if status_callback:
            status_callback(erro)


def fechar_posicao_por_reversao(
    symbol, side, qty, last_entry_price, current_price, exchange, status_callback=None
):
    try:
        params = {"reduceOnly": True}
        order = exchange.create_order(symbol, "market", side, abs(qty), None, params)
        # forçar fallback para current_price
        fechamento_preco = order.get("average") or current_price
        msg = DEFAULT_FECHAMENTO_MSG["reversao"].format(
            symbol=symbol, price=fechamento_preco, order_id=order.get("id", "N/A")
        )
        logging.info(msg)
        send_telegram_message(msg)

        pnl = (
            (fechamento_preco - last_entry_price) * qty
            if qty > 0
            else (last_entry_price - fechamento_preco) * abs(qty)
        )
        resultado_msg = (
            f"Resultado (Reversão): ROI = {last_roi:.2f}% | PnL = {pnl:.4f} USDT"
        )
        send_telegram_message(resultado_msg)

        if status_callback:
            status_callback(f"{msg} | {resultado_msg}")
        # 3) Envia saldo
        send_account_balance(exchange)
    except Exception as e:
        erro = f"Erro ao fechar posição por Reversão: {e}"
        logging.error(erro)
        if status_callback:
            status_callback(erro)


# ============================================================================
# --------------- Função de Atualização da Ordem de Stop Gain ----------------
def update_stop_gain_order(
    symbol,
    side,
    pos_qty,
    last_entry_price,
    current_price,
    exchange,
    active_order_data,
    stop_distance,
):
    """
    Atualiza a ordem de stop gain (trailing stop) para mover a barreira para um valor mais favorável sem recuar.
    Primeiro cria a nova ordem; se for criada com sucesso, cancela a ordem anterior.
    Para LONG (side='sell'), a barreira = pico máximo - stop_distance.
    Para SHORT (side='buy'), a barreira = fundo mínimo + stop_distance.
    """
    current_time = time.time()
    if active_order_data is None:
        active_order_data = {
            "order_id": None,
            "barrier": None,
            "max_price": None,
            "min_price": None,
            "init_time": current_time,
        }
    new_order = None
    new_barrier = None

    if side == "sell":  # Proteção para posição LONG (compra)
        # Atualiza pico para LONG
        if (
            active_order_data.get("max_price") is None
            or current_price > active_order_data["max_price"]
        ):
            active_order_data["max_price"] = current_price
        # Calcula barreira a partir do stop_distance fornecido
        candidate_barrier = active_order_data["max_price"] - stop_distance
        if (
            active_order_data.get("barrier") is None
            or candidate_barrier > active_order_data["barrier"]
        ):
            new_barrier = candidate_barrier
            params = {"stopPrice": new_barrier, "reduceOnly": True}
            try:
                new_order = retry_operation(
                    exchange.create_order,
                    symbol,
                    "STOP_MARKET",
                    side,
                    abs(pos_qty),
                    None,
                    params,
                )
                logging.info(
                    "Nova ordem de stop gain (LONG) criada com barrier = %.4f, ordem ID = %s",
                    new_barrier,
                    new_order.get("id"),
                )
            except Exception as e:
                logging.exception(
                    "Erro ao criar nova ordem de stop gain (LONG): %s",
                    e,
                )
    elif side == "buy":  # Proteção para posição SHORT (venda)
        # Atualiza fundo para SHORT
        if (
            active_order_data.get("min_price") is None
            or current_price < active_order_data["min_price"]
        ):
            active_order_data["min_price"] = current_price
        candidate_barrier = active_order_data["min_price"] + stop_distance
        if (
            active_order_data.get("barrier") is None
            or candidate_barrier < active_order_data["barrier"]
        ):
            new_barrier = candidate_barrier
            params = {"stopPrice": new_barrier, "reduceOnly": True}
            try:
                new_order = retry_operation(
                    exchange.create_order,
                    symbol,
                    "STOP_MARKET",
                    side,
                    abs(pos_qty),
                    None,
                    params,
                )
                logging.info(
                    "Nova ordem de stop gain (SHORT) criada com barrier = %.4f, ordem ID = %s",
                    new_barrier,
                    new_order.get("id"),
                )
            except Exception as e:
                logging.exception(
                    "Erro ao criar nova ordem de stop gain (SHORT): %s",
                    e,
                )
    else:
        logging.error("Lado não reconhecido para atualização da barreira: %s", side)

    if new_order is not None:
        if active_order_data.get("order_id"):
            try:
                exchange.cancel_order(active_order_data["order_id"], symbol)
                logging.info(
                    "Ordem de stop gain anterior cancelada: %s",
                    active_order_data["order_id"],
                )
            except Exception as e:
                logging.exception(
                    "Erro ao cancelar ordem de stop gain anterior: %s",
                    e,
                )
        active_order_data["order_id"] = new_order.get("id")
        active_order_data["barrier"] = new_barrier
        active_order_data["last_update_time"] = current_time

    return active_order_data


# ============================================================================
# ------------------ Websocket para Atualização dos Candles ------------------
def on_message(ws, message, event, candle_type):
    global live_price, current_candle_main, current_candle_conf, current_candle_comp
    try:
        data = json.loads(message)
        if "k" in data:
            kline = data["k"]
            if candle_type == "main":
                live_price = float(kline.get("c", 0))
                current_candle_main = kline
            elif candle_type == "conf":
                current_candle_conf = kline
            elif candle_type == "comp":
                current_candle_comp = kline
            if kline.get("x"):
                event.set()
    except Exception as e:
        logging.exception(
            "Erro no on_message do WebSocket: %s",
            e,
        )


def on_open(ws, event, candle_type):
    logging.info("Websocket handshake completo para %s", candle_type)
    # dispara o event imediatamente após a conexão, antes de esperar pelo fechamento do candle
    event.set()


def start_ws_listener(symbol, interval, event, candle_type, stop_event):
    ws_url = f"wss://fstream.binance.com/ws/{symbol.lower().replace('/', '')}@kline_{interval}"
    ws_app = websocket.WebSocketApp(
        ws_url,
        on_open=lambda ws: on_open(ws, event, candle_type),
        on_message=lambda ws, msg: on_message(ws, msg, event, candle_type),
        on_error=lambda ws, err: logging.error("Erro no WebSocket: %s", err),
        on_close=lambda ws, code, msg: logging.info(
            "WebSocket fechado: %s %s", code, msg
        ),
    )
    ws_apps.append(ws_app)
    # Loop para reiniciar até receber stop_event
    while not stop_event.is_set():
        ws_app.run_forever(ping_interval=30, ping_timeout=10)
        # se desconectar, aguarda 1s e tenta reconectar
        time.sleep(1)


# ============================================================================
# ----------------------- Recupera posição já aberta -------------------------
def recover_existing_position(config):
    """
    Tenta recuperar uma posição já aberta para config["future_symbol"].
    Retorna o dict da posição ou None.
    """
    symbol = config["future_symbol"]
    pos = get_open_position(config, symbol)
    if pos:
        qty = float(pos.get("positionAmt", 0))
        logging.info("Posição aberta recuperada para %s: Qtd=%.4f", symbol, qty)
        global last_order_qty, last_entry_price, active_stop_gain_data
        last_order_qty = qty
        entry = float(pos.get("entryPrice", 0))
        if entry > 0:
            last_entry_price = entry
        active_stop_gain_data = {
            "order_id": None,
            "barrier": None,
            "max_price": None,
            "min_price": None,
            "init_time": time.time(),
        }
        return pos
    else:
        logging.info("Nenhuma posição aberta encontrada para %s.", symbol)
        return None


# ============================================================================
# -------------- Função para Execução de Ordens e Atualizações ---------------
def execute_trade(
    future_symbol, side, margin, atr, exchange, status_callback=None, is_reposicao=False
):
    global last_entry_price, last_order_qty, last_order_time
    global active_stop_gain_data, reposicao_count, signal_count, first_entry_done

    # --- Definir o lado do trade conforme o sinal recebido ---
    if side.lower() == "long":
        trade_side = "buy"
    elif side.lower() == "short":
        trade_side = "sell"
    else:
        trade_side = side.lower()

    # --- Definir order_type com base no contexto da ordem ---
    if is_reposicao:
        order_type = "Ordem de Reposição"
    elif last_order_qty is not None and abs(last_order_qty) > 1e-8:
        order_type = "Nova Ordem"
    else:
        order_type = "Ordem Normal"
    # ---------------- Fim da definição ---------------------------------------

    current_time = time.time()

    # Se já existe posição aberta e não se trata de reposição, verificar o intervalo mínimo de 5 minutos
    if (last_order_qty is not None and abs(last_order_qty) > 1e-8) or is_reposicao:
        # Para reposição, ignoramos o tempo mínimo entre ordens
        if not is_reposicao:
            if (current_time - last_order_time) < 300:
                logging.info(
                    "%s ignorada: Intervalo de 5 minutos não decorrido para posição aberta.",
                    order_type,
                )
                return False  # Não executa a operação
            last_order_time = current_time
        # Em novo sinal (que aumenta a posição) ou reposição, cancelamos as ordens de proteção
        cancel_protection_orders(future_symbol, exchange)
        time.sleep(0.1)  # Delay de 100 milissegundos para permitir processamentos
        ticker = exchange.fetch_ticker(future_symbol)
        current_price = ticker["last"]
        logging.info("Preço obtido do ticker: %.4f", current_price)
        logging.info(
            "%s: Atualizando posição com margem de %.2f USDT.", order_type, margin
        )
        quantity_new = (margin * config_leverage) / current_price
        quantity_new = exchange.amount_to_precision(future_symbol, quantity_new)
        new_qty = float(quantity_new) if trade_side == "buy" else -float(quantity_new)

        # Atualiza média ponderada se já existir posição
        if last_order_qty is not None and (
            (trade_side == "buy" and last_order_qty > 0)
            or (trade_side == "sell" and last_order_qty < 0)
        ):
            total_qty = last_order_qty + new_qty
            if total_qty != 0:
                new_avg = (
                    last_entry_price * abs(last_order_qty)
                    + current_price * abs(new_qty)
                ) / (abs(last_order_qty) + abs(new_qty))
                last_order_qty = total_qty
                last_entry_price = new_avg
                logging.info(
                    "%s: Atualizando média ponderada do EntryPrice para: %.4f",
                    order_type,
                    new_avg,
                )
            else:
                last_order_qty = new_qty
                last_entry_price = current_price
                logging.info(
                    "%s: Setando EntryPrice para: %.4f", order_type, current_price
                )
        else:
            last_order_qty = new_qty
            last_entry_price = current_price
            logging.info("%s: Setando EntryPrice para: %.4f", order_type, current_price)

        logging.info("%s: Quantidade de entrada inicial: %s", order_type, quantity_new)
        try:
            entry_order = retry_operation(
                exchange.create_order,
                future_symbol,
                "market",
                trade_side,
                abs(float(quantity_new)),
            )
            logging.info(
                "%s executada (ID: %s) a %.4f",
                order_type,
                entry_order.get("id", "N/A"),
                current_price,
            )
            send_telegram_message(
                f"{order_type}: {trade_side.upper()} {future_symbol} executada a {current_price:.4f}"
            )
            execution_price = entry_order.get("average", current_price)
            last_entry_price = execution_price
            logging.info(
                "%s: Preço de execução (EntryPrice atualizado): %.4f",
                order_type,
                execution_price,
            )
            time.sleep(0.1)  # Delay de 100 ms antes de ajustar proteções
            # —————————————— Forçar nova barreira após entrada ——————————————
            active_stop_gain_data = None
            # —————— Reinicia somente os contadores ——————
            reposicao_count = 0
            signal_count = 0
            return True
        except RuntimeError as e:
            # Aqui e é a string do retry_operation formatada
            msg = f"{order_type} falhou: {e}"
            logging.error(msg)
            if status_callback:
                status_callback(msg)
            return False
        except ClientError as ce:
            # Mantém o mesmo estilo
            msg = f"{order_type} Binance ClientError: {ce}"
            logging.error(msg)
            if status_callback:
                status_callback(msg)
            return False

    else:
        # -------- Caso não haja posição aberta (entrada normal ou imediata) --------
        ticker = exchange.fetch_ticker(future_symbol)
        current_price = ticker["last"]
        logging.info("Preço obtido do ticker: %.4f", current_price)
        logging.info("%s: Setando EntryPrice para: %.4f", order_type, current_price)
        last_order_qty = None  # Será criado o novo trade
        last_entry_price = current_price
        # Calcular a quantidade com a mesma precisão do ramo com posição aberta
        quantity_new = (margin * config_leverage) / current_price
        quantity_new = exchange.amount_to_precision(future_symbol, quantity_new)
        logging.info(
            "%s: Quantidade calculada para entrada: %s", order_type, quantity_new
        )
        try:
            entry_order = retry_operation(
                exchange.create_order,
                future_symbol,
                "market",
                trade_side,
                abs(float(quantity_new)),
            )
            logging.info(
                "%s executada (ID: %s) a %.4f",
                order_type,
                entry_order.get("id", "N/A"),
                current_price,
            )
            send_telegram_message(
                f"{order_type}: {trade_side.upper()} {future_symbol} executada a {current_price:.4f}"
            )
            execution_price = entry_order.get("average", current_price)
            last_entry_price = execution_price
            logging.info(
                "%s: Preço de execução (EntryPrice atualizado): %.4f",
                order_type,
                execution_price,
            )
            time.sleep(0.1)  # Delay de 100 ms antes de ajustar proteções
            # ————— Forçar nova barreira após entrada —————
            active_stop_gain_data = None
            return True
        except Exception as e:
            logging.exception(
                "Erro em %s: %s",
                order_type,
                e,
            )
            if status_callback:
                status_callback(f"Erro em {order_type}: {e}")
            return False
            # --------------------------- Fim do execute_trade ---------------------------
            # ============================================================================


# ============================================================================
# ----------------- Função para pré-processar a configuração -----------------
def preprocess_config(config):
    # ------------- Valores padrão para todos os parâmetros do robô --------------
    defaults = {
        "lot_value": 10,  # Valor de investimento em USDT por operação
        "confirmation_tolerance": 0.05,  # Tolerância para confirmação (% convertida para decimal)
        "max_signals": 4,  # Máximo de novos sinais permitidos
        "max_reposicao_orders": 1,  # Máximo de ordens de reposição permitidas
        "reposicao_multiplier": 1.1,  # Multiplicador para aumentar a margem na reposição
        "reposicao_roi_threshold": -25,  # Limiar de ROI negativo para acionar reposição
        "retry_attempts": 3,  # Número de tentativas de reexecução em caso de falha
        "retry_delay": 3,  # Delay em segundos entre tentativas de reexecução
        "leverage": 125,  # Alavancagem utilizada nas operações
        "margin_mode": "CROSSED",  # Modo de margem: "CROSSED" ou "ISOLATED"
        "order_book_levels": 5,  # Nível de profundidade do order book a ser analisado
        "adx_threshold": 25,  # Limiar do ADX para validação do sinal
        "roi_stop_loss_threshold": -50,  # Limiar de ROI negativo que aciona o Stop Loss
        "roi_stop_win_threshold": 100,  # Limiar de ROI positivo que aciona o Stop Win
        "roi_trailing_activation": 50,  # limiar (%) para começar o trailing stop
        "min_imbalance_long": 0.3,  # Limiar mínimo para desequilíbrio para sinal LONG
        "max_imbalance_short": -0.3,  # Limiar máximo (valor negativo) para sinal SHORT
        "distance": 400,  # Distância inicial da barreira (pontos)
        "indicator_period": 14,  # Período para cálculo dos indicadores técnicos
        "comparison_tf": "5m",  # Timeframe para os candles de comparação
        "operational_tf": "15m",  # Timeframe para os candles operacionais
        "confirmation_tf": "1m",  # Timeframe para os candles de confirmação
        "rsi_protection_min": 30,  # Limite inferior do RSI para proteção em posições LONG
        "rsi_protection_max": 70,  # Limite superior do RSI para proteção em posições SHORT
        "enable_novossinais": True,  # Habilita/Desabilita a entrada de novos sinais
        "roi_reduzir": 25,  # ROI (+%) a partir do qual reduzir a distância da Barreira Inicial
        "trailing_stop_percent": 0.00118,  # Distância do trailing stop
    }

    # Atualiza ou define cada parâmetro no dicionário de configuração
    for key, value in defaults.items():
        config[key] = config.get(key, value)
    return config


MODEL_DIR = "models"


# ============================================================================
# ------------ Função run_realtime – Atualização contínua dos logs -----------
def run_realtime(
    config,
    log_callback=None,
    status_callback=None,
    stop_event=None,
    shutdown_callback=None,
):
    """
    Loop principal do robô.  Recebe um dicionário de configuração já
    validado na GUI, inicializa a exchange, web-sockets, licenciamento,
    heart-beat, variáveis globais e — dentro do while True — processa
    candles, indicadores, ML, ordens e proteções.
    """
    # ———————— Declarar globals antes de usar ou atribuir ————————
    global RETRY_ATTEMPTS, RETRY_DELAY, config_leverage
    global last_pnl, order_closed_notified
    global last_order_qty, last_entry_price, last_position_qty, last_order_time
    global reposicao_count, signal_count, first_entry_done, active_stop_gain_data
    global last_roi

    # Agora você pode atribuir sem erro:
    reposicao_count = 0
    signal_count = 0
    first_entry_done = False
    active_stop_gain_data = None

    # ➡️ Carrega flags da config
    enable_new = config.get("enable_novossinais", True)

    future_symbol = config["future_symbol"]

    # --------------------- 1)  Normaliza / completa config ------------------
    config = preprocess_config(config)  # define valores-padrão

    # --------------------- 2)  Modelo de Machine-Learning -------------------
    ml_model = config.get("ml_model")  # já vem da GUI
    if ml_model is None:
        logging.info(
            "Machine Learning indisponível p/ %s; pulando predições.", future_symbol
        )

    # --------------------- 3)  Lê parâmetros da interface -------------------
    margin = float(config["lot_value"])
    confirmation_tolerance = float(config["confirmation_tolerance"])
    max_signals = int(config["max_signals"])
    max_reposicao_orders = int(config["max_reposicao_orders"])
    reposicao_multiplier = float(config["reposicao_multiplier"])
    reposicao_roi_threshold = float(config["reposicao_roi_threshold"])
    RETRY_ATTEMPTS = int(config["retry_attempts"])
    RETRY_DELAY = float(config["retry_delay"])
    config_leverage = int(config["leverage"])
    leverage = int(config["leverage"])
    margin_mode = config["margin_mode"]
    order_book_levels = int(config["order_book_levels"])
    adx_threshold = float(config["adx_threshold"])
    roi_stop_loss_threshold = float(config["roi_stop_loss_threshold"])
    roi_stop_win_threshold = float(config["roi_stop_win_threshold"])
    min_imbalance_long = float(config["min_imbalance_long"])
    max_imbalance_short = float(config["max_imbalance_short"])
    indicator_period = int(config["indicator_period"])
    operational_tf = config["operational_tf"]
    conf_tf = config["confirmation_tf"]
    comparison_tf = config["comparison_tf"]
    rsi_protection_min = float(config["rsi_protection_min"])
    rsi_protection_max = float(config["rsi_protection_max"])
    ml_confidence_threshold = float(config.get("ml_confidence_threshold", 0.55))
    initial_barrier = float(config["distance"])
    distance = float(config["distance"])
    roi_reduzir = float(config["roi_reduzir"])
    trailing_stop_percent = float(config["trailing_stop_percent"])
    roi_trailing_activation = float(config["roi_trailing_activation"])
    atr_multiplier = float(config.get("atr_multiplier", 1.0))

    # --------------------- 4)  Logs de conferência --------------------------
    logging.info("Parâmetros carregados:")
    logging.info(
        "lot_value=%s, confirmation_tolerance=%s, max_signals=%s",
        margin,
        confirmation_tolerance,
        max_signals,
    )
    logging.info(
        "max_reposicao_orders=%s, reposicao_multiplier=%s, "
        "reposicao_roi_threshold=%s",
        max_reposicao_orders,
        reposicao_multiplier,
        reposicao_roi_threshold,
    )
    logging.info(
        "future_symbol=%s, leverage=%s, margin_mode=%s",
        future_symbol,
        leverage,
        margin_mode,
    )
    logging.info(
        "order_book_levels=%s, adx_threshold=%s, "
        "roi_stop_loss_threshold=%s, roi_stop_win_threshold=%s",
        order_book_levels,
        adx_threshold,
        roi_stop_loss_threshold,
        roi_stop_win_threshold,
    )
    logging.info(
        "min_imbalance_long=%s, max_imbalance_short=%s",
        min_imbalance_long,
        max_imbalance_short,
    )
    logging.info(
        "indicator_period=%s, operational_tf=%s, confirmation_tf=%s, "
        "comparison_tf=%s",
        indicator_period,
        operational_tf,
        conf_tf,
        comparison_tf,
    )
    logging.info(
        "rsi_protection_min=%s, rsi_protection_max=%s",
        rsi_protection_min,
        rsi_protection_max,
    )
    logging.info("ml_confidence_threshold=%s%%", ml_confidence_threshold * 100)
    logging.info(
        "initial_barrier=%s, distance=%s, roi_reduzir=%s, "
        "roi_trail_act=%s, trailing_stop_percent=%s",
        initial_barrier,
        distance,
        roi_reduzir,
        roi_trailing_activation,
        trailing_stop_percent,
    )
    logging.info("atr_multiplier=%s", atr_multiplier)

    # --------------------- 5)  Debounce de sinal oposto ---------------------
    opposite_signal_count = 0
    opposite_signal_start_ts = None

    # --------------------- 6)  Zera contadores, posição, etc. ---------------
    reset_contadores()

    # ——————— Limpa qualquer barreira existente AO INICIAR O ROBÔ ———————
    active_stop_gain_data = None

    # --------------------- 7)  Inicia WebSockets (candle live) --------------
    ws_event_main = threading.Event()
    ws_event_conf = threading.Event()
    ws_event_comp = threading.Event()

    threading.Thread(
        target=start_ws_listener,
        args=(future_symbol, operational_tf, ws_event_main, "main", stop_event),
        daemon=True,
    ).start()
    time.sleep(0.1)
    threading.Thread(
        target=start_ws_listener,
        args=(future_symbol, conf_tf, ws_event_conf, "conf", stop_event),
        daemon=True,
    ).start()
    time.sleep(0.1)
    threading.Thread(
        target=start_ws_listener,
        args=(future_symbol, comparison_tf, ws_event_comp, "comp", stop_event),
        daemon=True,
    ).start()

    ws_event_conf.wait()  # garante 1º candle de confirmação

    # --------------------- 8)  Cria objeto CCXT / Binance -------------------
    exchange = ccxt.binance(
        {
            "apiKey": config["real_api_key"].strip(),
            "secret": config["real_api_secret"].strip(),
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",
                "adjustForTimeDifference": True,
                "fetchMarketsMethod": "fapiPublicGetExchangeInfo",
                "fetchCurrencies": False,  # <— pula o fetch de moedas
            },
        }
    )
    exchange.load_markets()
    set_leverage(future_symbol, leverage, exchange)
    set_margin_type(future_symbol, margin_mode, exchange)
    cancel_protection_orders(future_symbol, exchange)

    # >>>> AQUI >>>> calcular o offset do relógio para as chamadas autenticadas
    client = UMFutures(
        key=config["real_api_key"].strip(), secret=config["real_api_secret"].strip()
    )
    # ... depois de configurar a variável `exchange` ...
    server_ts = exchange.fetch_time()  # timestamp do servidor em ms
    local_ts = int(time.time() * 1000)
    time_offset = server_ts - local_ts
    logging.info(f"Time offset (ms) Binance ↔ local: {time_offset}")
    config["time_offset"] = time_offset  # salva no config

    # agora pode chamar recover_existing_position e get_open_position SEM passar time_offset
    selected_pos = recover_existing_position(config)

    if log_callback:
        log_callback("Operação Iniciada!")
    codigo_unico = obter_codigo_licenca()
    threading.Thread(
        target=heartbeat_loop, args=(codigo_unico, 60, stop_event), daemon=True
    ).start()
    threading.Thread(
        target=license_monitor,
        args=(stop_event, status_callback, shutdown_callback, log_callback),
        daemon=True,
    ).start()

    # --------------------- 9)  Recupera posição aberta (se houver) ----------
    if selected_pos:
        logging.info("Robô adotou posição aberta para %s.", future_symbol)
        last_order_qty = float(selected_pos.get("positionAmt", 0))

        # —————— 10) Cria barreira inicial imediatamente após adotar a posição ——————
        ticker = exchange.fetch_ticker(future_symbol)
        current_price = ticker["last"]
        distance = float(config["distance"])

        active_stop_gain_data = {
            "order_id": None,
            "barrier": None,
            "max_price": current_price,
            "min_price": current_price,
            "init_time": time.time(),
            "reduced_once": False,
            "trailing_active": False,
        }
        active_stop_gain_data = update_stop_gain_order(
            future_symbol,
            "sell" if last_order_qty > 0 else "buy",
            last_order_qty,
            last_entry_price,
            current_price,
            exchange,
            active_stop_gain_data,
            stop_distance=distance,
        )
    else:
        logging.info("Nenhuma posição aberta recuperada – aguardando sinal.")

    # Constantes internas
    TEMPO_MINIMO_FORCE_PROTECTION = 30  # seg
    FORCE_PROTECTION_TIMEOUT = 300  # seg
    last_api_check_time = time.time()
    api_miss_count = 0

    def finalize_position(
        close_fn,
        symbol,
        side,
        qty,
        entry_price,
        current_price,
        exchange,
        status_cb,
        log_msg,
    ):
        """
        Executa o fechamento (via close_fn), envia log, resultado (ROI/PnL) e saldo,
        espera o fechamento, cancela proteções e reseta contadores.
        """
        # 1) Log de início de fechamento
        logging.info(log_msg)
        try:
            # 2) Executa fechamento (cada close_fn já envia msg de preço)
            close_fn(symbol, side, qty, entry_price, current_price, exchange, status_cb)

            # 3) Calcula PnL e ROI
            # Para LONG (side='sell'): pnl = (current_price - entry_price)*qty
            # Para SHORT (side='buy'):  pnl = (entry_price - current_price)*qty
            if side == "sell":
                pnl = (current_price - entry_price) * qty
            else:
                pnl = (entry_price - current_price) * qty
            # margem usada = entry_price * qty
            margin_used = entry_price * qty
            roi = (pnl / margin_used * 100) if margin_used else 0.0

            # 4) Envia resultado
            resultado_msg = f"Resultado Final: ROI = {roi:.2f}% | PnL = {pnl:.4f} USDT"
            logging.info(resultado_msg)
            send_telegram_message(resultado_msg)

            # 5) Envia saldo atualizado
            send_account_balance(exchange)

        except Exception as e:
            logging.exception(
                "Erro no finalize_position (%s): %s", close_fn.__name__, e
            )

        # 6) Aguarda realmente a posição fechar
        wait_for_position_close(config, symbol)

        # 7) Cancela quaisquer ordens de proteção remanescentes
        cancel_protection_orders(symbol, exchange)

        # 8) Reseta todos os contadores
        reset_contadores()

        # 9) Permite novas entradas
        first_entry_done = False
        if status_cb:
            status_cb("Operando…")

    # Início do loop principal
    while True:
        # --------------------------------------------------------------------
        # 0) Encerramento limpo se stop_event for sinalizado
        # --------------------------------------------------------------------
        if stop_event and stop_event.is_set():
            if log_callback:
                log_callback(STOP_MSG)
            if status_callback:
                status_callback("Encerrado OK!")
            break

        # --------------------------------------------------------------------
        # 1) VERIFICAÇÃO DE LICENÇA – a cada 15 min isso já roda numa thread,
        #    aqui apenas abortamos se o monitor a invalidou.
        # --------------------------------------------------------------------
        if shutdown_callback and shutdown_callback():
            logging.error("Licença expirada (callback). Encerrando robô.")
            if status_callback:
                status_callback("Licença expirada.")
            break

        # --------------------------------------------------------------------
        # 2) CAPTURA PREÇO ATUAL  (ticker vs candle alive do WS)
        # --------------------------------------------------------------------
        try:
            ticker = exchange.fetch_ticker(future_symbol)
            time.sleep(0.01)
            ticker_price = ticker["last"]
        except Exception as e:
            logging.exception(
                "Erro fetch_ticker: %s",
                e,
            )
            ticker_price = 0

        if not last_order_qty or abs(last_order_qty) < 1e-8:  # sem posição
            current_price = ticker_price
        else:  # tem posição
            if current_candle_main:
                cp = float(current_candle_main.get("c", 0))
                if cp > 0:
                    current_price = cp
                else:
                    current_price = ticker_price
            else:
                current_price = ticker_price

        if not current_price:
            logging.error("Preço indisponível; aguardando...")
            time.sleep(0.5)
            continue

        # --------------------------------------------------------------------
        # 3) CANDLE DE COMPARAÇÃO (comparison_tf)
        # --------------------------------------------------------------------
        df_comp = get_candles(exchange, future_symbol, comparison_tf, limit=50)
        if current_candle_comp:
            # espelha candle ainda aberto
            df_comp.iloc[-1, df_comp.columns.get_loc("open")] = float(
                current_candle_comp["o"]
            )
            df_comp.iloc[-1, df_comp.columns.get_loc("close")] = float(
                current_candle_comp["c"]
            )
            df_comp.iloc[-1, df_comp.columns.get_loc("high")] = float(
                current_candle_comp["h"]
            )
            df_comp.iloc[-1, df_comp.columns.get_loc("low")] = float(
                current_candle_comp["l"]
            )
        comp_open, comp_close = df_comp.iloc[-1][["open", "close"]]
        comp_color = "\x1b[32m" if comp_close > comp_open else "\x1b[31m"
        logging.info(
            f"{comp_color}Candle Comparação ({comparison_tf}): "
            f"Open={comp_open:.4f}, Close={comp_close:.4f}\x1b[0m"
        )

        # --------------------------------------------------------------------
        # 4) CANDLE OPERACIONAL + FEATURES DO PIPELINE
        # --------------------------------------------------------------------
        df_ind = get_candles(exchange, future_symbol, operational_tf, limit=500)
        # ── A) calcula os indicadores de ML/features
        df_feat = compute_features(df_ind.rename(columns={"timestamp": "open_time"}))
        # ── B) calcula o ADX separado para o mesmo dataframe de candles
        df_adx = calculate_adx(
            df_ind.rename(columns={"timestamp": "open_time"}), period=indicator_period
        )
        if len(df_feat) < 2:
            time.sleep(0.2)
            continue
        last_closed_ind = df_feat.iloc[-2]

        # 5) extrai os valores de indicadores do candle fechado anterior
        prev_close = last_closed_ind["close"]
        rsi14_val = last_closed_ind["rsi14"]
        macd_hist = last_closed_ind["macd_hist"]

        # ─── suavização das MAs com JMA ───────────────────────────────────────────────
        # alinhado ao seu MACD(padrão fast=8, slow=17)
        fast_period = 8
        slow_period = 17

        price_series = df_ind["close"]
        jma_fast_series = calculate_jma(price_series, fast_period)
        jma_slow_series = calculate_jma(price_series, slow_period)

        # pega o valor do candle fechado anterior
        ma_fast = jma_fast_series.iloc[-2]
        ma_slow = jma_slow_series.iloc[-2]
        # ────────────────────────────────────────────────────────────────────────────────

        # ADX separado para o mesmo dataframe de candles
        adx_val = df_adx["ADX"].iloc[-2] if len(df_adx) >= 2 else 0.0

        # --------------------------------------------------------------------
        # 5.1) CANDLE DE CONFIRMAÇÃO (conf_tf)
        df_conf = get_candles(exchange, future_symbol, conf_tf, limit=50)
        if current_candle_conf:
            df_conf.iloc[-1, df_conf.columns.get_loc("open")] = float(
                current_candle_conf["o"]
            )
            df_conf.iloc[-1, df_conf.columns.get_loc("close")] = float(
                current_candle_conf["c"]
            )
            df_conf.iloc[-1, df_conf.columns.get_loc("high")] = float(
                current_candle_conf["h"]
            )
            df_conf.iloc[-1, df_conf.columns.get_loc("low")] = float(
                current_candle_conf["l"]
            )
        confirm_candle = df_conf.iloc[-1].to_dict()
        conf_color = (
            "\x1b[32m"
            if confirm_candle["close"] > confirm_candle["open"]
            else "\x1b[31m"
        )
        logging.info(
            f"{conf_color}Candle Confirmação ({conf_tf}): "
            f"Open={confirm_candle['open']:.4f}, "
            f"Close={confirm_candle['close']:.4f}\x1b[0m"
        )

        # 6) BOOK – volume total, imbalance, agressor
        total_bid, total_ask, *_ = get_total_volume(
            exchange, future_symbol, order_book_levels
        )
        bid_vol, ask_vol, imbalance = get_order_book_metrics(
            exchange, future_symbol, order_book_levels
        )
        buy_agg, sell_agg = get_aggressive_volume(
            exchange, future_symbol, limit=order_book_levels
        )

        # 7) MACHINE-LEARNING
        ml_pred = None
        if ml_model is not None:
            latest = (
                df_feat.iloc[-1]
                .drop(["open_time", "target"], errors="ignore")
                .values.reshape(1, -1)
            )
            p_short, p_long = ml_model.predict_proba(latest)[0]
            ml_pred = (
                1
                if p_long >= ml_confidence_threshold
                else (0 if p_short >= ml_confidence_threshold else None)
            )
            logging.info(
                "Machine Learning Probabilidade: SHORT=%.2f%% | LONG=%.2f%%",
                p_short * 100,
                p_long * 100,
            )

        # 8) CONFLUÊNCIA DE INDICADORES
        # 8.1 Médias móveis
        if ma_fast > ma_slow and prev_close > ma_fast:
            mm_signal = "LONG"
        elif ma_fast < ma_slow and prev_close < ma_fast:
            mm_signal = "SHORT"
        else:
            mm_signal = "NEUTRO"

        # 8.2 RSI – retirado da confluência (sempre “OK” aqui)
        rsi_signal = "NEUTRO"  # não usado para decisão neste bloco

        # 8.3 MACD histograma
        macd_signal = (
            "LONG" if macd_hist > 0 else "SHORT" if macd_hist < 0 else "NEUTRO"
        )
        # define booleano de confluência MACD apenas se coincidir com MM
        macd_ok = (macd_signal == mm_signal) or (mm_signal == "NEUTRO")

        # 8.4 ADX
        adx_ok = adx_val > adx_threshold

        # 8.5 Machine Learning
        ml_signal = "LONG" if ml_pred == 1 else "SHORT" if ml_pred == 0 else "NEUTRO"
        # define booleano de confluência ML apenas se coincidir com MM
        ml_ok = (ml_signal == mm_signal) or (mm_signal == "NEUTRO")

        # 8.6 Decisão preliminar de sinal
        if mm_signal in ["LONG", "SHORT"] and macd_ok and adx_ok and ml_ok:
            signal_status = mm_signal
        else:
            signal_status = "NEUTRO"

        # ➡️ Log de indicadores detalhado
        log_callback(
            f"[INDICADORES] "
            f"MA={mm_signal} "
            f"MACD={macd_signal} "
            f"ADX={adx_val:.2f}>{adx_threshold} "
            f"ML={ml_signal}"
        )

        # 9) FILTRO DE BOOK (imbalance + agressor)
        # log_callback(
        #    f"[LIVRO DE OFERTAS] Bids={bid_vol:.2f} Asks={ask_vol:.2f} Imb={imbalance:.2f} "
        #    f"BuyA={buy_agg:.2f} SellA={sell_agg:.2f}"
        # )
        if signal_status == "LONG" and (
            imbalance < min_imbalance_long or buy_agg <= sell_agg
        ):
            log_callback("[BOOK] Cancelado LONG por fluxo/imbalance")
            signal_status = "NEUTRO"
        elif signal_status == "SHORT" and (
            imbalance > max_imbalance_short or sell_agg <= buy_agg
        ):
            log_callback("[BOOK] Cancelado SHORT por fluxo/imbalance")
            signal_status = "NEUTRO"

        # 10) LOG OPERACIONAL COLORIDO
        # use na hora do log:
        pref = (
            "\x1b[32m"
            if signal_status == "LONG"
            else ("\x1b[31m" if signal_status == "SHORT" else "")
        )
        logging.info(
            f"{pref}Candle Operacional ({operational_tf}): "
            f"Close={prev_close:.4f} MA{fast_period}={ma_fast:.4f} MA{slow_period}={ma_slow:.4f} "
            f"RSI14={rsi14_val:.2f} MACD_Hist={macd_hist:.4f} ADX={adx_val:.2f} | "
            f"Sinal={signal_status} | "
            f"Book(Imb)={imbalance:.4f} "
            f"TotalVol(Bid/Ask)={total_bid:.2f}/{total_ask:.2f} "
            f"AggVol(Buy/Sell)={buy_agg:.2f}/{sell_agg:.2f} "
            f"(levels={order_book_levels})\x1b[0m"
        )

        # 11) Reversão pura: se há posição aberta e sinal oposto ———
        selected_pos = get_open_position(config, future_symbol)
        if selected_pos:
            pos_qty = float(selected_pos.get("positionAmt", 0))
            # se sinal for contra a posição atual:
            if (pos_qty > 0 and signal_status == "SHORT") or (
                pos_qty < 0 and signal_status == "LONG"
            ):
                log_callback(
                    f"[REVERSÃO] Fechando posição atual para inverter para {signal_status}"
                )
                finalize_position(
                    fechar_posicao_por_reversao,
                    future_symbol,
                    "sell" if pos_qty > 0 else "buy",
                    abs(pos_qty),
                    float(selected_pos.get("entryPrice", last_entry_price)),
                    current_price,
                    exchange,
                    status_callback,
                    "Reversão de Sinal: fechando antes de reabrir…",
                )
                # após fechar, executa a nova entrada
                executed = execute_trade(
                    future_symbol,
                    signal_status,
                    margin,
                    None,
                    exchange,
                    status_callback,
                )
                if executed:
                    signal_count += 1
                    log_callback(
                        f"[REVERSÃO] Nova entrada {signal_status} executada ({signal_count}/{max_signals})."
                    )
                continue

        # ============================
        # 11.1) BLOCO DE ENTRADAS (e log de posição)
        current_time = time.time()  # ← aqui você garante que current_time existe

        # Busca posição real
        selected_pos = get_open_position(config, future_symbol)
        if selected_pos:
            pos_qty = float(selected_pos.get("positionAmt", 0))
        else:
            pos_qty = 0.0

        # Atualiza a variável global para não ficar None
        last_order_qty = pos_qty

        # Define direção
        if abs(pos_qty) < 1e-8:
            direcao = "NENHUMA"
        elif pos_qty > 0:
            direcao = "LONG"
        else:
            direcao = "SHORT"

        # Log de posição
        log_callback(f"[POSIÇÃO] Quantidade={pos_qty:.4f} | Direção={direcao}")

        # Se não há posição, podemos tentar entrar até max_signals vezes
        if last_order_qty is None or abs(last_order_qty) < 1e-8:
            # Impede novos sinais antes de 5 minutos
            if (current_time - last_order_time) < 300:
                log_callback(
                    "[SINAL] Ignorado: intervalo de 5 minutos não decorrido desde a última ordem."
                )
            else:
                # ── Sinais dos candles de comparação ────────────────────────────────
                if comp_close > comp_open:
                    comp_signal = "LONG"
                elif comp_close < comp_open:
                    comp_signal = "SHORT"
                else:
                    comp_signal = "NEUTRO"

                # ── Sinais do candle de confirmação ─────────────────────────────────
                if confirm_candle["close"] > confirm_candle["open"]:
                    conf_signal = "LONG"
                elif confirm_candle["close"] < confirm_candle["open"]:
                    conf_signal = "SHORT"
                else:
                    conf_signal = "NEUTRO"

                # ── Log dos TimeFrames ───────────────────────────────────────────────
                log_callback(
                    f"[TIMEFRAME] Comparação={comp_signal} Confirmação={conf_signal}"
                )

                # ── Verifica se cada TimeFrame confere com o signal_status desejado ──
                comp_ok = comp_signal == signal_status
                conf_ok = conf_signal == signal_status

                # ➡️ Apenas novos sinais se habilitado e dentro do limite
                if (
                    signal_status in ["LONG", "SHORT"]
                    and comp_ok
                    and conf_ok
                    and NOVOS_SINAIS_ENABLED
                    and signal_count < max_signals
                ):

                    executed = execute_trade(
                        future_symbol,
                        signal_status,
                        margin,
                        None,
                        exchange,
                        status_callback,
                    )
                    if executed:
                        # marca hora da ordem e incrementa contador
                        last_order_time = current_time
                        signal_count += 1
                        log_callback(
                            f"[SINAL] Entrada {signal_status} executada ({signal_count}ª vez)."
                        )
                        # Reinicia a barreira para recriação a partir da distância inicial
                        active_stop_gain_data = None
                    else:
                        log_callback(
                            f"[SINAL] Limite de novos sinais ({max_signals}) atingido; aguardando posição fechada."
                        )

        # --------------------------------------------------------------------
        # 12) BLOCO DE GESTÃO DE POSIÇÃO (se existir posição) -----------------
        # --------------------------------------------------------------------
        selected_pos = get_open_position(config, future_symbol)
        if selected_pos:
            pos_qty = float(selected_pos.get("positionAmt", 0))
            entry_price = float(selected_pos.get("entryPrice", 0)) or last_entry_price
            unrealized = float(selected_pos.get("unRealizedProfit", 0))
            position_margin = float(selected_pos.get("positionInitialMargin", 0))
            roi = (unrealized / position_margin) * 100 if position_margin else 0
            last_roi = roi

            # → 1) Log do ROI recém-calculado
            logging.info(
                "[PROTEÇÃO] ROI atualizado: %.2f%% (PnL=%.4f USDT)", roi, unrealized
            )

            # <-- AQUI: atualização de status -->
            status_callback(
                f"Margem Posição= {position_margin:.2f} USDT | "
                f"PnL= {unrealized:.4f} USDT | "
                f"Posição={'LONG' if pos_qty>0 else 'SHORT'} | "
                f"ROI={roi:.2f}%"
            )

            # ---------------------------------- Proteções RSI ----------------
            rsi_valor = rsi14_val

            # ——— Log do RSI de Proteção ———
            log_callback(
                f"[RSI PROTEÇÃO] Valor={rsi14_val:.2f} | "
                f"LimiarMin={rsi_protection_min:.2f} | "
                f"LimiarMax={rsi_protection_max:.2f}"
            )

            if pos_qty > 0 and rsi_valor < rsi_protection_min:
                log_callback(
                    f"[RSI PROTEÇÃO LONG] RSI atual = {rsi_valor:.2f} < limiar {rsi_protection_min:.2f}"
                )
                finalize_position(
                    fechar_posicao_por_rsi_reversao,
                    future_symbol,
                    "sell",
                    abs(pos_qty),
                    entry_price,
                    current_price,
                    exchange,
                    status_callback,
                    "RSI Reversão LONG atingido. Finalizando posição…",
                )
                continue
            if pos_qty < 0 and rsi_valor > rsi_protection_max:
                log_callback(
                    f"[RSI PROTEÇÃO SHORT] RSI atual = {rsi_valor:.2f} > limiar {rsi_protection_max:.2f}"
                )
                finalize_position(
                    fechar_posicao_por_rsi_reversao,
                    future_symbol,
                    "buy",
                    abs(pos_qty),
                    entry_price,
                    current_price,
                    exchange,
                    status_callback,
                    "RSI Reversão SHORT atingido. Finalizando posição…",
                )
                continue

            # ============================
            # 12.4) REPOSIÇÃO DE ORDENS
            # só repõe se ROI negativo e dentro do limite de reposição
            if (
                REPOSICAO_ENABLED
                and roi < reposicao_roi_threshold
                and reposicao_count < max_reposicao_orders
            ):
                log_callback(
                    f"[REPOSIÇÃO] ROI={roi:.2f}% abaixo de {reposicao_roi_threshold:.2f}%; executando reposição #{reposicao_count+1}."
                )
                # determina o side a partir da posição aberta
                # pos_qty vem de get_open_position()
                repos_side = "LONG" if pos_qty > 0 else "SHORT"
                executed = execute_trade(
                    future_symbol,
                    repos_side,
                    margin * reposicao_multiplier,
                    None,
                    exchange,
                    status_callback,
                    is_reposicao=True,
                )
                if executed:
                    reposicao_count += 1
                    log_callback(
                        f"[REPOSIÇÃO] #{reposicao_count}/{max_reposicao_orders} executada."
                    )
                    # reinicia barreira para recriação a partir da distância inicial
                    active_stop_gain_data = None
                else:
                    log_callback("[REPOSIÇÃO] falhou ao executar.")
            elif REPOSICAO_ENABLED and roi < reposicao_roi_threshold:
                log_callback(
                    f"[REPOSIÇÃO] Limite de reposições ({max_reposicao_orders}) atingido."
                )

                # 12.5) PROTEÇÃO POR BARREIRA / TRAILING -------------------
        if selected_pos:
            pos_qty = float(selected_pos.get("positionAmt", 0))
            entry_price = float(selected_pos.get("entryPrice", 0)) or last_entry_price
            unrealized = float(selected_pos.get("unRealizedProfit", 0))
            position_margin = float(selected_pos.get("positionInitialMargin", 0))
            roi = (unrealized / position_margin) * 100 if position_margin else 0

            # inicializa o data dict se faltar
            if active_stop_gain_data is None:
                active_stop_gain_data = {
                    "order_id": None,
                    "barrier": None,
                    "max_price": None,
                    "min_price": None,
                    "init_time": time.time(),
                    "reduced_once": False,
                    "trailing_active": False,
                }

            # escolhe a distância de stop conforme estágio
            if not active_stop_gain_data["reduced_once"] and roi >= roi_reduzir:
                active_stop_gain_data["reduced_once"] = True
                stop_distance = distance / 2
            elif (
                not active_stop_gain_data["trailing_active"]
                and roi >= roi_trailing_activation
            ):
                active_stop_gain_data["trailing_active"] = True
                stop_distance = current_price * trailing_stop_percent
            elif active_stop_gain_data["trailing_active"]:
                stop_distance = current_price * trailing_stop_percent
            else:
                stop_distance = distance

            # efetivamente atualiza (ou cria) a ordem de barrier/trailing
            active_stop_gain_data = update_stop_gain_order(
                future_symbol,
                "sell" if pos_qty > 0 else "buy",
                pos_qty,
                entry_price,
                current_price,
                exchange,
                active_stop_gain_data,
                stop_distance=stop_distance,
            )

            # agora faz a verificação de barrier para fechar a posição
            barrier = active_stop_gain_data.get("barrier")
            if barrier is not None:
                tol = 0.0005  # 0,05% de tolerância
                if pos_qty > 0:
                    adjusted = barrier * (1 + tol)
                    logging.info(
                        "Verificação Barreira (LONG): barrier=%.4f, adjusted=%.4f, price=%.4f",
                        barrier,
                        adjusted,
                        current_price,
                    )
                    if current_price <= adjusted:
                        finalize_position(
                            fechar_posicao_por_barreira,
                            future_symbol,
                            "sell",
                            abs(pos_qty),
                            entry_price,
                            current_price,
                            exchange,
                            status_callback,
                            "Condição Barreira LONG atingida. Finalizando posição…",
                        )
                        continue
                else:
                    adjusted = barrier * (1 - tol)
                    logging.info(
                        "Verificação Barreira (SHORT): barrier=%.4f, adjusted=%.4f, price=%.4f",
                        barrier,
                        adjusted,
                        current_price,
                    )
                    if current_price >= adjusted:
                        finalize_position(
                            fechar_posicao_por_barreira,
                            future_symbol,
                            "buy",
                            abs(pos_qty),
                            entry_price,
                            current_price,
                            exchange,
                            status_callback,
                            "Condição Barreira SHORT atingida. Finalizando posição…",
                        )
                        continue

            # ---------------------------------- ROI Stop-loss / Stop-win -----
            # fecha se ROI estiver abaixo do limiar negativo (ex: roi <= -30)
            if roi <= roi_stop_loss_threshold:
                finalize_position(
                    fechar_posicao_por_roi_stop_loss,
                    future_symbol,
                    "sell" if pos_qty > 0 else "buy",
                    abs(pos_qty),
                    entry_price,
                    current_price,
                    exchange,
                    status_callback,
                    "ROI Stop-Loss atingido. Finalizando posição…",
                )
                continue
            if roi >= roi_stop_win_threshold:
                finalize_position(
                    fechar_posicao_por_roi_stop_win,
                    future_symbol,
                    "sell" if pos_qty > 0 else "buy",
                    abs(pos_qty),
                    entry_price,
                    current_price,
                    exchange,
                    status_callback,
                    "ROI Stop-Win atingido. Finalizando posição…",
                )
                continue

            # --------------------------------------------------------------------
            # 13) PEQUENA PAUSA / sync com WS, checando stop_event de novo
            # --------------------------------------------------------------------
            ws_event_main.wait(timeout=0.1)
            ws_event_main.clear()
            # rechecagem de parada após o wait
            if stop_event and stop_event.is_set():
                if log_callback:
                    log_callback(STOP_MSG + " (via post-wait)")
                if status_callback:
                    status_callback("Encerrado OK!")
                break
            # volta pro topo do while

            # Fim do loop while True do run_realtime


# ============================================================================
# ---------------------------- Classe para Logs ------------------------------
class TextHandler(logging.Handler):

    ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")

    def __init__(self, text_widget: tk.Text, auto_scroll: bool = True):
        super().__init__()
        self.text_widget = text_widget
        self.auto_scroll = auto_scroll

        # define as tags de cor
        self.text_widget.tag_config("GREEN", foreground="green")
        self.text_widget.tag_config("RED", foreground="red")

    def emit(self, record: logging.LogRecord):
        try:
            # formata e já inclui o ANSI codes na variável raw
            raw = self.format(record) + "\n"
            # limpa o ANSI para exibir no widget
            clean = self.ANSI_ESCAPE.sub("", raw)

            # decide a tag pela presença do escape code
            tag = None
            if "\x1b[32m" in raw:
                tag = "GREEN"
            elif "\x1b[31m" in raw:
                tag = "RED"
            else:
                # fallback: procura pelos logs que não têm ANSI
                if "Sinal LONG detectado" in clean or "Posição atual: LONG" in clean:
                    tag = "GREEN"
                elif (
                    "Sinal SHORT detectado" in clean or "Posição atual: SHORT" in clean
                ):
                    tag = "RED"

            # insere no widget
            self.text_widget.configure(state="normal")
            if tag:
                self.text_widget.insert("end", clean, tag)
            else:
                self.text_widget.insert("end", clean)

            if self.auto_scroll:
                self.text_widget.yview("end")
            self.text_widget.configure(state="disabled")

        except Exception:
            self.handleError(record)


# ============================================================================
# ------------------------- Configuração da Interface ------------------------
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720

ativos = [
    "1000BONK/USDT",
    "1000PEPE/USDT",
    "1000SHIB/USDT",
    "AI16Z/USDT",
    "AAVE/USDT",
    "AIXBT/USDT",
    "ADA/USDT",
    "ARC/USDT",
    "AVAX/USDT",
    "AUCTION/USDT",
    "BAKE/USDT",
    "B3/USDT",
    "BERA/USDT",
    "BNB/USDT",
    "BNX/USDT",
    "BTC/USDT",
    "CAKE/USDT",
    "CRV/USDT",
    "DOGE/USDT",
    "DOT/USDT",
    "ENA/USDT",
    "ETH/USDT",
    "FARTCOIN/USDT",
    "HEIU/USDT",
    "HBAR/USDT",
    "IPU/USDT",
    "JTO/USDT",
    "JUPU/USDT",
    "LAYER/USDT",
    "LDO/USDT",
    "LINK/USDT",
    "LTC/USDT",
    "ME/USDT",
    "NEAR/USDT",
    "NEIRO/USDT",
    "NOT/USDT",
    "OM/USDT",
    "ONDO/USDT",
    "PENGU/USDT",
    "PNUT/USDT",
    "POPCAT/USDT",
    "SOLU/USDT",
    "TAO/USDT",
    "TST/USDT",
    "TRUMP/USDT",
    "TRX/USDT",
    "THE/USDT",
    "VIRTUAL/USDT",
    "VINE/USDT",
    "VVV/USDT",
    "WIF/USDT",
    "WLD/USDT",
    "XLM/USDT",
    "XRP/USDT",
]


# ============================================================================
# -------------------------- Classe TradingRobotGUI --------------------------
class TradingRobotGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        # <<< Adicione esta linha para inicializar o log interno >>>
        self.log_content = ""
        self.robot_thread = None
        self.stop_event = threading.Event()
        self.telegram_bot_token_var = ctk.StringVar(value=TELEGRAM_BOT_TOKEN)
        self.telegram_chat_id_var = ctk.StringVar(value="")
        config = load_Telegram_Config_Futures()
        self.telegram_chat_id_var.set(config.get("chat_id", ""))

        self.title("TrendMax-Futures - Configurações - Suporte (44)99113-2217")
        self.minsize(WINDOW_WIDTH, WINDOW_HEIGHT)
        if sys.platform.startswith("win"):
            self.after(100, lambda: self.state("zoomed"))
        else:
            self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")

        self.shutdown_requested = False

        self.top_buttons_frame = ctk.CTkFrame(self)
        self.top_buttons_frame.pack(pady=5)
        self.info_button = ctk.CTkButton(
            self.top_buttons_frame,
            text="Informações",
            command=self.show_info,
            font=DEFAULT_FONT,
            width=120,
            height=30,
        )
        self.info_button.pack(side="left", padx=5)
        self.license_button = ctk.CTkButton(
            self.top_buttons_frame,
            text="Minha Licença",
            command=self.minhas_licencas,
            font=DEFAULT_FONT,
            width=120,
            height=30,
        )
        self.license_button.pack(side="left", padx=5)
        self.telegram_button = ctk.CTkButton(
            self.top_buttons_frame,
            text="Telegram",
            command=self.show_Telegram_Config_Futures,
            font=DEFAULT_FONT,
            width=120,
            height=30,
        )
        self.telegram_button.pack(side="left", padx=5)

        self.config_frame = ctk.CTkFrame(self, corner_radius=10)
        self.config_frame.pack(padx=10, pady=5, fill="x")

        self.search_label = ctk.CTkLabel(
            self.config_frame, text="Buscar o Ativo:", font=DEFAULT_FONT
        )
        self.search_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.search_var = ctk.StringVar()
        self.search_entry = ctk.CTkEntry(
            self.config_frame,
            textvariable=self.search_var,
            width=120,
            font=DEFAULT_FONT,
        )
        self.search_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        self.search_entry.bind("<KeyRelease>", self.filter_symbols)

        self.future_symbol_label = ctk.CTkLabel(
            self.config_frame, text="Selecione o Ativo:", font=DEFAULT_FONT
        )
        self.future_symbol_label.grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.future_symbol_var = ctk.StringVar(value="BTC/USDT")
        self.future_symbol_combo = ctk.CTkComboBox(
            self.config_frame,
            values=ativos,
            variable=self.future_symbol_var,
            width=120,
            font=("Arial", 10),
            dropdown_font=("Arial", 10),
            state="normal",
        )
        self.future_symbol_combo.grid(row=0, column=3, padx=5, pady=5, sticky="w")
        self.future_symbol_combo.bind("<<ComboboxSelected>>", self.clear_search)
        self.future_symbol_var.trace("w", self.clear_search)

        self.lot_value_label = ctk.CTkLabel(
            self.config_frame, text="Margem (USDT):", font=DEFAULT_FONT
        )
        self.lot_value_label.grid(row=0, column=4, padx=5, pady=5, sticky="w")
        self.lot_value_var = ctk.StringVar(value="2")
        self.lot_value_entry = ctk.CTkEntry(
            self.config_frame,
            textvariable=self.lot_value_var,
            width=80,
            font=DEFAULT_FONT,
        )
        self.lot_value_entry.grid(row=0, column=5, padx=5, pady=5, sticky="w")
        self.lot_value_entry.bind(
            "<FocusOut>", lambda e: self.check_empty(self.lot_value_var, "2")
        )
        self.lot_value_entry.bind(
            "<KeyRelease>", lambda e: self.sanitize_numeric(self.lot_value_var)
        )

        self.leverage_label = ctk.CTkLabel(
            self.config_frame, text="Alavancagem (X):", font=DEFAULT_FONT
        )
        self.leverage_label.grid(row=0, column=6, padx=5, pady=5, sticky="w")
        self.leverage_var = ctk.StringVar(value="125")
        self.leverage_entry = ctk.CTkEntry(
            self.config_frame,
            textvariable=self.leverage_var,
            width=80,
            font=DEFAULT_FONT,
        )
        self.leverage_entry.grid(row=0, column=7, padx=5, pady=5, sticky="w")
        self.leverage_entry.bind(
            "<FocusOut>", lambda e: self.check_empty(self.leverage_var, "125")
        )
        self.leverage_entry.bind(
            "<KeyRelease>", lambda e: self.sanitize_integer(self.leverage_var)
        )

        self.operational_tf_label = ctk.CTkLabel(
            self.config_frame, text="TimeFrame Operacional:", font=DEFAULT_FONT
        )
        self.operational_tf_label.grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.timeframe_options = [
            "1m",
            "3m",
            "5m",
            "15m",
            "30m",
            "1h",
            "2h",
            "4h",
            "6h",
            "8h",
            "12h",
            "1d",
        ]
        self.operational_tf_var = ctk.StringVar(value="15m")
        self.operational_tf_menu = ctk.CTkOptionMenu(
            self.config_frame,
            variable=self.operational_tf_var,
            values=self.timeframe_options,
            font=DEFAULT_FONT,
            width=80,
        )
        self.operational_tf_menu.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        self.timeframe_label = ctk.CTkLabel(
            self.config_frame, text="TimeFrame de Comparação:", font=DEFAULT_FONT
        )
        self.timeframe_label.grid(row=1, column=2, padx=5, pady=5, sticky="w")
        self.timeframe_options = [
            "1m",
            "3m",
            "5m",
            "15m",
            "30m",
            "1h",
            "2h",
            "4h",
            "6h",
            "8h",
            "12h",
            "1d",
        ]
        self.timeframe_var = ctk.StringVar(value="5m")
        self.timeframe_menu = ctk.CTkOptionMenu(
            self.config_frame,
            variable=self.timeframe_var,
            values=self.timeframe_options,
            font=DEFAULT_FONT,
            width=80,
        )
        self.timeframe_menu.grid(row=1, column=3, padx=5, pady=5, sticky="w")

        self.confirmation_tf_label = ctk.CTkLabel(
            self.config_frame, text="TimeFrame Confirmação:", font=DEFAULT_FONT
        )
        self.confirmation_tf_label.grid(row=1, column=4, padx=5, pady=5, sticky="w")
        self.timeframe_options = [
            "1m",
            "3m",
            "5m",
            "15m",
            "30m",
            "1h",
            "2h",
            "4h",
            "6h",
            "8h",
            "12h",
            "1d",
        ]
        self.confirmation_tf_var = ctk.StringVar(value="1m")
        self.confirmation_tf_menu = ctk.CTkOptionMenu(
            self.config_frame,
            variable=self.confirmation_tf_var,
            values=self.timeframe_options,
            font=DEFAULT_FONT,
            width=80,
        )
        self.confirmation_tf_menu.grid(row=1, column=5, padx=5, pady=5, sticky="w")

        self.confirmation_tolerance_label = ctk.CTkLabel(
            self.config_frame, text="Tolerância Confirmação (%):", font=DEFAULT_FONT
        )
        self.confirmation_tolerance_label.grid(
            row=1, column=6, padx=5, pady=5, sticky="w"
        )
        self.confirmation_tolerance_var = ctk.StringVar(value="5")
        self.confirmation_tolerance_entry = ctk.CTkEntry(
            self.config_frame,
            textvariable=self.confirmation_tolerance_var,
            width=80,
            font=DEFAULT_FONT,
        )
        self.confirmation_tolerance_entry.grid(
            row=1, column=7, padx=5, pady=5, sticky="w"
        )
        self.confirmation_tolerance_entry.bind(
            "<FocusOut>",
            lambda e: self.check_empty(self.confirmation_tolerance_var, "5"),
        )
        self.confirmation_tolerance_entry.bind(
            "<KeyRelease>",
            lambda e: self.sanitize_numeric(self.confirmation_tolerance_var),
        )

        self.max_signals_label = ctk.CTkLabel(
            self.config_frame, text="Max. Novos Sinais:", font=DEFAULT_FONT
        )
        self.max_signals_label.grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.max_signals_var = ctk.StringVar(value="4")
        self.max_signals_entry = ctk.CTkEntry(
            self.config_frame,
            textvariable=self.max_signals_var,
            width=80,
            font=DEFAULT_FONT,
        )
        self.max_signals_entry.grid(row=2, column=1, padx=5, pady=5, sticky="w")
        self.max_signals_entry.bind(
            "<FocusOut>", lambda e: self.check_empty(self.max_signals_var, "4")
        )
        self.max_signals_entry.bind(
            "<KeyRelease>", lambda e: self.sanitize_integer(self.max_signals_var)
        )

        self.max_reposição_label = ctk.CTkLabel(
            self.config_frame, text="Max. Reposição Ordens:", font=DEFAULT_FONT
        )
        self.max_reposição_label.grid(row=2, column=2, padx=5, pady=5, sticky="w")
        self.max_reposição_var = ctk.StringVar(value="1")
        self.max_reposição_entry = ctk.CTkEntry(
            self.config_frame,
            textvariable=self.max_reposição_var,
            width=80,
            font=DEFAULT_FONT,
        )
        self.max_reposição_entry.grid(row=2, column=3, padx=5, pady=5, sticky="w")
        self.max_reposição_entry.bind(
            "<FocusOut>", lambda e: self.check_empty(self.max_reposição_var, "1")
        )
        self.max_reposição_entry.bind(
            "<KeyRelease>", lambda e: self.sanitize_integer(self.max_reposição_var)
        )

        self.reposicao_multiplier_label = ctk.CTkLabel(
            self.config_frame, text="Multiplicador de Reposição:", font=DEFAULT_FONT
        )
        self.reposicao_multiplier_label.grid(
            row=2, column=4, padx=5, pady=5, sticky="w"
        )
        self.reposicao_multiplier_var = ctk.StringVar(value="1.1")
        self.reposicao_multiplier_entry = ctk.CTkEntry(
            self.config_frame,
            textvariable=self.reposicao_multiplier_var,
            width=80,
            font=DEFAULT_FONT,
        )
        self.reposicao_multiplier_entry.grid(
            row=2, column=5, padx=5, pady=5, sticky="w"
        )
        self.reposicao_multiplier_entry.bind(
            "<FocusOut>",
            lambda e: self.check_empty(self.reposicao_multiplier_var, "1.1"),
        )
        self.reposicao_multiplier_entry.bind(
            "<KeyRelease>",
            lambda e: self.sanitize_numeric(self.reposicao_multiplier_var),
        )

        self.reposicao_roi_label = ctk.CTkLabel(
            self.config_frame, text="ROI (-%) Reposição Ordens:", font=DEFAULT_FONT
        )
        self.reposicao_roi_label.grid(row=2, column=6, padx=5, pady=5, sticky="w")
        self.reposicao_roi_var = ctk.StringVar(value="-25")
        self.reposicao_roi_entry = ctk.CTkEntry(
            self.config_frame,
            textvariable=self.reposicao_roi_var,
            width=80,
            font=DEFAULT_FONT,
        )
        self.reposicao_roi_entry.grid(row=2, column=7, padx=5, pady=5, sticky="w")
        self.reposicao_roi_entry.bind(
            "<FocusOut>", lambda e: self._ensure_negative(self.reposicao_roi_var)
        )
        self.reposicao_roi_entry.bind(
            "<KeyRelease>", lambda e: self.sanitize_numeric(self.reposicao_roi_var)
        )

        self.initial_barrier_label = ctk.CTkLabel(
            self.config_frame, text="Barreira INICIAL (Pontos):", font=DEFAULT_FONT
        )
        self.initial_barrier_label.grid(row=3, column=0, padx=5, pady=5, sticky="w")
        self.initial_barrier_var = ctk.StringVar(value="400")
        self.initial_barrier_entry = ctk.CTkEntry(
            self.config_frame,
            textvariable=self.initial_barrier_var,
            width=80,
            font=DEFAULT_FONT,
        )
        self.initial_barrier_entry.grid(row=3, column=1, padx=5, pady=5, sticky="w")
        self.initial_barrier_entry.bind(
            "<FocusOut>", lambda e: self.check_empty(self.initial_barrier_var, "400")
        )
        self.initial_barrier_entry.bind(
            "<KeyRelease>", lambda e: self.sanitize_numeric(self.initial_barrier_var)
        )

        self.roi_reduzir_label = ctk.CTkLabel(
            self.config_frame, text="ROI (+%) Reduzir Distância /2:", font=DEFAULT_FONT
        )
        self.roi_reduzir_label.grid(row=3, column=2, padx=5, pady=5, sticky="w")
        self.roi_reduzir_var = ctk.StringVar(value="25")
        self.roi_reduzir_entry = ctk.CTkEntry(
            self.config_frame,
            textvariable=self.roi_reduzir_var,
            width=80,
            font=DEFAULT_FONT,
        )
        self.roi_reduzir_entry.grid(row=3, column=3, padx=5, pady=5, sticky="w")
        self.roi_reduzir_entry.bind(
            "<KeyRelease>", lambda e: self.sanitize_numeric(self.roi_reduzir_var)
        )

        self.roi_trailing_activation_label = ctk.CTkLabel(
            self.config_frame, text="ROI (+%) Ativar Trailing Stop:", font=DEFAULT_FONT
        )
        self.roi_trailing_activation_label.grid(
            row=3, column=4, padx=5, pady=5, sticky="w"
        )
        self.roi_trailing_activation_var = ctk.StringVar(value="50")
        self.roi_trailing_activation_entry = ctk.CTkEntry(
            self.config_frame,
            textvariable=self.roi_trailing_activation_var,
            width=80,
            font=DEFAULT_FONT,
        )
        self.roi_trailing_activation_entry.grid(
            row=3, column=5, padx=5, pady=5, sticky="w"
        )
        self.roi_trailing_activation_entry.bind(
            "<FocusOut>",
            lambda e: self.check_empty(self.roi_trailing_activation_var, "50"),
        )
        self.roi_trailing_activation_entry.bind(
            "<KeyRelease>",
            lambda e: self.sanitize_numeric(self.roi_trailing_activation_var),
        )

        self.trailing_stop_label = ctk.CTkLabel(
            self.config_frame, text="Distância Trailing Stop (%):", font=DEFAULT_FONT
        )
        self.trailing_stop_label.grid(row=3, column=6, padx=5, pady=5, sticky="w")
        self.trailing_stop_var = ctk.StringVar(value="0.00118")
        self.trailing_stop_entry = ctk.CTkEntry(
            self.config_frame,
            textvariable=self.trailing_stop_var,
            width=80,
            font=DEFAULT_FONT,
        )
        self.trailing_stop_entry.grid(row=3, column=7, padx=5, pady=5, sticky="w")
        self.trailing_stop_entry.bind(
            "<KeyRelease>", lambda e: self.sanitize_numeric(self.trailing_stop_var)
        )

        self.roi_stop_loss_label = ctk.CTkLabel(
            self.config_frame, text="ROI (-%) Stop Loss:", font=DEFAULT_FONT
        )
        self.roi_stop_loss_label.grid(row=4, column=0, padx=5, pady=5, sticky="w")
        self.roi_stop_loss_threshold_var = ctk.StringVar(value="-50")
        self.roi_stop_loss_entry = ctk.CTkEntry(
            self.config_frame,
            textvariable=self.roi_stop_loss_threshold_var,
            width=80,
            font=DEFAULT_FONT,
        )
        self.roi_stop_loss_entry.grid(row=4, column=1, padx=5, pady=5, sticky="w")
        self.roi_stop_loss_entry.bind(
            "<FocusOut>",
            lambda e: self._ensure_negative(self.roi_stop_loss_threshold_var),
        )
        self.roi_stop_loss_entry.bind(
            "<KeyRelease>",
            lambda e: self.sanitize_numeric(self.roi_stop_loss_threshold_var),
        )

        self.roi_threshold_win_label = ctk.CTkLabel(
            self.config_frame, text="ROI (+%) Stop Win:", font=DEFAULT_FONT
        )
        self.roi_threshold_win_label.grid(row=4, column=2, padx=5, pady=5, sticky="w")
        self.roi_stop_win_threshold_var = ctk.StringVar(value="100")
        self.roi_threshold_win_entry = ctk.CTkEntry(
            self.config_frame,
            textvariable=self.roi_stop_win_threshold_var,
            width=80,
            font=DEFAULT_FONT,
        )
        self.roi_threshold_win_entry.grid(row=4, column=3, padx=5, pady=5, sticky="w")
        self.roi_threshold_win_entry.bind(
            "<KeyRelease>",
            lambda e: self.sanitize_numeric(self.roi_stop_win_threshold_var),
        )

        self.adx_threshold_label = ctk.CTkLabel(
            self.config_frame, text="Limite do ADX:", font=DEFAULT_FONT
        )
        self.adx_threshold_label.grid(row=4, column=4, padx=5, pady=5, sticky="w")
        self.adx_threshold_var = ctk.StringVar(value="25")
        self.adx_threshold_entry = ctk.CTkEntry(
            self.config_frame,
            textvariable=self.adx_threshold_var,
            width=80,
            font=DEFAULT_FONT,
        )
        self.adx_threshold_entry.grid(row=4, column=5, padx=5, pady=5, sticky="w")
        self.adx_threshold_entry.bind(
            "<KeyRelease>", lambda e: self.sanitize_numeric(self.adx_threshold_var)
        )

        self.ml_confidence_label = ctk.CTkLabel(
            self.config_frame, text="Limiar Confiança ML (%):", font=DEFAULT_FONT
        )
        self.ml_confidence_label.grid(row=4, column=6, padx=5, pady=5, sticky="w")
        self.ml_confidence_var = ctk.StringVar(value="55")
        self.ml_confidence_entry = ctk.CTkEntry(
            self.config_frame,
            textvariable=self.ml_confidence_var,
            width=80,
            font=DEFAULT_FONT,
        )
        self.ml_confidence_entry.grid(row=4, column=7, padx=5, pady=5, sticky="w")
        self.ml_confidence_entry.bind(
            "<FocusOut>", lambda e: self.check_empty(self.ml_confidence_var, "55")
        )
        self.ml_confidence_entry.bind(
            "<KeyRelease>", lambda e: self.sanitize_numeric(self.ml_confidence_var)
        )

        self.rsi_protection_min_label = ctk.CTkLabel(
            self.config_frame, text="RSI Proteção Reversão LONG:", font=DEFAULT_FONT
        )
        self.rsi_protection_min_label.grid(row=5, column=0, padx=5, pady=5, sticky="w")
        self.rsi_protection_min_var = ctk.StringVar(value="30")
        self.rsi_protection_min_entry = ctk.CTkEntry(
            self.config_frame,
            textvariable=self.rsi_protection_min_var,
            width=80,
            font=DEFAULT_FONT,
        )
        self.rsi_protection_min_entry.grid(row=5, column=1, padx=5, pady=5, sticky="w")
        self.rsi_protection_min_entry.bind(
            "<FocusOut>", lambda e: self.check_empty(self.rsi_protection_min_var, "30")
        )
        self.rsi_protection_min_entry.bind(
            "<KeyRelease>", lambda e: self.sanitize_numeric(self.rsi_protection_min_var)
        )

        self.rsi_protection_max_label = ctk.CTkLabel(
            self.config_frame, text="RSI Proteção Reversão SHORT:", font=DEFAULT_FONT
        )
        self.rsi_protection_max_label.grid(row=5, column=2, padx=5, pady=5, sticky="w")
        self.rsi_protection_max_var = ctk.StringVar(value="70")
        self.rsi_protection_max_entry = ctk.CTkEntry(
            self.config_frame,
            textvariable=self.rsi_protection_max_var,
            width=80,
            font=DEFAULT_FONT,
        )
        self.rsi_protection_max_entry.grid(row=5, column=3, padx=5, pady=5, sticky="w")
        self.rsi_protection_max_entry.bind(
            "<FocusOut>", lambda e: self.check_empty(self.rsi_protection_max_var, "70")
        )
        self.rsi_protection_max_entry.bind(
            "<KeyRelease>", lambda e: self.sanitize_numeric(self.rsi_protection_max_var)
        )

        self.order_book_levels_label = ctk.CTkLabel(
            self.config_frame, text="Níveis do Book:", font=DEFAULT_FONT
        )
        self.order_book_levels_label.grid(row=5, column=4, padx=5, pady=5, sticky="w")
        self.order_book_levels_var = ctk.StringVar(value="5")
        self.order_book_levels_entry = ctk.CTkEntry(
            self.config_frame,
            textvariable=self.order_book_levels_var,
            width=80,
            font=DEFAULT_FONT,
        )
        self.order_book_levels_entry.grid(row=5, column=5, padx=5, pady=5, sticky="w")
        self.order_book_levels_entry.bind(
            "<FocusOut>", lambda e: self.check_empty(self.order_book_levels_var, "5")
        )
        self.order_book_levels_entry.bind(
            "<KeyRelease>", lambda e: self.sanitize_numeric(self.order_book_levels_var)
        )

        self.indicator_period_label = ctk.CTkLabel(
            self.config_frame, text="Período dos Indicadores:", font=DEFAULT_FONT
        )
        self.indicator_period_label.grid(row=6, column=0, padx=5, pady=5, sticky="w")
        self.indicator_period_var = ctk.StringVar(value="14")
        self.indicator_period_entry = ctk.CTkEntry(
            self.config_frame,
            textvariable=self.indicator_period_var,
            width=80,
            font=DEFAULT_FONT,
        )
        self.indicator_period_entry.grid(row=6, column=1, padx=5, pady=5, sticky="w")
        self.indicator_period_entry.bind(
            "<FocusOut>", lambda e: self.check_empty(self.indicator_period_var, "14")
        )
        self.indicator_period_entry.bind(
            "<KeyRelease>", lambda e: self.sanitize_numeric(self.indicator_period_var)
        )

        self.imbalance_long_label = ctk.CTkLabel(
            self.config_frame, text="Imbalance Long:", font=DEFAULT_FONT
        )
        self.imbalance_long_label.grid(row=6, column=2, padx=5, pady=5, sticky="w")
        self.imbalance_long_var = ctk.StringVar(value="0.3")
        self.imbalance_long_entry = ctk.CTkEntry(
            self.config_frame,
            textvariable=self.imbalance_long_var,
            width=80,
            font=DEFAULT_FONT,
        )
        self.imbalance_long_entry.grid(row=6, column=3, padx=5, pady=5, sticky="w")
        self.imbalance_long_entry.bind(
            "<FocusOut>", lambda e: self.check_empty(self.imbalance_long_var, "0.3")
        )
        self.imbalance_long_entry.bind(
            "<KeyRelease>", lambda e: self.sanitize_numeric(self.imbalance_long_var)
        )

        self.imbalance_short_label = ctk.CTkLabel(
            self.config_frame, text="Imbalance Short:", font=DEFAULT_FONT
        )
        self.imbalance_short_label.grid(row=6, column=4, padx=5, pady=5, sticky="w")
        self.imbalance_short_var = ctk.StringVar(value="-0.3")
        self.imbalance_short_entry = ctk.CTkEntry(
            self.config_frame,
            textvariable=self.imbalance_short_var,
            width=80,
            font=DEFAULT_FONT,
        )
        self.imbalance_short_entry.grid(row=6, column=5, padx=5, pady=5, sticky="w")
        self.imbalance_short_entry.bind(
            "<FocusOut>", lambda e: self.check_empty(self.imbalance_short_var, "-0.3")
        )
        self.imbalance_short_entry.bind(
            "<KeyRelease>", lambda e: self.sanitize_numeric(self.imbalance_short_var)
        )

        self.margin_mode_label = ctk.CTkLabel(
            self.config_frame, text="Modo de Margem:", font=DEFAULT_FONT
        )
        self.margin_mode_label.grid(row=7, column=0, padx=5, pady=5, sticky="w")
        self.margin_mode_var = ctk.StringVar(value="CROSSED")
        self.isolated_radiobutton = ctk.CTkRadioButton(
            self.config_frame,
            text="Isolado",
            variable=self.margin_mode_var,
            value="ISOLATED",
            font=DEFAULT_FONT,
        )
        self.isolated_radiobutton.grid(row=7, column=1, padx=5, pady=5, sticky="w")
        self.crossed_radiobutton = ctk.CTkRadioButton(
            self.config_frame,
            text="Cruzado",
            variable=self.margin_mode_var,
            value="CROSSED",
            font=DEFAULT_FONT,
        )
        self.crossed_radiobutton.grid(row=7, column=2, padx=5, pady=5, sticky="w")

        self.enable_novos_sinais_label = ctk.CTkLabel(
            self.config_frame, text="Ativar Novos Sinais:", font=DEFAULT_FONT
        )
        self.enable_novos_sinais_label.grid(row=7, column=3, padx=5, pady=5, sticky="w")
        self.enable_novos_sinais_var = ctk.BooleanVar(value=True)
        self.enable_novos_sinais_checkbox = ctk.CTkCheckBox(
            self.config_frame,
            variable=self.enable_novos_sinais_var,
            text="",
            font=DEFAULT_FONT,
        )
        self.enable_novos_sinais_checkbox.grid(
            row=7, column=4, padx=5, pady=5, sticky="w"
        )
        self.enable_novos_sinais_var.trace("w", self.on_toggle_novos_sinais)

        self.enable_reposição_label = ctk.CTkLabel(
            self.config_frame, text="Ativar Reposição:", font=DEFAULT_FONT
        )
        self.enable_reposição_label.grid(row=7, column=5, padx=5, pady=5, sticky="w")
        self.enable_reposição_var = ctk.BooleanVar(value=True)
        self.enable_reposição_checkbox = ctk.CTkCheckBox(
            self.config_frame,
            variable=self.enable_reposição_var,
            text="",
            font=DEFAULT_FONT,
        )
        self.enable_reposição_checkbox.grid(row=7, column=6, padx=5, pady=5, sticky="w")
        self.enable_reposição_var.trace("w", self.on_toggle_reposicao)

        self.enable_telegram_label = ctk.CTkLabel(
            self.config_frame, text="Ativar Telegram:", font=DEFAULT_FONT
        )
        self.enable_telegram_label.grid(row=7, column=7, padx=5, pady=5, sticky="w")
        self.enable_telegram_var = ctk.BooleanVar(value=True)
        self.enable_telegram_checkbox = ctk.CTkCheckBox(
            self.config_frame,
            variable=self.enable_telegram_var,
            text="",
            font=DEFAULT_FONT,
        )
        self.enable_telegram_checkbox.grid(row=7, column=8, padx=5, pady=5, sticky="w")
        self.enable_telegram_var.trace("w", self.on_toggle_telegram)

        self.status_label = ctk.CTkLabel(
            self, text="Status: Aguardando Início!", font=("Arial", 22)
        )
        self.status_label.pack(pady=5)

        self.keys_frame = ctk.CTkFrame(self, corner_radius=10)
        self.keys_frame.pack(padx=10, pady=5, fill="x")
        self.real_api_key_label = ctk.CTkLabel(
            self.keys_frame, text="REAL API KEY:", font=DEFAULT_FONT
        )
        self.real_api_key_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.real_api_key_var = ctk.StringVar(value="")
        self.real_api_key_entry = ctk.CTkEntry(
            self.keys_frame,
            textvariable=self.real_api_key_var,
            width=465,
            font=DEFAULT_FONT,
        )
        self.real_api_key_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        self.real_api_secret_label = ctk.CTkLabel(
            self.keys_frame, text="REAL API SECRET:", font=DEFAULT_FONT
        )
        self.real_api_secret_label.grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.real_api_secret_var = ctk.StringVar(value="")
        self.real_api_secret_entry = ctk.CTkEntry(
            self.keys_frame,
            textvariable=self.real_api_secret_var,
            width=465,
            font=DEFAULT_FONT,
        )
        self.real_api_secret_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        self.save_credentials_button = ctk.CTkButton(
            self.keys_frame,
            text="Salvar Credenciais",
            command=self.save_credentials,
            font=DEFAULT_FONT,
            width=120,
            height=30,
        )
        self.save_credentials_button.grid(row=3, column=0, padx=5, pady=5, sticky="w")
        self.remove_credentials_button = ctk.CTkButton(
            self.keys_frame,
            text="Remover Credenciais",
            command=self.remove_credentials,
            font=DEFAULT_FONT,
            width=120,
            height=30,
        )
        self.remove_credentials_button.grid(row=3, column=1, padx=5, pady=5, sticky="w")

        self.bottom_buttons_frame = ctk.CTkFrame(self)
        self.bottom_buttons_frame.pack(pady=10)

        # Campo de busca de Logs
        self.log_search_frame = ctk.CTkFrame(self)
        self.log_search_frame.pack(padx=10, pady=(5, 0), fill="x")
        self.log_search_label = ctk.CTkLabel(
            self.log_search_frame, text="Buscar nos Logs:", font=DEFAULT_FONT
        )
        self.log_search_label.pack(side="left", padx=5)
        self.log_search_var = ctk.StringVar()
        self.log_search_entry = ctk.CTkEntry(
            self.log_search_frame,
            textvariable=self.log_search_var,
            width=300,
            font=DEFAULT_FONT,
        )
        self.log_search_entry.pack(side="left", padx=5)
        self.log_search_entry.bind("<KeyRelease>", self.search_logs)

        # Logo abaixo do campo de busca
        self.btn_anterior = ctk.CTkButton(
            self.log_search_frame, text="◀", command=self.anterior_log, width=30
        )
        self.btn_anterior.pack(side="left", padx=2)
        self.btn_proximo = ctk.CTkButton(
            self.log_search_frame, text="▶", command=self.proximo_log, width=30
        )
        self.btn_proximo.pack(side="left", padx=2)

        # Botão para limpar a busca de logs
        self.clear_search_button = ctk.CTkButton(
            self.log_search_frame,
            text="Limpar Busca",
            command=self.clear_search_logs,
            font=DEFAULT_FONT,
            width=100,
            height=30,
        )
        self.clear_search_button.pack(side="left", padx=5)

        self.current_search_index = "1.0"  # posição inicial para a busca

        # ─── Janela de Logs ─────────────────────────────────────────────────
        self.log_text = ctk.CTkTextbox(self, width=1250, height=300, font=SMALL_FONT)
        self.log_text.configure(state="disabled")
        self.log_text.pack(padx=10, pady=10, fill="both", expand=True)

        # já prepara a tag de destaque
        self.log_text.tag_config("highlight", background="#ffff99", foreground="black")

        self.text_handler = TextHandler(self.log_text, auto_scroll=True)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S - "
        )
        self.text_handler.setFormatter(formatter)

        logging.getLogger().addHandler(self.text_handler)

        # Inicializa estes atributos para evitar AttributeError nos callbacks
        self.robot_thread = None
        self.stop_event = threading.Event()

        self.toggle_button = ctk.CTkButton(
            self.bottom_buttons_frame,
            text="Iniciar TrendMax",
            command=self.toggle_robot,
            font=DEFAULT_FONT,
            width=120,
            height=30,
        )
        self.toggle_button.pack(side="left", padx=5)
        # Fechar posição pelo botão na interface
        self.fechar_posicao_button = ctk.CTkButton(
            self.bottom_buttons_frame,
            text="Fechar Posição",
            command=lambda: threading.Thread(
                target=__import__(__name__).fechar_posicao_manual,
                args=(
                    {
                        "real_api_key": self.real_api_key_var.get().strip(),
                        "real_api_secret": self.real_api_secret_var.get().strip(),
                        "future_symbol": self.future_symbol_var.get().strip(),
                    },
                    self.future_symbol_var.get().strip(),  # future_symbol
                    self.real_api_key_var.get().strip(),  # api_key
                    self.real_api_secret_var.get().strip(),  # api_secret
                    self.update_status,  # status_callback
                ),
                daemon=True,
            ).start,
            font=DEFAULT_FONT,
            width=120,
            height=30,
        )
        self.fechar_posicao_button.pack(side="left", padx=5)

        self.autoscroll_button = ctk.CTkButton(
            self.bottom_buttons_frame,
            text="Auto Scroll: ON",
            command=self.toggle_autoscroll,
            font=DEFAULT_FONT,
            width=120,
            height=30,
        )
        self.autoscroll_button.pack(side="left", padx=5)

    def clear_search_logs(self):
        # Se já não há termo, só liga auto-scroll e vai pro fim
        if not self.log_search_var.get().strip():
            self.text_handler.auto_scroll = True
            self.log_text.see("end")
            return

        # caso contrário, limpa e refaz a busca
        self.log_search_var.set("")
        self.search_logs()
        # e garante que, com termo vazio, você volte ao fim
        self.log_text.see("end")

    def search_logs(self, event=None):
        termo = self.log_search_var.get().strip().lower()
        self.text_handler.auto_scroll = not bool(termo)

        # Lê todo o texto que está de fato no widget
        conteudo = self.log_text.get("1.0", "end")

        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")

        # Reinsere todo o conteúdo
        for linha in conteudo.splitlines():
            self.log_text.insert("end", linha + "\n")

        if termo:
            idx = "1.0"
            while True:
                idx = self.log_text.search(termo, idx, nocase=1, stopindex="end")
                if not idx:
                    break
                end_idx = f"{idx}+{len(termo)}c"
                self.log_text.tag_add("highlight", idx, end_idx)
                idx = end_idx

        self.log_text.configure(state="disabled")

    def proximo_log(self):
        termo = self.log_search_var.get().strip()
        if not termo:
            return
        # Inicia a busca a partir da última posição armazenada
        pos = self.log_text.search(
            termo, self.current_search_index, tk.END, nocase=True
        )
        if pos:
            # Atualiza a posição de busca para logo após a ocorrência encontrada
            self.current_search_index = f"{pos}+1c"
            self.log_text.see(pos)
            # Você pode, se desejar, alterar a cor da ocorrência; por exemplo,
            # inserir a tag "highlight" (se for suportada) ou simplesmente rolar até lá.
        else:
            # Se não encontrar, reinicia a busca do início
            self.current_search_index = "1.0"
            pos = self.log_text.search(
                termo, self.current_search_index, tk.END, nocase=True
            )
            if pos:
                self.current_search_index = f"{pos}+1c"
                self.log_text.see(pos)

    def anterior_log(self):
        termo = self.log_search_var.get().strip()
        if not termo:
            return
        # Procura pela ocorrência anterior: para isso, pode ser necessário buscar todas as ocorrências,
        # armazenar as posições em uma lista e encontrar aquela imediatamente anterior à posição atual.
        # Uma abordagem simples é:
        conteudo = self.log_text.get("1.0", tk.END)
        linhas = conteudo.splitlines()
        indices = []
        start_index = "1.0"
        while True:
            pos = self.log_text.search(termo, start_index, tk.END, nocase=True)
            if not pos:
                break
            indices.append(pos)
            start_index = f"{pos}+1c"
        # Se achar ocorrências, encontre a que seja menor que a posição atual (convertendo para números de linha/coluna)
        if indices:
            # Converter a posição atual para uma tupla (linha, coluna)
            current_line = int(
                self.log_text.index(self.current_search_index).split(".")[0]
            )
            # Filtra as ocorrências cuja linha seja menor que a atual
            occ_prev = [idx for idx in indices if int(idx.split(".")[0]) < current_line]
            if occ_prev:
                # Seleciona a última (a mais próxima antes da posição atual)
                pos = occ_prev[-1]
                self.current_search_index = f"{pos}+1c"
                self.log_text.see(pos)
            else:
                # Se nenhuma ocorrência for anterior, reinicia do final
                self.current_search_index = indices[-1]
                self.log_text.see(self.current_search_index)

    def on_toggle_telegram(self, *args):
        global TELEGRAM_ENABLED
        TELEGRAM_ENABLED = (
            self.enable_telegram_var.get()
        )  # Retorna True ou False conforme checkbox
        logging.info("Telegram enabled: %s", TELEGRAM_ENABLED)

    def on_toggle_novos_sinais(self, *args):
        global NOVOS_SINAIS_ENABLED
        NOVOS_SINAIS_ENABLED = (
            self.enable_novos_sinais_var.get()
        )  # Retorna True ou False conforme checkbox
        logging.info("Novos Sinais enabled: %s", NOVOS_SINAIS_ENABLED)

    def on_toggle_reposicao(self, *args):
        global REPOSICAO_ENABLED
        REPOSICAO_ENABLED = (
            self.enable_reposição_var.get()
        )  # Retorna True ou False conforme checkbox
        logging.info("Reposição enabled: %s", REPOSICAO_ENABLED)

    def fechar_posicao_manual(self):
        threading.Thread(target=self._fechar_posicao_manual, daemon=True).start()

    def fechar_posicao_manual(
        config, future_symbol, api_key, api_secret, status_callback=None
    ):
        try:
            # 1) Instancia o cliente Binance Futures via CCXT
            client = UMFutures(key=api_key, secret=api_secret)
            # 2) Verifica se há posição aberta
            selected_pos = get_open_position(
                config,
                future_symbol,
            )
            if not selected_pos:
                msg = "Nenhuma posição aberta para o ativo."
                logging.info(msg)
                if status_callback:
                    status_callback(msg)
                return

            pos_qty = float(selected_pos.get("positionAmt", 0))
            entry_price = float(selected_pos.get("entryPrice", 0))
            side = "sell" if pos_qty > 0 else "buy"

            # 3) Prepara exchange CCXT
            exchange = ccxt.binance(
                {
                    "apiKey": api_key,
                    "secret": api_secret,
                    "enableRateLimit": True,
                    "options": {
                        "defaultType": "future",
                        "adjustForTimeDifference": True,
                        "fetchMarketsMethod": "fapiPublicGetExchangeInfo",
                    },
                }
            )
            exchange.load_markets()

            # 4) Executa fechamento de posição
            params = {"reduceOnly": True}
            order = exchange.create_order(
                future_symbol, "market", side, abs(pos_qty), None, params
            )

            # 5) Define preço de fechamento (fallback para ticker se average for None)
            fechamento_preco = (
                order.get("average") or exchange.fetch_ticker(future_symbol)["last"]
            )

            # 6) Mensagem padronizada
            msg = DEFAULT_FECHAMENTO_MSG["manual"].format(
                symbol=future_symbol, order_id=order.get("id", "N/A")
            )
            logging.info(msg)
            send_telegram_message(msg)

            # 7) Calcula ROI e PnL
            pnl = (
                (fechamento_preco - entry_price) * pos_qty
                if pos_qty > 0
                else (entry_price - fechamento_preco) * abs(pos_qty)
            )
            roi_val = (
                ((fechamento_preco - entry_price) / entry_price) * 100
                if entry_price
                else 0
            )
            resultado_msg = (
                f"Resultado (Manual): ROI = {roi_val:.2f}% | PnL = {pnl:.4f} USDT"
            )
            logging.info(resultado_msg)
            send_telegram_message(resultado_msg)

            if status_callback:
                status_callback(f"{msg} | {resultado_msg}")

            # 8) Envia saldo
            send_account_balance(exchange)

        except Exception as e:
            erro = f"Erro no fechamento manual: {e}"
            logging.error(erro)
            if status_callback:
                status_callback(erro)

    def _ensure_negative(self, var: tk.StringVar):
        """
        Garante que o conteúdo de var comece com '-' e só tenha dígitos depois.
        Se o usuário digitar '25', vira '-25'; se digitar '-30', mantém '-30'.
        """
        v = var.get().strip()
        # remove quaisquer sinais extras e espaços
        v = v.lstrip("+-").strip()
        if v and v.replace(".", "", 1).isdigit():
            # reconstroi com sinal negativo
            var.set(f"-{v}")
        else:
            # se não for número válido, pode limpar ou deixar como está
            pass

    def sanitize_numeric(self, var, e=None):
        # troca todas as vírgulas por pontos, preserva apenas um ponto
        s = var.get().replace(",", ".")
        # opcional: remover caracteres inválidos
        # s = re.sub(r"[^0-9.]", "", s)
        var.set(s)

    def sanitize_integer(self, var: tk.StringVar):
        # deixa passar apenas caracteres numéricos
        clean = "".join(ch for ch in var.get() if ch.isdigit())
        var.set(clean)

    def check_empty(self, var, default):
        try:
            value = var.get()
        except Exception:
            value = ""
        if value == "" or value is None:
            try:
                var.set(default)
            except Exception as e:
                logging.exception(
                    "Erro ao definir valor padrão: %s",
                    e,
                )

    def filter_symbols(self, event):
        texto = self.search_var.get()
        filtrados = [
            ativo for ativo in ativos if ativo.lower().startswith(texto.lower())
        ]
        if texto == "":
            self.future_symbol_combo.configure(values=ativos)
        else:
            self.future_symbol_combo.configure(values=filtrados)

    def clear_search(self, *args):
        global current_candle_main, current_candle_conf, current_candle_comp
        current_candle_main = None
        current_candle_conf = None
        current_candle_comp = None
        self.search_var.set("")
        self.future_symbol_combo.configure(values=ativos)

    def on_exchange_change(self, *args):
        self.log("Utilizando Binance. (Outros provedores foram removidos)")

    def log(self, message):
        # Primeiro verifica se o widget de log existe
        if not hasattr(self, "log_text"):
            print(message)
            return

        def update_log():
            try:
                # Atualiza o conteúdo completo dos logs
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.log_content += f"{now} - {message}\n"

                # Insere o novo conteúdo no widget de logs
                self.log_text.configure(state="normal")
                self.log_text.insert(
                    ctk.END,
                    f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {message}\n",
                )
                self.log_text.configure(state="disabled")
                if self.text_handler.auto_scroll:
                    self.log_text.see(ctk.END)
            except Exception as e:
                print(f"Erro ao atualizar log: {e} - {message}")

        self.after(0, update_log)

    def update_status(self, message):
        self.status_label.after(
            0, lambda: self.status_label.configure(text="Status: " + message)
        )

    def save_credentials(self):
        exchange_name = "BINANCE"
        creds = {}
        path = get_credentials_path()
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    creds = json.load(f)
            except Exception as e:
                self.log("Erro ao carregar credenciais para salvar: " + str(e))
        creds[exchange_name] = {
            "apiKey": self.real_api_key_var.get().strip(),
            "secret": self.real_api_secret_var.get().strip(),
        }
        try:
            with open(path, "w") as f:
                json.dump(creds, f)
            self.log(f"Credenciais carregadas para {exchange_name}.")
            self.log("Configurações atualizadas.")
            self.log("TrendMax iniciado.")
        except Exception as e:
            self.log("Erro ao salvar credenciais: " + str(e))

    def remove_credentials(self):
        exchange_name = "BINANCE"
        creds = {}
        path = get_credentials_path()
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    creds = json.load(f)
            except Exception as e:
                self.log("Erro ao carregar credenciais para remover: " + str(e))
        if exchange_name in creds:
            del creds[exchange_name]
        try:
            with open(path, "w") as f:
                json.dump(creds, f)
            self.real_api_key_var.set("")
            self.real_api_secret_var.set("")
            self.log(f"Credenciais removidas para {exchange_name}.")
        except Exception as e:
            self.log("Erro ao remover credenciais: " + str(e))

    def load_credentials(self):
        exchange_name = "BINANCE"
        creds = {}
        path = get_credentials_path()
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    creds = json.load(f)
                if exchange_name in creds:
                    self.real_api_key_var.set(creds[exchange_name].get("apiKey", ""))
                    self.real_api_secret_var.set(creds[exchange_name].get("secret", ""))
                    self.log(f"Credenciais carregadas para {exchange_name}.")
                else:
                    self.real_api_key_var.set("")
                    self.real_api_secret_var.set("")
                    self.log(f"Nenhuma credencial para {exchange_name}.")
            except Exception as e:
                self.log("Erro ao carregar credenciais: " + str(e))
        else:
            self.log("Arquivo de credenciais não encontrado.")

    def show_info(self):
        info_win = ctk.CTkToplevel(self)
        info_win.title("Informações - Configurações")
        info_win.geometry("750x500")
        info_win.attributes("-topmost", True)
        info_win.focus_force()
        scroll_frame = ctk.CTkScrollableFrame(info_win, width=680, height=400)
        scroll_frame.pack(padx=10, pady=10, fill="both", expand=True)
        info_text = (
            "INFORMAÇÕES DA INTERFACE DO TrendMax-Futures\n\n"
            "1. CORRETORA:\nSeleciona a exchange utilizada (atualmente, apenas Binance).\n\n"
            "2. BUSCAR O ATIVO:\nCampo para filtrar os ativos disponíveis.\n\n"
            "3. SELECIONE O ATIVO:\nLista de ativos (ex.: BTC/USDT, ETH/USDT, etc.) para negociação.\n\n"
            "4. ALAVANCAGEM (X):\nDefine o multiplicador de alavancagem para as operações.\n\n"
            "5. PERÍODO DE TEMPO:\nIntervalo usado na comparação dos candles para análise dos sinais.\n\n"
            "6. TIMEFRAME CONFIRMAÇÃO:\nTime frame do candle utilizado para confirmar o sinal.\n\n"
            "7. TOLERÂNCIA CONFIRMAÇÃO (%):\nPercentual de tolerância para que o candle de confirmação seja válido.\n\n"
            "8. MARGEM (USDT):\nValor em USDT destinado à operação.\n\n"
            "9. TIMEFRAME OPERACIONAL:\nIntervalo utilizado para calcular os indicadores técnicos.\n\n"
            "10. MAX NOVOS SINAIS:\nLimita o número de novos sinais executados em um ciclo.\n\n"
            "11. MAX REPOSIÇÃO ORDERS:\nNúmero máximo de ordens de reposição permitidas.\n\n"
            "12. MULTIPLICADOR DE REPOSIÇÃO:\nFator que aumenta a margem inicial em ordens de reposição.\n\n"
            "13. ROI (-%) REPOSIÇÃO:\nLimiar de ROI negativo para acionar uma ordem de reposição.\n\n"
            "14. DISTÂNCIA INICIAL DA BARREIRA (Pontos):\nDistância inicial da ordem de proteção a partir do preço de entrada Ex. WIF/USDT= 0.01, AVAX/USDT= 0.40, BTC/USDT= 500\n\n"
            "15. ROI (-%) STOP LOSS:\nPercentual de ROI negativo que dispara o fechamento da posição, caso a proteção falhe.\n\n"
            "16. ROI (+%) STOP WIN:\nPercentual de ROI positivo que aciona a realização de lucros se nenhuma proteção for acionada.\n\n"
            "17. LIMITE DO ADX:\nValor mínimo do ADX para validar um sinal.\n\n"
            "18. RSI PROTEÇÃO LONG/SHORT:\nQuando esses níveis críticos são alcançados, o robô emite um log informando que o RSI não confirma o sinal e a posição é encerrada automaticamente para limitar perdas.\n\n"
            "19. NÍVEIS DO BOOK:\nQuantidade de níveis do order book analisados para avaliar o fluxo de ordens.\n\n"
            "20. PERÍODO DOS INDICADORES:\nNúmero de períodos usado no cálculo dos indicadores técnicos.\n\n"
            "21. IMBALANCE LONG:\nDesequilíbrio mínimo para confirmar um sinal de compra.\n\n"
            "22. IMBALANCE SHORT:\nDesequilíbrio máximo (valor negativo) para confirmar um sinal de venda.\n\n"
            "23. MODO DE MARGEM:\nSeleção entre 'ISOLATED' e 'CROSSED'.\n\n"
            "24. ATIVAR NOVOS SINAIS:\nHabilita ou desabilita a entrada de novos sinais.\n\n"
            "25. ATIVAR REPOSIÇÃO:\nPermite ordens de reposição para ajustar a posição.\n\n"
            "26. ATIVAR TELEGRAM:\nAtiva ou desabilita notificações via Telegram.\n\n"
            "27. REAL API KEY e SECRET:\nCredenciais para acesso à Binance Futures.\n\n"
            "28. SEGURANÇA POR IP e HEARTBEAT:\nGarante a sessão e comunicação com o servidor.\n\n"
            "29. TELEGRAM:\nUtilize o bot TrendMaxFutures (@TrendMaxFutures_bot) para notificações importantes."
        )
        info_label = ctk.CTkLabel(
            scroll_frame,
            text=info_text,
            font=DEFAULT_FONT,
            wraplength=680,
            justify="left",
        )
        info_label.pack(padx=10, pady=10)
        close_button = ctk.CTkButton(
            info_win,
            text="Fechar",
            command=info_win.destroy,
            font=DEFAULT_FONT,
            width=120,
            height=30,
        )
        close_button.pack(pady=5)

    def minhas_licencas(self, **kwargs):
        licenca = conexao_licenca() or "Licença não encontrada"

        def validar_cpf(cpf):
            return cpf.isdigit() and len(cpf) == 11

        def validar_email(email):
            return "@" in email and "." in email

        def validar_entrada():
            nome = entrada_nome.get().strip()
            sobrenome = entrada_sobrenome.get().strip()
            cpf = entrada_cpf.get().strip()
            email = entrada_email.get().strip()
            if nome and sobrenome and validar_cpf(cpf) and validar_email(email):
                btn_renovar.configure(state="normal")
            else:
                btn_renovar.configure(state="disabled")

        def criar_pagamento(*args):
            cod_unico = obter_codigo_licenca()
            nome = entrada_nome.get()
            sobrenome = entrada_sobrenome.get()
            email = entrada_email.get()
            cpf = entrada_cpf.get()
            url = "http://api.trendmax.space/gerar_pagamento_pix"
            payload = {
                "codigo_unico": cod_unico,
                "email_cliente": email,
                "nome_cliente": nome + sobrenome,
                "cpf_cliente": cpf,
            }
            response = requests.post(url, json=payload)
            if response.status_code == 201:
                data = response.json()
                url_pagamento = data.get("payment_url")
                pix_code = data.get("pix_copia_e_cola")
                if url_pagamento and pix_code:
                    return url_pagamento, pix_code
                else:
                    print("Erro: 'url_pagamento' ou 'pix' não encontrados na resposta.")
                    return None, None
            else:
                print("Erro ao gerar pagamento:", response.text)
                return None, None

        def janela_pagamento(*args):
            (url_pagamento,) = criar_pagamento()
            if url_pagamento:
                webbrowser.open(url_pagamento, new=1, autoraise=True)
                janela_licenca.after(10, lambda: janela_licenca.destroy())
            else:
                messagebox.showerror(
                    "Erro", "Erro ao gerar pagamento. Tente novamente."
                )

        janela_licenca = ctk.CTkToplevel()
        janela_licenca.title("Minha Licença")
        janela_licenca.geometry("600x500")
        janela_licenca.attributes("-topmost", True)

        main_frame = ctk.CTkFrame(janela_licenca)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        main_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=2)
        main_frame.columnconfigure(0, weight=1)

        header_frame = ctk.CTkFrame(main_frame)
        header_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        lbl_info = ctk.CTkLabel(
            header_frame, text="INFORMAÇÕES DA LICENÇA", font=DEFAULT_FONT
        )
        lbl_info.grid(row=0, column=0, columnspan=2, sticky="w")
        lbl_status = ctk.CTkLabel(
            header_frame, text="Status da Licença:", font=("Arial", 10)
        )
        lbl_status.grid(row=1, column=0, sticky="e", padx=(0, 5), pady=(5, 0))
        status_label = ctk.CTkLabel(header_frame, text=licenca, font=("Arial", 20))
        status_label.grid(row=1, column=1, sticky="w", padx=(5, 0), pady=(5, 0))
        header_frame.rowconfigure(0, weight=1)
        header_frame.rowconfigure(1, weight=1)
        header_frame.columnconfigure(0, weight=1)
        header_frame.columnconfigure(1, weight=1)

        payment_frame = ctk.CTkFrame(main_frame)
        payment_frame.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        lbl_pag = ctk.CTkLabel(
            payment_frame, text="INFORMAÇÕES PARA PAGAMENTO", font=DEFAULT_FONT
        )
        lbl_pag.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        payment_frame.columnconfigure(0, weight=1)
        payment_frame.columnconfigure(1, weight=2)

        lbl_nome = ctk.CTkLabel(payment_frame, text="Nome:", font=("Arial", 10))
        lbl_nome.grid(row=1, column=0, sticky="e", padx=(0, 5), pady=5)
        entrada_nome = ctk.CTkEntry(payment_frame, width=300)
        entrada_nome.grid(row=1, column=1, sticky="ew", pady=5)
        entrada_nome.bind("<KeyRelease>", lambda e: validar_entrada())

        lbl_sobrenome = ctk.CTkLabel(
            payment_frame, text="Sobrenome:", font=("Arial", 10)
        )
        lbl_sobrenome.grid(row=2, column=0, sticky="e", padx=(0, 5), pady=5)
        entrada_sobrenome = ctk.CTkEntry(payment_frame, width=300)
        entrada_sobrenome.grid(row=2, column=1, sticky="ew", pady=5)
        entrada_sobrenome.bind("<KeyRelease>", lambda e: validar_entrada())

        lbl_cpf = ctk.CTkLabel(payment_frame, text="CPF:", font=("Arial", 10))
        lbl_cpf.grid(row=3, column=0, sticky="e", padx=(0, 5), pady=5)
        entrada_cpf = ctk.CTkEntry(payment_frame, width=300)
        entrada_cpf.grid(row=3, column=1, sticky="ew", pady=5)
        entrada_cpf.bind("<KeyRelease>", lambda e: validar_entrada())

        lbl_email = ctk.CTkLabel(payment_frame, text="E-mail:", font=("Arial", 10))
        lbl_email.grid(row=4, column=0, sticky="e", padx=(0, 5), pady=5)
        entrada_email = ctk.CTkEntry(payment_frame, width=300)
        entrada_email.grid(row=4, column=1, sticky="ew", pady=5)
        entrada_email.bind("<KeyRelease>", lambda e: validar_entrada())

        btn_renovar = ctk.CTkButton(
            payment_frame,
            text="Renovar Licença",
            command=janela_pagamento,
            state="disabled",
        )
        btn_renovar.grid(row=5, column=0, columnspan=2, pady=10)

        janela_licenca.mainloop()

    def show_Telegram_Config_Futures(self):
        tel_win = ctk.CTkToplevel(self)
        tel_win.title("Configurações do Telegram")
        tel_win.geometry("400x300")
        tel_win.attributes("-topmost", True)
        label_token = ctk.CTkLabel(tel_win, text="Bot Token:", font=DEFAULT_FONT)
        label_token.pack(pady=5)
        entry_token = ctk.CTkEntry(
            tel_win,
            textvariable=self.telegram_bot_token_var,
            width=350,
            font=DEFAULT_FONT,
            state="disabled",
        )
        entry_token.pack(pady=5)
        label_chat = ctk.CTkLabel(tel_win, text="Chat ID:", font=DEFAULT_FONT)
        label_chat.pack(pady=5)
        entry_chat = ctk.CTkEntry(
            tel_win,
            textvariable=self.telegram_chat_id_var,
            width=350,
            font=DEFAULT_FONT,
        )
        entry_chat.pack(pady=5)
        test_button = ctk.CTkButton(
            tel_win,
            text="Testar Bot",
            command=self.test_Telegram_Config_Futures,
            font=DEFAULT_FONT,
            width=150,
        )
        test_button.pack(pady=5)
        save_button = ctk.CTkButton(
            tel_win,
            text="Adicionar Configuração",
            command=lambda: self.save_Telegram_Config_Futures(tel_win),
            font=DEFAULT_FONT,
            width=150,
        )
        save_button.pack(pady=10)
        remove_button = ctk.CTkButton(
            tel_win,
            text="Remover Configuração",
            command=lambda: self.remove_Telegram_Config_Futures(tel_win),
            font=DEFAULT_FONT,
            width=150,
        )
        remove_button.pack(pady=5)

    def test_Telegram_Config_Futures(self):
        bot_token = TELEGRAM_BOT_TOKEN
        chat_id = self.telegram_chat_id_var.get().strip()
        if not chat_id:
            self.log("Informe um Chat ID válido para testar.")
            return
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": "Olá! Estou pronto para acompanhar suas negociações, Vamos começar.",
        }
        try:
            response = requests.post(url, json=payload, timeout=5)
            if response.status_code == 200:
                self.log("Mensagem de teste enviada com sucesso.")
            else:
                self.log("Falha ao enviar mensagem de teste.")
        except Exception as e:
            self.log("Erro ao enviar mensagem de teste: " + str(e))

    def save_Telegram_Config_Futures(self, win):
        chat_id = self.telegram_chat_id_var.get().strip()
        if not chat_id:
            self.log("Informe um Chat ID válido para salvar a configuração.")
            return
        config_path = get_Telegram_Config_Futures_path()
        try:
            with open(config_path, "w") as f:
                json.dump({"chat_id": chat_id}, f)
            self.log("Configurações do Telegram salvas.")
        except Exception as e:
            self.log("Erro ao salvar configurações do Telegram: " + str(e))
        win.destroy()

    def remove_Telegram_Config_Futures(self, win):
        config_path = get_Telegram_Config_Futures_path()
        if os.path.exists(config_path):
            try:
                os.remove(config_path)
                self.log("Configurações do Telegram removidas.")
            except Exception as e:
                self.log("Erro ao remover configurações do Telegram: " + str(e))
        else:
            self.log("Nenhuma configuração encontrada para remover.")
        self.telegram_chat_id_var.set("")
        win.destroy()

    def toggle_autoscroll(self):
        self.text_handler.auto_scroll = not self.text_handler.auto_scroll
        new_text = (
            "Auto Scroll: ON" if self.text_handler.auto_scroll else "Auto Scroll: OFF"
        )
        self.autoscroll_button.configure(text=new_text)

    def set_shutdown_requested(self, value=True):
        self.shutdown_requested = value

    # Refatoração de start_robot para treinar, mostrar dias e tempo de treino, e carregar modelo

    def start_robot(self):
        import os
        import time

        import ccxt
        import joblib
        from ml_pipeline import compute_features, fetch_historical_data
        from xgboost import XGBClassifier

        # 1) Carrega credenciais salvas
        self.load_credentials()

        # 2) Verifica licença
        status_licenca = conexao_licenca()
        if status_licenca != "Ativa":
            self.log("Licença não ativa ou expirada!")
            return

        # 3) Lê e valida inputs numéricos
        try:
            lot_value = float(self.lot_value_var.get() or "2")
            leverage = int(self.leverage_var.get() or "125")
            roi_stop_loss_threshold = float(
                self.roi_stop_loss_threshold_var.get() or "-50"
            )
            roi_stop_win_threshold = float(
                self.roi_stop_win_threshold_var.get() or "100"
            )
        except ValueError as e:
            self.log(f"Insira valores numéricos válidos: {e}")
            return

        # 4) Verifica credenciais Binance Futures
        api_key = self.real_api_key_var.get().strip()
        api_secret = self.real_api_secret_var.get().strip()
        if not api_key or not api_secret:
            self.log("Insira suas credenciais Binance Futures")
            return

        # 5) Parâmetros para ML
        symbol_ui = self.future_symbol_var.get().strip()  # "BTC/USDT"
        symbol = symbol_ui.replace("/", "").lower()  # "btcusdt"
        timeframe = self.operational_tf_var.get().strip()  # ex: "15m"
        lookback_days = 90
        model_dir = "models"
        os.makedirs(model_dir, exist_ok=True)
        model_filename = f"xgb_{symbol}_model.pkl"
        model_path = os.path.join(model_dir, model_filename)

        # 6) FETCH HISTÓRICO
        self.log(
            f"[ML] [1/4] Buscando dados históricos de {symbol_ui} ({lookback_days} dias, TF={timeframe})…"
        )
        start_fetch = time.time()
        exchange_tmp = ccxt.binance(
            {"enableRateLimit": True, "options": {"defaultType": "future"}}
        )
        df = fetch_historical_data(
            exchange_tmp, symbol_ui, timeframe, lookback_days
        )  # <- symbol_ui aqui
        fetch_time = time.time() - start_fetch
        self.log(f"[ML] Dados históricos obtidos em {fetch_time:.2f}s.")

        # 7) COMPUTA FEATURES
        self.log("[ML] [2/4] Computando features via ml_pipeline…")
        start_feat = time.time()
        df_feat = compute_features(df)
        feat_time = time.time() - start_feat
        self.log(f"[ML] Features calculadas em {feat_time:.2f}s.")

        # 8) TREINO XGBOOST
        self.log("[ML] [3/4] Iniciando treino XGBoost…")
        start_train = time.time()
        model = XGBClassifier(eval_metric="logloss")
        model.fit(df_feat.drop(columns=["open_time", "target"]), df_feat["target"])
        train_time = time.time() - start_train
        joblib.dump(model, model_path)
        self.log(
            f"[ML] Modelo treinado e salvo em {model_path} (treino levou {train_time:.2f}s)."
        )

        # 9) Carrega modelo ML
        try:
            ml_model = joblib.load(model_path)
            self.log(f"[ML] Modelo carregado: {model_filename}")
        except Exception:
            ml_model = None
            self.log(f"[ML] Falha ao carregar modelo; ML ficará indisponível.")

        # 10) Monta o dicionário de configuração, incluindo as chaves da API
        config = {
            "account_mode": "REAL",
            "future_symbol": symbol_ui,
            "lot_value": lot_value,
            "leverage": leverage,
            "margin_mode": self.margin_mode_var.get().upper(),
            "comparison_tf": self.timeframe_var.get().strip(),
            "operational_tf": self.operational_tf_var.get().strip(),
            "confirmation_tf": self.confirmation_tf_var.get().strip(),
            "real_api_key": api_key,
            "real_api_secret": api_secret,
            "roi_stop_loss_threshold": roi_stop_loss_threshold,
            "roi_stop_win_threshold": roi_stop_win_threshold,
            "order_book_levels": int(self.order_book_levels_var.get() or "5"),
            "confirmation_tolerance": float(
                self.confirmation_tolerance_var.get() or "5"
            )
            / 100,
            "adx_threshold": float(self.adx_threshold_var.get() or "25"),
            "max_signals": int(self.max_signals_var.get() or "4"),
            "max_reposicao_orders": int(self.max_reposição_var.get() or "1"),
            "enable_reposicao": self.enable_reposição_var.get(),
            "reposicao_multiplier": float(self.reposicao_multiplier_var.get() or "1.1"),
            "distance": float(self.initial_barrier_var.get() or "400"),
            "reposicao_roi_threshold": float(self.reposicao_roi_var.get() or "-25"),
            "roi_reduzir": float(self.roi_reduzir_var.get() or "25"),
            "roi_trailing_activation": float(
                self.roi_trailing_activation_var.get() or "50"
            ),
            "trailing_stop_percent": float(self.trailing_stop_var.get() or "0.00118"),
            "min_imbalance_long": float(self.imbalance_long_var.get() or "0.3"),
            "max_imbalance_short": float(self.imbalance_short_var.get() or "-0.3"),
            "indicator_period": int(self.indicator_period_var.get() or "14"),
            "enable_novossinais": self.enable_novos_sinais_var.get(),
            "rsi_protection_min": float(self.rsi_protection_min_var.get() or "30"),
            "rsi_protection_max": float(self.rsi_protection_max_var.get() or "70"),
            "ml_confidence_threshold": float(self.ml_confidence_var.get() or "55")
            / 100,
            "ml_model": ml_model,
            "exchange": "BINANCE",
        }

        # 11) Inicia o loop de execução em background
        self.log("Configurações atualizadas. Iniciando execução…")
        self.stop_event.clear()
        self.robot_thread = threading.Thread(
            target=run_realtime,
            args=(
                config,
                self.log,
                self.update_status,
                self.stop_event,
                self.set_shutdown_requested,
            ),
            daemon=True,
        )
        self.robot_thread.start()

        # 12) Atualiza UI
        self.toggle_button.configure(text="Parar TrendMax")
        self.log("TrendMax iniciado.")
        self.update_status("Operando…")
        self.fechar_posicao_button.configure(state="normal")

    def stop_robot(self):
        # ————————————— Zerando APENAS os contadores de sinais/reposição —————————————
        global reposicao_count, signal_count
        reposicao_count = 0
        signal_count = 0

        # 1) Sinaliza para o run_realtime parar
        self.stop_event.set()

        # 2) Fecha cada WebSocketApp que ainda estiver rodando
        global ws_apps
        for ws_app in ws_apps:
            try:
                ws_app.close()
            except Exception as e:
                logging.warning(
                    "Erro ao fechar WebSocket: %s",
                    e,
                )
        ws_apps.clear()

        # 3) Aguarda a thread principal encerrar
        if self.robot_thread and self.robot_thread.is_alive():
            self.robot_thread.join(timeout=5)

        # 4) Atualiza a interface
        self.toggle_button.configure(text="Iniciar TrendMax")
        self.fechar_posicao_button.configure(state="disabled")
        self.log("Solicitado parada.")
        self.update_status("Encerrado OK!")

        # 5) Limpa o flag de erro crítico para permitir reinício
        self.shutdown_requested = False

    def toggle_robot(self):
        # Se o robô estiver rodando, sempre para o robô
        if self.robot_thread and self.robot_thread.is_alive():
            self.stop_robot()
            return

        # Se houve um erro crítico anteriormente, limpar o flag e notificar
        if self.shutdown_requested:
            self.log(
                "Ocorreu um erro crítico anteriormente, mas você pode reiniciar o robô."
            )
            self.shutdown_requested = False

        # Caso contrário, inicia o robô
        self.start_robot()


# ============================================================================
# ---------------------------- Código principal ------------------------------
if __name__ == "__main__":
    update_available, remote_version = check_for_new_version()
    if update_available:
        messagebox.showinfo(
            "Atualização Disponível",
            f"Nova versão disponível: {remote_version}.\nPor favor, baixe a nova versão em:\nhttps://trendmax.space/TrendMaxFutures/",
        )
        sys.exit()

    load_Telegram_Config_Futures()
    app = TradingRobotGUI()
    app.load_credentials()

    def on_closing():
        if app.robot_thread and app.robot_thread.is_alive():
            if messagebox.askyesno(
                "Fechar Aplicativo",
                "O robô ainda está em execução. Deseja forçar o encerramento?",
            ):
                app.stop_robot()
                app.robot_thread.join(timeout=5)
                app.destroy()
            else:
                app.log("POR FAVOR, PARE O RÔBO ANTES DE FECHAR A JANELA!")
        else:
            app.destroy()

    app.protocol("WM_DELETE_WINDOW", on_closing)
    app.mainloop()
    # ============================================================================
    # ---------------------------- Final do código -------------------------------
    # ============================================================================
