# orderbook_utils.py
"""
Utilidades para métricas de Order Book e Fluxo de Ordens
========================================================
Todas as funções são *stateless*; basta passar a instância CCXT e o símbolo
(em formato CCXT, ex.: "BTC/USDT").

Funções
-------
get_order_book(exchange, symbol, levels=5)
    Devolve apenas os 'levels' primeiros bids/asks do book.

get_total_volume(exchange, symbol, levels=5)
    Soma o volume de bids/asks nos 'levels' primeiros níveis.  
    Retorna: total_bid, total_ask, best_bid, best_ask, avg_bid, avg_ask

get_order_book_metrics(exchange, symbol, levels=5)
    Retorna bid_volume, ask_volume e imbalance
    imbalance = (bid - ask) / (bid + ask)

get_aggressive_volume(exchange, symbol, limit=100)
    Faz fetch_trades e separa volume aggressor de BUY e SELL.
"""

from __future__ import annotations

import logging
from typing import Tuple, Optional

import ccxt  # type: ignore


# --------------------------------------------------------------------------- #
# Book “cru”                                                                  #
# --------------------------------------------------------------------------- #
def get_order_book(
    exchange: "ccxt.Exchange",
    symbol: str,
    levels: int = 5,
) -> Optional[dict]:
    """
    Retorna um dicionário {'bids': [...], 'asks': [...]} contendo
    apenas *levels* níveis de profundidade.

    Se ocorrer erro na consulta, devolve None.
    """
    try:
        full_book = exchange.fetch_order_book(symbol)
        return {
            "bids": full_book.get("bids", [])[:levels],
            "asks": full_book.get("asks", [])[:levels],
        }
    except Exception as e:  # pragma: no cover
        logging.error("Erro get_order_book: %s", e)
        return None


# --------------------------------------------------------------------------- #
# Volume total por lado                                                       #
# --------------------------------------------------------------------------- #
def get_total_volume(
    exchange: "ccxt.Exchange",
    symbol: str,
    levels: int = 5,
) -> Tuple[float, float, float, float, float, float]:
    """
    total_bid, total_ask, best_bid, best_ask, avg_bid, avg_ask
    """
    try:
        book = get_order_book(exchange, symbol, levels)
        if book is None:
            raise RuntimeError("book vazio")

        bids = book["bids"]
        asks = book["asks"]

        total_bid = sum(b[1] for b in bids)
        total_ask = sum(a[1] for a in asks)
        best_bid  = bids[0][0] if bids else 0
        best_ask  = asks[0][0] if asks else 0
        avg_bid   = total_bid / len(bids) if bids else 0
        avg_ask   = total_ask / len(asks) if asks else 0

        return total_bid, total_ask, best_bid, best_ask, avg_bid, avg_ask
    except Exception as e:  # pragma: no cover
        logging.error("Erro get_total_volume: %s", e)
        return 0, 0, 0, 0, 0, 0


# --------------------------------------------------------------------------- #
# Métricas compactas                                                          #
# --------------------------------------------------------------------------- #
def get_order_book_metrics(
    exchange: "ccxt.Exchange",
    symbol: str,
    levels: int = 5,
) -> Tuple[float, float, float]:
    """
    bid_volume, ask_volume, imbalance
    imbalance ∈ [-1, +1]:
        +1  → só bids
        -1  → só asks
         0  → perfeito equilíbrio
    """
    try:
        book = get_order_book(exchange, symbol, levels)
        if book is None:
            raise RuntimeError("book vazio")

        bids = book["bids"]
        asks = book["asks"]

        bid_vol = sum(b[1] for b in bids)
        ask_vol = sum(a[1] for a in asks)

        denom = bid_vol + ask_vol
        imbalance = (bid_vol - ask_vol) / denom if denom else 0.0
        return bid_vol, ask_vol, imbalance
    except Exception as e:  # pragma: no cover
        logging.error("Erro get_order_book_metrics: %s", e)
        return 0.0, 0.0, 0.0


# --------------------------------------------------------------------------- #
# Volume agressor                                                             #
# --------------------------------------------------------------------------- #
def get_aggressive_volume(
    exchange,
    symbol: str,
    limit: int = 100,
) -> Tuple[float, float]:
    """
    Retorna buy_aggressive, sell_aggressive medidos pelos últimos *limit* trades.
    Sempre devolve floats, mesmo se não houver trades.
    """
    try:
        trades = exchange.fetch_trades(symbol, limit=limit)
        # sum(..., 0.0) garante que o resultado seja float
        buy_aggressive  = sum((t["amount"] for t in trades if t.get("side") == "buy"),  0.0)
        sell_aggressive = sum((t["amount"] for t in trades if t.get("side") == "sell"), 0.0)
        return buy_aggressive, sell_aggressive
    except Exception as e:  # pragma: no cover
        logging.error("Erro get_aggressive_volume: %s", e)
        return 0.0, 0.0


