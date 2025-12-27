"""
KRAKEN SWING BOT - BACKTESTING OPTIMIZADO
Data: yfinance 1h, 2 años, ADA-USD
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
from typing import Tuple, Optional

# ═══════════════════════════════════════════════════════════════════════════
#                        DETECTOR DE SWING POINTS
# ═══════════════════════════════════════════════════════════════════════════

class SwingDetector:
    def __init__(self, data: pd.DataFrame):
        self.data = data.copy()
        self.short_term_highs = pd.Series(index=data.index, dtype=float)
        self.short_term_lows = pd.Series(index=data.index, dtype=float)
        self.intermediate_highs = pd.Series(index=data.index, dtype=float)
        self.intermediate_lows = pd.Series(index=data.index, dtype=float)
    
    def detect_all_swings(self):
        """Detecta todos los swing points de una vez."""
        highs = self.data['High'].values
        lows = self.data['Low'].values
        
        # Short-term
        for i in range(1, len(lows) - 1):
            if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                self.short_term_lows.iloc[i] = lows[i]
        
        for i in range(1, len(highs) - 1):
            if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                self.short_term_highs.iloc[i] = highs[i]
        
        # Intermediate
        st_high_indices = self.short_term_highs.dropna().index.tolist()
        for i in range(1, len(st_high_indices) - 1):
            prev_idx = st_high_indices[i-1]
            curr_idx = st_high_indices[i]
            next_idx = st_high_indices[i+1]
            
            curr_val = self.short_term_highs[curr_idx]
            prev_val = self.short_term_highs[prev_idx]
            next_val = self.short_term_highs[next_idx]
            
            if curr_val > prev_val and curr_val > next_val:
                self.intermediate_highs[curr_idx] = curr_val
        
        st_low_indices = self.short_term_lows.dropna().index.tolist()
        for i in range(1, len(st_low_indices) - 1):
            prev_idx = st_low_indices[i-1]
            curr_idx = st_low_indices[i]
            next_idx = st_low_indices[i+1]
            
            curr_val = self.short_term_lows[curr_idx]
            prev_val = self.short_term_lows[prev_idx]
            next_val = self.short_term_lows[next_idx]
            
            if curr_val < prev_val and curr_val < next_val:
                self.intermediate_lows[curr_idx] = curr_val
        
        return self.intermediate_highs, self.intermediate_lows
    
    def get_signal_at_date(self, date):
        """Obtiene la señal vigente en una fecha específica."""
        highs = self.intermediate_highs.loc[:date].dropna()
        lows = self.intermediate_lows.loc[:date].dropna()
        
        if len(highs) == 0 and len(lows) == 0:
            return None, None
        
        last_high = highs.index[-1] if len(highs) > 0 else pd.Timestamp.min
        last_low = lows.index[-1] if len(lows) > 0 else pd.Timestamp.min
        
        if last_low > last_high:
            return 'BUY', lows.iloc[-1]
        elif last_high > last_low:
            return 'SELL', highs.iloc[-1]
        else:
            return None, None


# ═══════════════════════════════════════════════════════════════════════════
#                        BACKTESTER OPTIMIZADO
# ═══════════════════════════════════════════════════════════════════════════

class SwingBacktester:
    def __init__(self, data: pd.DataFrame, initial_capital: float = 1000.0,
                 position_size_pct: float = 0.30, leverage: int = 3):
        self.data = data.copy()
        self.initial_capital = initial_capital
        self.position_size_pct = position_size_pct
        self.leverage = leverage
        
        self.position = None
        self.entry_price = 0
        self.entry_date = None
        self.capital = initial_capital
        self.trades = []
        self.equity_curve = []
        
        # Pre-calcular swings
        print("🔍 Calculando swing points...")
        self.detector = SwingDetector(data)
        self.detector.detect_all_swings()
        
        highs_count = self.detector.intermediate_highs.notna().sum()
        lows_count = self.detector.intermediate_lows.notna().sum()
        print(f"   ✓ {highs_count} highs, {lows_count} lows detectados")
    
    def run(self):
        print(f"\n{'='*70}")
        print(f"BACKTESTING - INTERMEDIATE SWINGS")
        print(f"{'='*70}")
        print(f"Capital inicial: ${self.initial_capital:.2f}")
        print(f"Tamaño posición: {self.position_size_pct*100}%")
        print(f"Leverage: {self.leverage}x")
        print(f"Período: {self.data.index[0]} - {self.data.index[-1]}")
        print(f"Total velas: {len(self.data)}")
        print(f"\n⏳ Ejecutando backtest...")
        
        for i in range(30, len(self.data)):  # Empezar en 30 para tener historia
            current_date = self.data.index[i]
            current_price = self.data['Close'].iloc[i]
            
            # Equity
            if self.position:
                if self.position == 'LONG':
                    unrealized_pnl = (current_price - self.entry_price) * self.leverage
                else:
                    unrealized_pnl = (self.entry_price - current_price) * self.leverage
                
                unrealized_pnl_dollars = (unrealized_pnl / self.entry_price) * (self.capital * self.position_size_pct)
                current_equity = self.capital + unrealized_pnl_dollars
            else:
                current_equity = self.capital
            
            self.equity_curve.append({
                'Date': current_date,
                'Equity': current_equity,
                'Position': self.position
            })
            
            # Obtener señal
            signal, signal_price = self.detector.get_signal_at_date(current_date)
            
            if signal is None:
                continue
            
            # Trading logic
            if self.position is None:
                self.position = 'LONG' if signal == 'BUY' else 'SHORT'
                self.entry_price = current_price
                self.entry_date = current_date
                
            elif (self.position == 'LONG' and signal == 'SELL') or \
                 (self.position == 'SHORT' and signal == 'BUY'):
                
                # Cerrar
                if self.position == 'LONG':
                    pnl = (current_price - self.entry_price) * self.leverage
                else:
                    pnl = (self.entry_price - current_price) * self.leverage
                
                pnl_pct = (pnl / self.entry_price) * 100
                pnl_dollars = (pnl / self.entry_price) * (self.capital * self.position_size_pct)
                
                self.capital += pnl_dollars
                
                self.trades.append({
                    'Entry_Date': self.entry_date,
                    'Exit_Date': current_date,
                    'Type': self.position,
                    'Entry_Price': self.entry_price,
                    'Exit_Price': current_price,
                    'PnL_Pct': pnl_pct,
                    'PnL_Dollars': pnl_dollars,
                    'Capital': self.capital
                })
                
                # Abrir nueva
                self.position = 'LONG' if signal == 'BUY' else 'SHORT'
                self.entry_price = current_price
                self.entry_date = current_date
            
            # Progress
            if i % 2000 == 0:
                progress = (i / len(self.data)) * 100
                print(f"   {progress:.1f}% completado...")
        
        # Cerrar final
        if self.position:
            final_price = self.data['Close'].iloc[-1]
            if self.position == 'LONG':
                pnl = (final_price - self.entry_price) * self.leverage
            else:
                pnl = (self.entry_price - final_price) * self.leverage
            
            pnl_pct = (pnl / self.entry_price) * 100
            pnl_dollars = (pnl / self.entry_price) * (self.capital * self.position_size_pct)
            self.capital += pnl_dollars
            
            self.trades.append({
                'Entry_Date': self.entry_date,
                'Exit_Date': self.data.index[-1],
                'Type': self.position,
                'Entry_Price': self.entry_price,
                'Exit_Price': final_price,
                'PnL_Pct': pnl_pct,
                'PnL_Dollars': pnl_dollars,
                'Capital': self.capital
            })
        
        print("   ✓ Backtest completado")
        return self.calculate_metrics()
    
    def calculate_metrics(self):
        if len(self.trades) == 0:
            return {
                'Total_Trades': 0,
                'Win_Rate': 0,
                'Total_Return': 0,
                'Total_Return_Pct': 0,
                'Max_Drawdown': 0,
                'Sharpe_Ratio': 0,
                'Trades_DF': pd.DataFrame(),
                'Equity_DF': pd.DataFrame()
            }
        
        trades_df = pd.DataFrame(self.trades)
        equity_df = pd.DataFrame(self.equity_curve)
        
        winning_trades = trades_df[trades_df['PnL_Dollars'] > 0]
        losing_trades = trades_df[trades_df['PnL_Dollars'] < 0]
        
        total_return = self.capital - self.initial_capital
        total_return_pct = (total_return / self.initial_capital) * 100
        
        equity_df['Peak'] = equity_df['Equity'].cummax()
        equity_df['Drawdown'] = (equity_df['Equity'] - equity_df['Peak']) / equity_df['Peak']
        max_drawdown = equity_df['Drawdown'].min() * 100
        
        returns = trades_df['PnL_Pct'].values
        sharpe = (returns.mean() / returns.std()) * np.sqrt(252/24) if len(returns) > 1 and returns.std() > 0 else 0
        
        metrics = {
            'Total_Trades': len(trades_df),
            'Winning_Trades': len(winning_trades),
            'Losing_Trades': len(losing_trades),
            'Win_Rate': (len(winning_trades) / len(trades_df) * 100) if len(trades_df) > 0 else 0,
            'Total_Return': total_return,
            'Total_Return_Pct': total_return_pct,
            'Max_Drawdown': max_drawdown,
            'Sharpe_Ratio': sharpe,
            'Avg_Win': winning_trades['PnL_Dollars'].mean() if len(winning_trades) > 0 else 0,
            'Avg_Loss': losing_trades['PnL_Dollars'].mean() if len(losing_trades) > 0 else 0,
            'Trades_DF': trades_df,
            'Equity_DF': equity_df
        }
        
        return metrics


# ═══════════════════════════════════════════════════════════════════════════
#                        MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("\n" + "="*70)
    print("KRAKEN SWING BOT - BACKTESTING")
    print("="*70)
    
    print("\n📊 Descargando datos de ADA-USD (2 años, 1h)...")
    ticker = yf.Ticker("ADA-USD")
    data = ticker.history(period="2y", interval="1h")
    
    if data.empty:
        print("❌ No se pudieron descargar datos")
        return
    
    print(f"✓ {len(data)} velas descargadas")
    print(f"  Período: {data.index[0]} - {data.index[-1]}")
    
    bt = SwingBacktester(
        data=data,
        initial_capital=40.0,
        position_size_pct=0.30,
        leverage=3
    )
    
    metrics = bt.run()
    
    print(f"\n{'='*70}")
    print("RESULTADOS")
    print(f"{'='*70}")
    print(f"Total trades:       {metrics['Total_Trades']}")
    print(f"Trades ganadores:   {metrics['Winning_Trades']}")
    print(f"Trades perdedores:  {metrics['Losing_Trades']}")
    print(f"Win rate:           {metrics['Win_Rate']:.2f}%")
    print(f"Retorno total:      ${metrics['Total_Return']:.2f} ({metrics['Total_Return_Pct']:.2f}%)")
    print(f"Capital final:      ${metrics['Total_Return'] + 40:.2f}")
    print(f"Drawdown máximo:    {metrics['Max_Drawdown']:.2f}%")
    print(f"Sharpe Ratio:       {metrics['Sharpe_Ratio']:.2f}")
    print(f"Ganancia promedio:  ${metrics['Avg_Win']:.2f}")
    print(f"Pérdida promedio:   ${metrics['Avg_Loss']:.2f}")
    print(f"{'='*70}\n")
    
    if len(metrics['Trades_DF']) > 0:
        print("\nÚltimos 10 trades:")
        print(metrics['Trades_DF'].tail(10)[['Exit_Date', 'Type', 'Entry_Price', 'Exit_Price', 'PnL_Pct', 'PnL_Dollars']].to_string(index=False))
    
    plot_results(metrics)


def plot_results(metrics):
    trades_df = metrics['Trades_DF']
    equity_df = metrics['Equity_DF']
    
    if len(trades_df) == 0:
        print("\n⚠️  No hay trades para graficar")
        return
    
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 10))
    
    ax1.plot(equity_df['Date'], equity_df['Equity'], linewidth=2, color='blue')
    ax1.fill_between(equity_df['Date'], equity_df['Equity'], alpha=0.3)
    ax1.axhline(y=40, color='red', linestyle='--', alpha=0.5, label='Capital inicial')
    ax1.set_title('Curva de Capital', fontsize=14, fontweight='bold')
    ax1.set_ylabel('Capital ($)')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    ax2.fill_between(equity_df['Date'], equity_df['Drawdown']*100, 0, alpha=0.5, color='red')
    ax2.set_title('Drawdown', fontsize=14, fontweight='bold')
    ax2.set_ylabel('Drawdown (%)')
    ax2.grid(True, alpha=0.3)
    
    wins = trades_df[trades_df['PnL_Dollars'] > 0]['PnL_Dollars']
    losses = trades_df[trades_df['PnL_Dollars'] <= 0]['PnL_Dollars']
    
    ax3.hist([wins, losses], bins=20, label=['Ganancias', 'Pérdidas'], color=['green', 'red'], alpha=0.7)
    ax3.set_title('Distribución de Trades', fontsize=14, fontweight='bold')
    ax3.set_xlabel('PnL ($)')
    ax3.set_ylabel('Frecuencia')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('backtest_results.png', dpi=150, bbox_inches='tight')
    print(f"\n✓ Gráficos guardados en: backtest_results.png")
    plt.show()


if __name__ == "__main__":
    main()