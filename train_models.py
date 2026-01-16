#!/usr/bin/env python3
"""
================================================================================
    BEAST ENGINE - MODEL TRAINING PIPELINE
================================================================================
    
    This script downloads fresh market data and retrains the AI models.
    Run weekly or when you want the AI to learn from recent market conditions.
    
    Usage:
        python train_models.py              # Train with default settings
        python train_models.py --days 365   # Train with 1 year of data
        python train_models.py --symbols SPY QQQ NVDA  # Train on specific symbols
    
================================================================================
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import joblib

# ML Models
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
import xgboost as xgb
import lightgbm as lgb

# Market Data
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

import yaml


def load_config() -> Dict:
    """Load configuration"""
    if os.path.exists("config.yaml"):
        with open("config.yaml", 'r') as f:
            return yaml.safe_load(f)
    return {}


class BeastTrainer:
    """
    AI Model Trainer for BEAST Engine
    
    Downloads market data, engineers features, and trains ensemble models.
    """
    
    def __init__(self, config: Dict):
        self.config = config
        
        # Initialize Alpaca client
        alpaca_config = config.get('alpaca', {})
        self.client = StockHistoricalDataClient(
            alpaca_config.get('api_key', ''),
            alpaca_config.get('api_secret', '')
        )
        
        # Default training symbols (high liquidity 0DTE options)
        self.default_symbols = [
            "SPY", "QQQ", "IWM", "DIA",
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AMD",
            "JPM", "BAC", "GS",
            "XOM", "CVX",
            "WMT", "HD", "NKE"
        ]
        
        # Feature names (must match beast_engine.py)
        self.feature_names = [
            'returns_1', 'returns_5', 'returns_10',
            'rsi', 'adx',
            'price_to_ema9', 'price_to_ema21', 'price_to_ema50',
            'macd_hist',
            'volume_ratio',
            'atr', 'atr_pct',
            'hour', 'minute', 'minutes_to_close',
            'day_of_week'
        ]
        
        print("=" * 60)
        print("    BEAST TRAINER INITIALIZED")
        print("=" * 60)
    
    def download_data(self, symbols: List[str], days: int = 365) -> Dict[str, pd.DataFrame]:
        """Download historical data from Alpaca"""
        print(f"\n[DATA] Downloading {days} days of data for {len(symbols)} symbols...")
        
        data = {}
        start_date = datetime.now() - timedelta(days=days)
        
        for symbol in symbols:
            try:
                request = StockBarsRequest(
                    symbol_or_symbols=symbol,
                    timeframe=TimeFrame.Minute,
                    start=start_date
                )
                
                bars = self.client.get_stock_bars(request)
                
                if symbol in bars.data:
                    df = pd.DataFrame([{
                        'timestamp': bar.timestamp,
                        'open': bar.open,
                        'high': bar.high,
                        'low': bar.low,
                        'close': bar.close,
                        'volume': bar.volume,
                        'vwap': bar.vwap
                    } for bar in bars.data[symbol]])
                    
                    df.set_index('timestamp', inplace=True)
                    data[symbol] = df
                    print(f"  [OK] {symbol}: {len(df):,} bars")
                    
            except Exception as e:
                print(f"  [ERROR] {symbol}: {e}")
        
        return data
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators"""
        df = df.copy()
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']
        
        # Returns
        df['returns_1'] = close.pct_change() * 100
        df['returns_5'] = close.pct_change(5) * 100
        df['returns_10'] = close.pct_change(10) * 100
        
        # EMAs
        df['ema9'] = close.ewm(span=9, adjust=False).mean()
        df['ema21'] = close.ewm(span=21, adjust=False).mean()
        df['ema50'] = close.ewm(span=50, adjust=False).mean()
        
        # Price to EMA ratios
        df['price_to_ema9'] = close / df['ema9']
        df['price_to_ema21'] = close / df['ema21']
        df['price_to_ema50'] = close / df['ema50']
        
        # RSI (7 periods - aggressive for 0DTE)
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(window=7).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=7).mean()
        rs = gain / loss.replace(0, np.nan)
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # MACD (fast for 0DTE)
        ema_fast = close.ewm(span=6, adjust=False).mean()
        ema_slow = close.ewm(span=26, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=5, adjust=False).mean()
        df['macd_hist'] = macd_line - signal_line
        
        # ATR
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=14).mean()
        df['atr_pct'] = df['atr'] / close * 100
        
        # ADX
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
        plus_di = 100 * (plus_dm.rolling(14).mean() / df['atr'])
        minus_di = 100 * (minus_dm.rolling(14).mean() / df['atr'])
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        df['adx'] = dx.rolling(14).mean()
        
        # Volume ratio
        df['volume_sma'] = volume.rolling(20).mean()
        df['volume_ratio'] = volume / df['volume_sma']
        
        # Time features
        df['hour'] = df.index.hour
        df['minute'] = df.index.minute
        df['minutes_to_close'] = (16 * 60) - (df['hour'] * 60 + df['minute'])
        df['day_of_week'] = df.index.dayofweek
        
        return df
    
    def create_labels(self, df: pd.DataFrame, lookahead: int = 15) -> pd.DataFrame:
        """
        Create target labels for training
        
        Labels:
        0 = Price goes DOWN in next N minutes
        1 = Price stays NEUTRAL (< 0.1% move)
        2 = Price goes UP in next N minutes
        """
        df = df.copy()
        
        # Future return
        df['future_return'] = df['close'].shift(-lookahead) / df['close'] - 1
        
        # Create labels
        threshold = 0.001  # 0.1% threshold for neutral
        
        df['target'] = 1  # Neutral by default
        df.loc[df['future_return'] > threshold, 'target'] = 2   # Up
        df.loc[df['future_return'] < -threshold, 'target'] = 0  # Down
        
        return df
    
    def prepare_training_data(self, data: Dict[str, pd.DataFrame]) -> Tuple[pd.DataFrame, pd.Series]:
        """Prepare features and labels for training"""
        print("\n[FEATURES] Engineering features...")
        
        all_features = []
        all_labels = []
        
        for symbol, df in data.items():
            # Calculate indicators
            df = self.calculate_indicators(df)
            
            # Create labels
            df = self.create_labels(df)
            
            # Filter trading hours only (9:30 AM - 4:00 PM ET)
            df = df[(df['hour'] >= 9) & (df['hour'] < 16)]
            df = df[~((df['hour'] == 9) & (df['minute'] < 30))]
            
            # Select features
            feature_cols = [
                'returns_1', 'returns_5', 'returns_10',
                'rsi', 'adx',
                'price_to_ema9', 'price_to_ema21', 'price_to_ema50',
                'macd_hist',
                'volume_ratio',
                'atr', 'atr_pct',
                'hour', 'minute', 'minutes_to_close',
                'day_of_week'
            ]
            
            # Drop NaN rows
            df = df.dropna(subset=feature_cols + ['target'])
            
            if len(df) > 0:
                all_features.append(df[feature_cols])
                all_labels.append(df['target'])
        
        # Combine all data
        X = pd.concat(all_features, ignore_index=True)
        y = pd.concat(all_labels, ignore_index=True)
        
        print(f"  Total samples: {len(X):,}")
        print(f"  Features: {len(feature_cols)}")
        print(f"  Label distribution:")
        print(f"    DOWN (0): {(y == 0).sum():,} ({(y == 0).mean()*100:.1f}%)")
        print(f"    NEUTRAL (1): {(y == 1).sum():,} ({(y == 1).mean()*100:.1f}%)")
        print(f"    UP (2): {(y == 2).sum():,} ({(y == 2).mean()*100:.1f}%)")
        
        return X, y
    
    def train_models(self, X: pd.DataFrame, y: pd.Series) -> Dict:
        """Train ensemble models"""
        print("\n[TRAINING] Training models...")
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
        
        print(f"  Train size: {len(X_train):,}")
        print(f"  Test size: {len(X_test):,}")
        
        models = {}
        
        # 1. Random Forest
        print("\n  [1/3] Training Random Forest...")
        rf_model = RandomForestClassifier(
            n_estimators=200,
            max_depth=15,
            min_samples_split=10,
            min_samples_leaf=5,
            random_state=42,
            n_jobs=-1
        )
        rf_model.fit(X_train, y_train)
        rf_pred = rf_model.predict(X_test)
        rf_acc = accuracy_score(y_test, rf_pred)
        print(f"    Accuracy: {rf_acc*100:.2f}%")
        models['rf_model'] = rf_model
        
        # 2. XGBoost
        print("\n  [2/3] Training XGBoost...")
        xgb_model = xgb.XGBClassifier(
            n_estimators=200,
            max_depth=10,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            use_label_encoder=False,
            eval_metric='mlogloss'
        )
        xgb_model.fit(X_train, y_train)
        xgb_pred = xgb_model.predict(X_test)
        xgb_acc = accuracy_score(y_test, xgb_pred)
        print(f"    Accuracy: {xgb_acc*100:.2f}%")
        models['xgb_model'] = xgb_model
        
        # 3. LightGBM
        print("\n  [3/3] Training LightGBM...")
        lgb_model = lgb.LGBMClassifier(
            n_estimators=200,
            max_depth=10,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            verbose=-1
        )
        lgb_model.fit(X_train, y_train)
        lgb_pred = lgb_model.predict(X_test)
        lgb_acc = accuracy_score(y_test, lgb_pred)
        print(f"    Accuracy: {lgb_acc*100:.2f}%")
        models['lgb_model'] = lgb_model
        
        # Ensemble prediction
        print("\n  [ENSEMBLE] Combining models...")
        ensemble_pred = np.round(
            (rf_pred + xgb_pred + lgb_pred) / 3
        ).astype(int)
        ensemble_acc = accuracy_score(y_test, ensemble_pred)
        print(f"    Ensemble Accuracy: {ensemble_acc*100:.2f}%")
        
        # Feature importance
        print("\n  [IMPORTANCE] Top features:")
        importance = pd.DataFrame({
            'feature': X.columns,
            'importance': rf_model.feature_importances_
        }).sort_values('importance', ascending=False)
        
        for i, row in importance.head(10).iterrows():
            print(f"    {row['feature']}: {row['importance']*100:.1f}%")
        
        # Store feature names
        models['feature_names'] = list(X.columns)
        
        # Store metrics
        models['metrics'] = {
            'rf_accuracy': rf_acc,
            'xgb_accuracy': xgb_acc,
            'lgb_accuracy': lgb_acc,
            'ensemble_accuracy': ensemble_acc,
            'train_samples': len(X_train),
            'test_samples': len(X_test),
            'training_date': datetime.now().isoformat()
        }
        
        return models
    
    def save_models(self, models: Dict, output_path: str = "models/ai_0dte_model.pkl"):
        """Save trained models"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        joblib.dump(models, output_path)
        print(f"\n[SAVED] Models saved to {output_path}")
        
        # Also save a backup with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"models/ai_0dte_model_{timestamp}.pkl"
        joblib.dump(models, backup_path)
        print(f"[BACKUP] Backup saved to {backup_path}")
    
    def run(self, symbols: List[str] = None, days: int = 60):
        """Run the full training pipeline"""
        print("\n" + "=" * 60)
        print("    BEAST TRAINING PIPELINE")
        print("=" * 60)
        
        if symbols is None:
            symbols = self.default_symbols
        
        # 1. Download data
        data = self.download_data(symbols, days)
        
        if not data:
            print("[ERROR] No data downloaded!")
            return
        
        # 2. Prepare training data
        X, y = self.prepare_training_data(data)
        
        if len(X) < 1000:
            print(f"[WARNING] Only {len(X)} samples - need more data for good training!")
        
        # 3. Train models
        models = self.train_models(X, y)
        
        # 4. Save models
        self.save_models(models)
        
        print("\n" + "=" * 60)
        print("    TRAINING COMPLETE!")
        print("=" * 60)
        print(f"\n  Ensemble Accuracy: {models['metrics']['ensemble_accuracy']*100:.2f}%")
        print(f"  Training Samples: {models['metrics']['train_samples']:,}")
        print(f"  Training Date: {models['metrics']['training_date']}")
        print("\n  The BEAST has learned from fresh data!")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='BEAST Engine Model Trainer')
    parser.add_argument('--days', type=int, default=60, 
                       help='Days of historical data to use (default: 60)')
    parser.add_argument('--symbols', nargs='+', default=None,
                       help='Symbols to train on (default: top 20 0DTE stocks)')
    
    args = parser.parse_args()
    
    # Load config
    config = load_config()
    
    # Initialize trainer
    trainer = BeastTrainer(config)
    
    # Run training
    trainer.run(symbols=args.symbols, days=args.days)


if __name__ == "__main__":
    main()
