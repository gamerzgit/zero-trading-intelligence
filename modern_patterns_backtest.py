#!/usr/bin/env python3
"""
================================================================================
    BACKTEST DE PATRONES MODERNOS
================================================================================
    
    Probando patrones que realmente funcionan en 2024-2026:
    
    1. ORB Breakout (Opening Range Breakout)
    2. VWAP Bounce / Rejection
    3. RSI Extremes (Oversold/Overbought reversals)
    4. Gap Fill
    5. Momentum Ignition (Volume spike + price move)
    6. Power Hour Reversal
    7. Trap / Failed Breakout
    8. MACD Zero Line Cross
    
================================================================================
"""

import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import yaml

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit


def load_config():
    with open("config.yaml", 'r') as f:
        return yaml.safe_load(f)


class ModernPatternBacktest:
    """Backtest de patrones que funcionan en mercados modernos"""
    
    def __init__(self, config: Dict):
        self.client = StockHistoricalDataClient(
            config['alpaca']['api_key'],
            config['alpaca']['api_secret']
        )
    
    async def fetch_data(self, symbol: str, days: int = 90) -> pd.DataFrame:
        """Fetch data"""
        try:
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame(15, TimeFrameUnit.Minute),
                start=datetime.now() - timedelta(days=days)
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
                df['hour'] = df.index.hour
                df['minute'] = df.index.minute
                return df
            return pd.DataFrame()
        except Exception as e:
            print(f"Error: {e}")
            return pd.DataFrame()
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcula indicadores necesarios"""
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']
        
        # RSI (7 periodos - agresivo para 0DTE)
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(window=7).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=7).mean()
        rs = gain / loss.replace(0, np.nan)
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # MACD (6, 13, 5 - rápido para 0DTE)
        ema_fast = close.ewm(span=6, adjust=False).mean()
        ema_slow = close.ewm(span=13, adjust=False).mean()
        df['macd'] = ema_fast - ema_slow
        df['macd_signal'] = df['macd'].ewm(span=5, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        # EMAs
        df['ema9'] = close.ewm(span=9, adjust=False).mean()
        df['ema21'] = close.ewm(span=21, adjust=False).mean()
        
        # ATR
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=14).mean()
        
        # Volume SMA
        df['vol_sma'] = volume.rolling(20).mean()
        df['vol_ratio'] = volume / df['vol_sma']
        
        # Daily change
        df['change_pct'] = close.pct_change() * 100
        
        return df
    
    def backtest_orb_breakout(self, df: pd.DataFrame) -> Dict:
        """
        Opening Range Breakout
        - Primeros 15-30 min definen el rango
        - Breakout arriba = CALL
        - Breakdown abajo = PUT
        """
        results = []
        
        # Agrupar por día
        df['date'] = df.index.date
        
        for date, day_df in df.groupby('date'):
            if len(day_df) < 20:
                continue
            
            # Filtrar market hours (9:30 - 16:00)
            market_df = day_df[(day_df['hour'] >= 9) & (day_df['hour'] < 16)]
            if len(market_df) < 10:
                continue
            
            # ORB = Primeras 2 barras de 15min (9:30-10:00)
            orb_df = market_df[(market_df['hour'] == 9) | 
                              ((market_df['hour'] == 10) & (market_df['minute'] == 0))]
            
            if len(orb_df) < 2:
                continue
            
            orb_high = orb_df['high'].max()
            orb_low = orb_df['low'].min()
            orb_range = orb_high - orb_low
            
            # Buscar breakout después del ORB
            post_orb = market_df[(market_df['hour'] >= 10) & (market_df['hour'] < 15)]
            
            for i in range(len(post_orb)):
                row = post_orb.iloc[i]
                
                # Breakout UP
                if row['close'] > orb_high * 1.002:  # 0.2% arriba del ORB high
                    entry_price = row['close']
                    # Ver qué pasa en los próximos 4 bars (1 hora)
                    future = post_orb.iloc[i+1:i+5]
                    if len(future) >= 2:
                        max_price = future['high'].max()
                        min_price = future['low'].min()
                        final_price = future['close'].iloc[-1] if len(future) > 0 else entry_price
                        
                        pct_change = (final_price - entry_price) / entry_price * 100
                        max_gain = (max_price - entry_price) / entry_price * 100
                        max_loss = (entry_price - min_price) / entry_price * 100
                        
                        results.append({
                            'direction': 'CALL',
                            'pct_change': pct_change,
                            'max_gain': max_gain,
                            'max_loss': max_loss,
                            'win': pct_change > 0.3
                        })
                    break  # Solo un trade por día
                
                # Breakdown DOWN
                elif row['close'] < orb_low * 0.998:
                    entry_price = row['close']
                    future = post_orb.iloc[i+1:i+5]
                    if len(future) >= 2:
                        max_price = future['high'].max()
                        min_price = future['low'].min()
                        final_price = future['close'].iloc[-1] if len(future) > 0 else entry_price
                        
                        pct_change = (entry_price - final_price) / entry_price * 100
                        
                        results.append({
                            'direction': 'PUT',
                            'pct_change': pct_change,
                            'win': pct_change > 0.3
                        })
                    break
        
        return self._calculate_stats(results, "ORB Breakout")
    
    def backtest_vwap_bounce(self, df: pd.DataFrame) -> Dict:
        """
        VWAP Bounce
        - Precio toca VWAP desde abajo y rebota = CALL
        - Precio toca VWAP desde arriba y rechaza = PUT
        """
        results = []
        
        for i in range(5, len(df) - 5):
            row = df.iloc[i]
            prev = df.iloc[i-1]
            
            vwap = row['vwap']
            close = row['close']
            prev_close = prev['close']
            
            # Skip if not market hours
            if row['hour'] < 10 or row['hour'] >= 15:
                continue
            
            # VWAP Bounce UP: precio estaba debajo, toca VWAP, rebota arriba
            if prev_close < vwap and close > vwap:
                # Confirmación: siguiente barra también arriba
                if df.iloc[i+1]['close'] > vwap:
                    entry = df.iloc[i+1]['close']
                    future = df.iloc[i+2:i+6]
                    
                    if len(future) >= 2:
                        final = future['close'].iloc[-1]
                        pct = (final - entry) / entry * 100
                        results.append({
                            'direction': 'CALL',
                            'pct_change': pct,
                            'win': pct > 0.2
                        })
            
            # VWAP Rejection DOWN
            elif prev_close > vwap and close < vwap:
                if df.iloc[i+1]['close'] < vwap:
                    entry = df.iloc[i+1]['close']
                    future = df.iloc[i+2:i+6]
                    
                    if len(future) >= 2:
                        final = future['close'].iloc[-1]
                        pct = (entry - final) / entry * 100
                        results.append({
                            'direction': 'PUT',
                            'pct_change': pct,
                            'win': pct > 0.2
                        })
        
        return self._calculate_stats(results, "VWAP Bounce")
    
    def backtest_rsi_extreme(self, df: pd.DataFrame) -> Dict:
        """
        RSI Extremes
        - RSI < 25 = Oversold, buscar reversal UP
        - RSI > 75 = Overbought, buscar reversal DOWN
        """
        results = []
        
        for i in range(5, len(df) - 5):
            row = df.iloc[i]
            rsi = row['rsi']
            
            if pd.isna(rsi):
                continue
            
            if row['hour'] < 10 or row['hour'] >= 15:
                continue
            
            # Oversold reversal
            if rsi < 25:
                # Esperar confirmación: RSI sube en siguiente barra
                next_rsi = df.iloc[i+1]['rsi']
                if not pd.isna(next_rsi) and next_rsi > rsi:
                    entry = df.iloc[i+1]['close']
                    future = df.iloc[i+2:i+6]
                    
                    if len(future) >= 2:
                        final = future['close'].iloc[-1]
                        pct = (final - entry) / entry * 100
                        results.append({
                            'direction': 'CALL',
                            'pct_change': pct,
                            'win': pct > 0.3,
                            'rsi_entry': rsi
                        })
            
            # Overbought reversal
            elif rsi > 75:
                next_rsi = df.iloc[i+1]['rsi']
                if not pd.isna(next_rsi) and next_rsi < rsi:
                    entry = df.iloc[i+1]['close']
                    future = df.iloc[i+2:i+6]
                    
                    if len(future) >= 2:
                        final = future['close'].iloc[-1]
                        pct = (entry - final) / entry * 100
                        results.append({
                            'direction': 'PUT',
                            'pct_change': pct,
                            'win': pct > 0.3,
                            'rsi_entry': rsi
                        })
        
        return self._calculate_stats(results, "RSI Extreme")
    
    def backtest_momentum_ignition(self, df: pd.DataFrame) -> Dict:
        """
        Momentum Ignition
        - Barra con volumen 2x+ del promedio
        - Movimiento >0.3% en una barra
        - Continúa en la misma dirección
        """
        results = []
        
        for i in range(5, len(df) - 5):
            row = df.iloc[i]
            
            if row['hour'] < 10 or row['hour'] >= 15:
                continue
            
            vol_ratio = row['vol_ratio']
            change = row['change_pct']
            
            if pd.isna(vol_ratio) or pd.isna(change):
                continue
            
            # Momentum ignition UP
            if vol_ratio > 2.0 and change > 0.3:
                entry = row['close']
                future = df.iloc[i+1:i+5]
                
                if len(future) >= 2:
                    final = future['close'].iloc[-1]
                    pct = (final - entry) / entry * 100
                    results.append({
                        'direction': 'CALL',
                        'pct_change': pct,
                        'win': pct > 0.2,
                        'vol_ratio': vol_ratio
                    })
            
            # Momentum ignition DOWN
            elif vol_ratio > 2.0 and change < -0.3:
                entry = row['close']
                future = df.iloc[i+1:i+5]
                
                if len(future) >= 2:
                    final = future['close'].iloc[-1]
                    pct = (entry - final) / entry * 100
                    results.append({
                        'direction': 'PUT',
                        'pct_change': pct,
                        'win': pct > 0.2,
                        'vol_ratio': vol_ratio
                    })
        
        return self._calculate_stats(results, "Momentum Ignition")
    
    def backtest_power_hour(self, df: pd.DataFrame) -> Dict:
        """
        Power Hour (3-4 PM)
        - Momentum continúa del día
        - Si precio > VWAP y EMA9 > EMA21 = CALL
        - Si precio < VWAP y EMA9 < EMA21 = PUT
        """
        results = []
        
        df['date'] = df.index.date
        
        for date, day_df in df.groupby('date'):
            # Solo power hour
            ph_df = day_df[day_df['hour'] == 15]
            
            if len(ph_df) < 2:
                continue
            
            first_bar = ph_df.iloc[0]
            
            # Condiciones para CALL
            if (first_bar['close'] > first_bar['vwap'] and 
                first_bar['ema9'] > first_bar['ema21'] and
                first_bar['macd_hist'] > 0):
                
                entry = first_bar['close']
                future = ph_df.iloc[1:4]
                
                if len(future) >= 1:
                    final = future['close'].iloc[-1]
                    pct = (final - entry) / entry * 100
                    results.append({
                        'direction': 'CALL',
                        'pct_change': pct,
                        'win': pct > 0.2
                    })
            
            # Condiciones para PUT
            elif (first_bar['close'] < first_bar['vwap'] and 
                  first_bar['ema9'] < first_bar['ema21'] and
                  first_bar['macd_hist'] < 0):
                
                entry = first_bar['close']
                future = ph_df.iloc[1:4]
                
                if len(future) >= 1:
                    final = future['close'].iloc[-1]
                    pct = (entry - final) / entry * 100
                    results.append({
                        'direction': 'PUT',
                        'pct_change': pct,
                        'win': pct > 0.2
                    })
        
        return self._calculate_stats(results, "Power Hour")
    
    def backtest_macd_zero_cross(self, df: pd.DataFrame) -> Dict:
        """
        MACD Zero Line Cross
        - MACD cruza arriba de 0 = CALL
        - MACD cruza abajo de 0 = PUT
        """
        results = []
        
        for i in range(2, len(df) - 5):
            curr_macd = df.iloc[i]['macd']
            prev_macd = df.iloc[i-1]['macd']
            
            if pd.isna(curr_macd) or pd.isna(prev_macd):
                continue
            
            if df.iloc[i]['hour'] < 10 or df.iloc[i]['hour'] >= 15:
                continue
            
            # Cross above zero
            if prev_macd < 0 and curr_macd > 0:
                entry = df.iloc[i]['close']
                future = df.iloc[i+1:i+5]
                
                if len(future) >= 2:
                    final = future['close'].iloc[-1]
                    pct = (final - entry) / entry * 100
                    results.append({
                        'direction': 'CALL',
                        'pct_change': pct,
                        'win': pct > 0.2
                    })
            
            # Cross below zero
            elif prev_macd > 0 and curr_macd < 0:
                entry = df.iloc[i]['close']
                future = df.iloc[i+1:i+5]
                
                if len(future) >= 2:
                    final = future['close'].iloc[-1]
                    pct = (entry - final) / entry * 100
                    results.append({
                        'direction': 'PUT',
                        'pct_change': pct,
                        'win': pct > 0.2
                    })
        
        return self._calculate_stats(results, "MACD Zero Cross")
    
    def backtest_failed_breakout(self, df: pd.DataFrame) -> Dict:
        """
        Failed Breakout (Trap)
        - Precio rompe un high reciente pero falla y reversa
        - Señal contrarian fuerte
        """
        results = []
        
        # Calcular highs/lows de 20 barras
        df['high_20'] = df['high'].rolling(20).max()
        df['low_20'] = df['low'].rolling(20).min()
        
        for i in range(25, len(df) - 5):
            row = df.iloc[i]
            prev = df.iloc[i-1]
            
            if row['hour'] < 10 or row['hour'] >= 15:
                continue
            
            high_20 = df.iloc[i-1]['high_20']
            low_20 = df.iloc[i-1]['low_20']
            
            if pd.isna(high_20) or pd.isna(low_20):
                continue
            
            # Failed breakout UP (Bull Trap) = PUT signal
            if prev['high'] > high_20 and row['close'] < prev['close']:
                # Confirmación: precio cae más en siguiente barra
                if df.iloc[i+1]['close'] < row['close']:
                    entry = df.iloc[i+1]['close']
                    future = df.iloc[i+2:i+6]
                    
                    if len(future) >= 2:
                        final = future['close'].iloc[-1]
                        pct = (entry - final) / entry * 100
                        results.append({
                            'direction': 'PUT (Bull Trap)',
                            'pct_change': pct,
                            'win': pct > 0.3
                        })
            
            # Failed breakdown (Bear Trap) = CALL signal
            elif prev['low'] < low_20 and row['close'] > prev['close']:
                if df.iloc[i+1]['close'] > row['close']:
                    entry = df.iloc[i+1]['close']
                    future = df.iloc[i+2:i+6]
                    
                    if len(future) >= 2:
                        final = future['close'].iloc[-1]
                        pct = (final - entry) / entry * 100
                        results.append({
                            'direction': 'CALL (Bear Trap)',
                            'pct_change': pct,
                            'win': pct > 0.3
                        })
        
        return self._calculate_stats(results, "Failed Breakout (Trap)")
    
    def _calculate_stats(self, results: List[Dict], name: str) -> Dict:
        """Calcula estadísticas del backtest"""
        if not results:
            return {
                'name': name,
                'sample_size': 0,
                'win_rate': 0,
                'avg_return': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'expected_value': 0,
                'profit_factor': 0
            }
        
        wins = [r for r in results if r['win']]
        losses = [r for r in results if not r['win']]
        
        win_rate = len(wins) / len(results)
        
        avg_return = np.mean([r['pct_change'] for r in results])
        avg_win = np.mean([r['pct_change'] for r in wins]) if wins else 0
        avg_loss = np.mean([abs(r['pct_change']) for r in losses]) if losses else 0
        
        expected_value = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        
        total_wins = sum([r['pct_change'] for r in wins]) if wins else 0
        total_losses = sum([abs(r['pct_change']) for r in losses]) if losses else 0.001
        profit_factor = total_wins / total_losses if total_losses > 0 else 0
        
        return {
            'name': name,
            'sample_size': len(results),
            'win_rate': round(win_rate * 100, 1),
            'avg_return': round(avg_return, 3),
            'avg_win': round(avg_win, 3),
            'avg_loss': round(avg_loss, 3),
            'expected_value': round(expected_value, 3),
            'profit_factor': round(profit_factor, 2)
        }
    
    async def run_all_backtests(self, symbols: List[str] = None):
        """Corre todos los backtests"""
        if symbols is None:
            symbols = ["SPY", "QQQ", "NVDA", "TSLA", "AMD", "META"]
        
        print("\n" + "=" * 70)
        print("  BACKTEST DE PATRONES MODERNOS")
        print("  Timeframe: 15 minutos | Datos: 90 dias")
        print("=" * 70)
        
        all_results = {
            'ORB Breakout': [],
            'VWAP Bounce': [],
            'RSI Extreme': [],
            'Momentum Ignition': [],
            'Power Hour': [],
            'MACD Zero Cross': [],
            'Failed Breakout (Trap)': []
        }
        
        for symbol in symbols:
            print(f"\n  Procesando {symbol}...")
            
            df = await self.fetch_data(symbol, days=90)
            if df.empty:
                print(f"    No hay datos para {symbol}")
                continue
            
            df = self.calculate_indicators(df)
            
            # Correr cada backtest
            orb = self.backtest_orb_breakout(df)
            vwap = self.backtest_vwap_bounce(df)
            rsi = self.backtest_rsi_extreme(df)
            momentum = self.backtest_momentum_ignition(df)
            power = self.backtest_power_hour(df)
            macd = self.backtest_macd_zero_cross(df)
            trap = self.backtest_failed_breakout(df)
            
            for name, result in [('ORB Breakout', orb), ('VWAP Bounce', vwap),
                                 ('RSI Extreme', rsi), ('Momentum Ignition', momentum),
                                 ('Power Hour', power), ('MACD Zero Cross', macd),
                                 ('Failed Breakout (Trap)', trap)]:
                if result['sample_size'] > 0:
                    all_results[name].append(result)
        
        # Combinar resultados
        print("\n" + "=" * 70)
        print("  RESULTADOS COMBINADOS (Todos los simbolos)")
        print("=" * 70)
        
        final_results = []
        
        for name, results_list in all_results.items():
            if not results_list:
                continue
            
            total_samples = sum(r['sample_size'] for r in results_list)
            
            if total_samples == 0:
                continue
            
            # Weighted average
            weighted_wr = sum(r['win_rate'] * r['sample_size'] for r in results_list) / total_samples
            weighted_ev = sum(r['expected_value'] * r['sample_size'] for r in results_list) / total_samples
            weighted_pf = sum(r['profit_factor'] * r['sample_size'] for r in results_list) / total_samples
            avg_win = np.mean([r['avg_win'] for r in results_list if r['avg_win'] > 0])
            avg_loss = np.mean([r['avg_loss'] for r in results_list if r['avg_loss'] > 0])
            
            final_results.append({
                'name': name,
                'sample_size': total_samples,
                'win_rate': round(weighted_wr, 1),
                'avg_win': round(avg_win, 2) if not np.isnan(avg_win) else 0,
                'avg_loss': round(avg_loss, 2) if not np.isnan(avg_loss) else 0,
                'expected_value': round(weighted_ev, 3),
                'profit_factor': round(weighted_pf, 2)
            })
        
        # Ordenar por Expected Value
        final_results.sort(key=lambda x: x['expected_value'], reverse=True)
        
        # Mostrar tabla
        print(f"\n  {'Patron':<25} {'Samples':>8} {'Win%':>8} {'AvgWin':>8} {'AvgLoss':>8} {'EV':>8} {'PF':>6}")
        print("-" * 80)
        
        for r in final_results:
            ev_color = "+" if r['expected_value'] > 0 else ""
            print(f"  {r['name']:<25} {r['sample_size']:>8} {r['win_rate']:>7.1f}% "
                  f"{r['avg_win']:>7.2f}% {r['avg_loss']:>7.2f}% "
                  f"{ev_color}{r['expected_value']:>7.3f} {r['profit_factor']:>6.2f}")
        
        # Conclusiones
        print("\n" + "=" * 70)
        print("  CONCLUSIONES")
        print("=" * 70)
        
        winners = [r for r in final_results if r['expected_value'] > 0]
        losers = [r for r in final_results if r['expected_value'] <= 0]
        
        if winners:
            print("\n  PATRONES CON VENTAJA ESTADISTICA (EV > 0):")
            for r in winners:
                print(f"    - {r['name']}: Win Rate {r['win_rate']}%, EV +{r['expected_value']}")
        else:
            print("\n  NINGUN PATRON TIENE EV POSITIVO EN ESTE PERIODO")
        
        if losers:
            print("\n  PATRONES SIN VENTAJA (EV <= 0):")
            for r in losers:
                print(f"    - {r['name']}: Win Rate {r['win_rate']}%, EV {r['expected_value']}")
        
        return final_results


async def main():
    print("""
    ================================================================
    |    BACKTEST DE PATRONES MODERNOS                             |
    |    Probando que realmente funciona en 2024-2026              |
    ================================================================
    """)
    
    config = load_config()
    backtest = ModernPatternBacktest(config)
    
    results = await backtest.run_all_backtests(
        symbols=["SPY", "QQQ", "NVDA", "TSLA", "AMD", "META", "AAPL", "MSFT"]
    )
    
    return results


if __name__ == "__main__":
    asyncio.run(main())
