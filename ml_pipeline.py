# ml_pipeline.py
# Pipeline de preparação de dados para Machine Learning

from indicators import (
    calculate_moving_averages,
    calculate_atr,
    calculate_volume_ma,
    calculate_rsi,
    calculate_macd
)
import re
import pandas as pd
import numpy as np
import joblib

def fetch_historical_data(exchange, symbol: str, timeframe: str, lookback_days: int) -> pd.DataFrame:
    """
    Baixa candles históricos de futuros via CCXT e monta um DataFrame com coluna 'target' binária
    (1 se o próximo fechamento for maior, 0 caso contrário).
    """
    # Ajusta formato do símbolo (ex: "BTCUSDT" -> "BTC/USDT")
    if "/" not in symbol:
        symbol = symbol[:-4] + "/" + symbol[-4:]

    # Converte timeframe em minutos
    if timeframe.endswith('m'):
        period_min = int(timeframe[:-1])
    elif timeframe.endswith('h'):
        period_min = int(timeframe[:-1]) * 60
    elif timeframe.endswith('d'):
        period_min = int(timeframe[:-1]) * 1440
    else:
        match = re.search(r"(\d+)", timeframe)
        period_min = int(match.group(1)) if match else 1

    # Calcula limite de candles
    limit = lookback_days * 24 * 60 // period_min

    # Busca dados OHLCV
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["open_time", "open", "high", "low", "close", "volume"])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")

    # Alvo binário: próximo fechamento maior que o atual
    df["target"] = np.where(df["close"].shift(-1) > df["close"], 1, 0)

    # Remove o último registro (target indefinido)
    return df.iloc[:-1].reset_index(drop=True)

def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Recebe DataFrame OHLCV + target e retorna DataFrame de features + target,
    enriquecido com retornos, médias móveis, ATR, volume médio, RSI e MACD.
    """
    df2 = df.copy()

    # 1) Retorno percentual do candle anterior
    df2["ret"] = df2["close"].pct_change()

    # 2) Médias móveis (5, 10, 50, 100 períodos)
    ma_df = calculate_moving_averages(df2["close"], periods=[5, 10, 50, 100])
    df2 = pd.concat([df2, ma_df], axis=1)

    # 3) ATR simplificado de 5 períodos
    atr_df = calculate_atr(df2[['high','low','close']], period=5)
    df2['atr5'] = atr_df['atr']

    # 4) Volume médio (5 e 10 períodos)
    vol_df = calculate_volume_ma(df2['volume'], periods=[5, 10])
    df2 = pd.concat([df2, vol_df], axis=1)

    # 5) RSI de 14 períodos
    df2['rsi14'] = calculate_rsi(df2[['close']], period=14)

    # 6) MACD (12, 26, 9)
    macd_df = calculate_macd(df2['close'], fast=12, slow=26, signal=9)
    df2 = pd.concat([df2, macd_df], axis=1)

    # Remove NaNs resultantes dos cálculos iniciais
    df2 = df2.dropna().reset_index(drop=True)
    return df2

def load_model(path: str):
    """
    Carrega um modelo serializado via joblib.
    """
    return joblib.load(path)
