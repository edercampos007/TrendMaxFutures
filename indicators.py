# indicators.py
# =============================================================================
# Todos os cálculos de indicadores técnicos usados pelo TrendMax-Futures
# (mantidos aqui para isolar lógica matemática do resto do robô).
# =============================================================================

import pandas as pd
import numpy as np
import logging
from typing import List, Tuple


# --------------------------------------------------------------------------- #
# 1) ATR – Average True Range
# --------------------------------------------------------------------------- #
def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Calcula o Average True Range (ATR) e devolve *uma cópia* do DataFrame
    original contendo a coluna 'atr'.

    df      → DataFrame com colunas ['high', 'low', 'close']
    period  → janela para média móvel simples
    """
    out = df.copy()

    out["prev_close"] = out["close"].shift(1)
    tr_components = pd.concat(
        [
            out["high"] - out["low"],
            (out["high"] - out["prev_close"]).abs(),
            (out["low"] - out["prev_close"]).abs(),
        ],
        axis=1,
    )
    out["tr"] = tr_components.max(axis=1)
    out["atr"] = out["tr"].rolling(window=period, min_periods=period).mean()

    return out.drop(columns=["prev_close", "tr"])


# --------------------------------------------------------------------------- #
# 2) JMA – simplificado (usamos EMA como proxy)
# --------------------------------------------------------------------------- #
def calculate_jma(price_series: pd.Series, period: int = 14) -> pd.Series:
    """
    Jurik Moving Average (proxy simplificado com EMA).
    """
    return price_series.ewm(span=period, adjust=False).mean()


# --------------------------------------------------------------------------- #
# 3) ADX – Average Directional Index
# --------------------------------------------------------------------------- #
def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Adiciona as colunas TR, +DM, -DM, DI+, DI-, DX e **ADX** (tudo
    maiúsculo) ao DataFrame e devolve o mesmo df.
    """
    df = df.copy()

    df['prev_close'] = df['close'].shift(1)

    df['tr0'] = df['high'] - df['low']
    df['tr1'] = (df['high'] - df['prev_close']).abs()
    df['tr2'] = (df['low']  - df['prev_close']).abs()
    df['TR']  = df[['tr0', 'tr1', 'tr2']].max(axis=1)

    df['+DM'] = df['high'] - df['high'].shift(1)
    df['-DM'] = df['low'].shift(1) - df['low']
    df['+DM'] = np.where((df['+DM'] > df['-DM']) & (df['+DM'] > 0), df['+DM'], 0)
    df['-DM'] = np.where((df['-DM'] > df['+DM']) & (df['-DM'] > 0), df['-DM'], 0)

    df['TR_sum']  = df['TR'] .rolling(window=period).sum()
    df['+DM_sum'] = df['+DM'].rolling(window=period).sum()
    df['-DM_sum'] = df['-DM'].rolling(window=period).sum()

    df['DI+'] = 100 * (df['+DM_sum'] / df['TR_sum'])
    df['DI-'] = 100 * (df['-DM_sum'] / df['TR_sum'])
    df['DX']  = 100 * (df['DI+'] - df['DI-']).abs() / (df['DI+'] + df['DI-'])
    df['ADX'] = df['DX'].rolling(window=period).mean()

    # limpa o excesso (opcional)
    df.drop(columns=['tr0','tr1','tr2','+DM','-DM','+DM_sum','-DM_sum','DX'], inplace=True)
    return df

# --------------------------------------------------------------------------- #
# 4) RSI – Relative Strength Index
# --------------------------------------------------------------------------- #
def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    delta     = df["close"].diff()
    gain      = delta.clip(lower=0)
    loss      = -delta.clip(upper=0)
    avg_gain  = gain.rolling(window=period, min_periods=period).mean()
    avg_loss  = loss.rolling(window=period, min_periods=period).mean()

    rs  = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    # Se avg_loss==0 → mercado só subiu → RSI=100
    rsi = rsi.where(avg_loss != 0, 100)
    # Se avg_gain==0 → só caiu → RSI=0
    rsi = rsi.where(avg_gain != 0, 0)

    return rsi

# --------------------------------------------------------------------------- #
# 5) MACD
# --------------------------------------------------------------------------- #
def calculate_macd(
    price_series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    """
    Retorna DataFrame com ['macd', 'macd_sig', 'macd_hist'].
    """
    ema_fast = price_series.ewm(span=fast, adjust=False).mean()
    ema_slow = price_series.ewm(span=slow, adjust=False).mean()

    macd = ema_fast - ema_slow
    macd_sig = macd.ewm(span=signal, adjust=False).mean()
    macd_hist = macd - macd_sig

    return pd.DataFrame(
        {
            "macd": macd,
            "macd_sig": macd_sig,
            "macd_hist": macd_hist,
        }
    )


# --------------------------------------------------------------------------- #
# 6) Médias Móveis simples
# --------------------------------------------------------------------------- #
def calculate_moving_averages(
    price_series: pd.Series, periods: List[int] = (5, 10, 50, 100)
) -> pd.DataFrame:
    """
    Gera DataFrame com colunas 'ma<periodo>'.
    """
    ma_dict = {f"ma{p}": price_series.rolling(window=p).mean() for p in periods}
    return pd.DataFrame(ma_dict)


# --------------------------------------------------------------------------- #
# 7) Médias móveis de volume
# --------------------------------------------------------------------------- #
def calculate_volume_ma(
    volume_series: pd.Series, periods: List[int] = (5, 10)
) -> pd.DataFrame:
    vol_dict = {f"vol_ma{p}": volume_series.rolling(window=p).mean() for p in periods}
    return pd.DataFrame(vol_dict)


# --------------------------------------------------------------------------- #
# 8) Volume agressor (trade tape)
# --------------------------------------------------------------------------- #
def get_aggressive_volume(exchange, symbol: str, limit: int = 100) -> Tuple[float, float]:
    try:
        trades = exchange.fetch_trades(symbol, limit=limit)
        buy_aggressive  = sum((t["amount"] for t in trades if t.get("side")=="buy"),  0.0)
        sell_aggressive = sum((t["amount"] for t in trades if t.get("side")=="sell"), 0.0)
        return buy_aggressive, sell_aggressive
    except Exception as e:
        logging.error("Erro get_aggressive_volume: %s", e)
        return 0.0, 0.0

