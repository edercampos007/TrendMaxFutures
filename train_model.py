# train_model.py
import os
import argparse
import joblib
from xgboost import XGBClassifier
import ccxt

from ml_pipeline import fetch_historical_data, compute_features

def train_and_save(exchange, symbol: str, timeframe: str, lookback_days: int, model_path: str):
    """
    1) Busca dados históricos
    2) Calcula features
    3) Treina XGBoost
    4) Serializa com joblib
    """
    print(f"[1/4] Buscando dados históricos de {symbol} ({lookback_days}d, TF={timeframe})...")
    df = fetch_historical_data(exchange, symbol, timeframe, lookback_days)

    print("[2/4] Computando features via ml_pipeline...")
    df_feat = compute_features(df)

    # Separar X e y
    X = df_feat.drop(columns=["open_time", "target"])
    y = df_feat["target"]

    print("[3/4] Treinando XGBoost...")
    model = XGBClassifier(use_label_encoder=False, eval_metric="logloss")
    model.fit(X, y)

    # Garantir que a pasta exista
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    joblib.dump(model, model_path)
    print(f"[4/4] Modelo salvo em {model_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Treina e salva um modelo XGBoost para um símbolo de futuros.")
    parser.add_argument("--symbol",       required=True, help="Símbolo CCXT (ex: BTC/USDT ou BTCUSDT)")
    parser.add_argument("--timeframe",    default="15m", help="Timeframe dos candles (ex: 15m)")
    parser.add_argument("--lookback_days",type=int, default=30,  help="Dias de histórico para treinar")
    parser.add_argument("--model_path",   default=None,          help="Caminho de saída (ex: models/xgb_btcusdt_model.pkl)")
    args = parser.parse_args()

    # Normalizar simbolismo
    sym = args.symbol.replace("/", "")
    tf  = args.timeframe
    lb  = args.lookback_days
    # Definir onde salvar
    default_path = f"models/xgb_{sym.lower()}_model.pkl"
    path = args.model_path or default_path

    # Cliente CCXT para Binance Futures
    exchange = ccxt.binance({
        "enableRateLimit": True,
        "options": {"defaultType": "future"}
    })

    train_and_save(exchange, args.symbol, tf, lb, path)
