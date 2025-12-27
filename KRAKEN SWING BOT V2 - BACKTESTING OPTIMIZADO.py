"""
KRAKEN SWING BOT V2 - BACKTESTING OPTIMIZADO
Mejoras: MTF, Volume Filter, ATR, Stop Loss, Take Profit, Trailing Stop
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
from typing import Tuple, Optional

# ═══════════════════════════════════════════════════════════════════════════
#                        INDICADORES
# ═══════════════════════════════════════════════════════════════════════════

def calculate_atr(data: pd.DataFrame, period: int = 14) -> pd.Series:
    high = data['High']
    low = data['Low']
    close = data['Close']
    
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def calculate_volume_ma(data: pd.DataFrame, period: int = 20) -> pd.Series:
    return data['Volume'].rolling(window=period).mean()


# ═══════════════════════════════════════════════════════════════════════════
#                        DETECTOR OPTIMIZADO
# ═══════════════════════════════════════════════════════════════════════════

class SwingDetectorV2:
    def __init__(self, data: pd.DataFrame, volume_filter: bool = True):
        self.data = data.copy()
        self.volume_filter = volume_filter
        self.volume_ma = calculate_volume_ma(data) if volume_filter else None
        
        self.short_term_highs = pd.Series(index=data.index, dtype=float)
        self.short_term_lows = pd.Series(index=data.index, dtype=float)
        self.intermediate_highs = pd.Series(index=data.index, dtype=float)
        self.intermediate_lows = pd.Series(index=data.index, dtype=float)
    
    def _check_volume(self, index: int) -> bool:
        if not self.volume_filter or self.volume_ma is None:
            return True
        
        if pd.isna(self.volume_ma.iloc[index]):
            return True
        
        return self.data['Volume'].iloc[index] > self.volume_ma.iloc[index]
    
    def detect_all_swings(self):
        highs = self.data['High'].values
        lows = self.data['Low'].values
        
        # Short-term
        for i in range(1, len(lows) - 1):
            if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                if self._check_volume(i):
                    self.short_term_lows.iloc[i] = lows[i]
        
        for i in range(1, len(highs) - 1):
            if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                if self._check_volume(i):
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
#                        BACKTESTER V2
# ═══════════════════════════════════════════════════════════════════════════

class SwingBacktesterV2:
    def __init__(self, data_1h: pd.DataFrame, data_4h: pd.DataFrame = None,
                 initial_capital: float = 40.0,
                 position_size_pct: float = 0.30,
                 leverage: int = 3,
                 # Risk management
                 use_stop_loss: bool = True,
                 stop_loss_pct: float = 4.0,
                 use_take_profit: bool = True,
                 take_profit_pct: float = 8.0,
                 use_trailing_stop: bool = True,
                 trailing_stop_pct: float = 2.5,
                 min_profit_for_trailing: float = 3.0,
                 # Filters
                 use_volume_filter: bool = True,
                 use_mtf_confirmation: bool = True,
                 use_atr_sizing: bool = True):
        
        self.data_1h = data_1h.copy()
        self.data_4h = data_4h.copy() if data_4h is not None else None
        self.initial_capital = initial_capital
        self.position_size_pct = position_size_pct
        self.leverage = leverage
        
        self.use_stop_loss = use_stop_loss
        self.stop_loss_pct = stop_loss_pct
        self.use_take_profit = use_take_profit
        self.take_profit_pct = take_profit_pct
        self.use_trailing_stop = use_trailing_stop
        self.trailing_stop_pct = trailing_stop_pct
        self.min_profit_for_trailing = min_profit_for_trailing
        
        self.use_volume_filter = use_volume_filter
        self.use_mtf_confirmation = use_mtf_confirmation and (data_4h is not None)
        self.use_atr_sizing = use_atr_sizing
        
        # Calcular ATR
        if use_atr_sizing:
            self.atr = calculate_atr(data_1h, period=14)
            self.atr_ma = self.atr.rolling(window=50).mean()
        
        self.position = None
        self.entry_price = 0
        self.entry_date = None
        self.peak_price = 0
        self.capital = initial_capital
        self.trades = []
        self.equity_curve = []
        
        # Pre-calcular swings
        print("🔍 Calculando swing points 1h...")
        self.detector_1h = SwingDetectorV2(data_1h, volume_filter=use_volume_filter)
        self.detector_1h.detect_all_swings()
        
        if self.use_mtf_confirmation and data_4h is not None:
            print("🔍 Calculando swing points 4h...")
            self.detector_4h = SwingDetectorV2(data_4h, volume_filter=use_volume_filter)
            self.detector_4h.detect_all_swings()
        else:
            self.detector_4h = None
        
        highs = self.detector_1h.intermediate_highs.notna().sum()
        lows = self.detector_1h.intermediate_lows.notna().sum()
        print(f"   ✓ 1h: {highs} highs, {lows} lows")
        
        if self.detector_4h:
            highs_4h = self.detector_4h.intermediate_highs.notna().sum()
            lows_4h = self.detector_4h.intermediate_lows.notna().sum()
            print(f"   ✓ 4h: {highs_4h} highs, {lows_4h} lows")
    
    def _get_position_size(self, current_price: float, current_index: int) -> float:
        base_size = self.capital * self.position_size_pct
        
        if not self.use_atr_sizing:
            return base_size
        
        if pd.isna(self.atr.iloc[current_index]) or pd.isna(self.atr_ma.iloc[current_index]):
            return base_size
        
        current_atr = self.atr.iloc[current_index]
        avg_atr = self.atr_ma.iloc[current_index]
        
        if avg_atr == 0:
            return base_size
        
        volatility_ratio = current_atr / avg_atr
        adjustment = max(0.5, min(1.5, 2 - volatility_ratio))
        
        return base_size * adjustment
    
    def _check_mtf_confirmation(self, signal_1h: str, date_1h) -> bool:
        if not self.use_mtf_confirmation or self.detector_4h is None:
            return True
        
        try:
            signal_4h, _ = self.detector_4h.get_signal_at_date(date_1h)
            return signal_4h == signal_1h
        except:
            return True
    
    def _check_stop_loss(self, current_price: float) -> Tuple[bool, str]:
        if not self.use_stop_loss or not self.position:
            return False, ""
        
        if self.position == 'LONG':
            pnl_pct = ((current_price - self.entry_price) / self.entry_price) * 100 * self.leverage
        else:
            pnl_pct = ((self.entry_price - current_price) / self.entry_price) * 100 * self.leverage
        
        if pnl_pct <= -self.stop_loss_pct:
            return True, f"Stop Loss: {pnl_pct:.2f}%"
        
        return False, ""
    
    def _check_take_profit(self, current_price: float) -> Tuple[bool, str]:
        if not self.use_take_profit or not self.position:
            return False, ""
        
        if self.position == 'LONG':
            pnl_pct = ((current_price - self.entry_price) / self.entry_price) * 100 * self.leverage
        else:
            pnl_pct = ((self.entry_price - current_price) / self.entry_price) * 100 * self.leverage
        
        if pnl_pct >= self.take_profit_pct:
            return True, f"Take Profit: {pnl_pct:.2f}%"
        
        return False, ""
    
    def _check_trailing_stop(self, current_price: float) -> Tuple[bool, str]:
        if not self.use_trailing_stop or not self.position:
            return False, ""
        
        if self.position == 'LONG':
            current_pnl = ((current_price - self.entry_price) / self.entry_price) * 100 * self.leverage
            
            if current_price > self.peak_price:
                self.peak_price = current_price
            
            if current_pnl >= self.min_profit_for_trailing:
                peak_pnl = ((self.peak_price - self.entry_price) / self.entry_price) * 100 * self.leverage
                drawdown = peak_pnl - current_pnl
                
                if drawdown >= self.trailing_stop_pct:
                    return True, f"Trailing Stop: {current_pnl:.2f}%"
        
        else:
            current_pnl = ((self.entry_price - current_price) / self.entry_price) * 100 * self.leverage
            
            if current_price < self.peak_price or self.peak_price == 0:
                self.peak_price = current_price
            
            if current_pnl >= self.min_profit_for_trailing:
                peak_pnl = ((self.entry_price - self.peak_price) / self.entry_price) * 100 * self.leverage
                drawdown = peak_pnl - current_pnl
                
                if drawdown >= self.trailing_stop_pct:
                    return True, f"Trailing Stop: {current_pnl:.2f}%"
        
        return False, ""
    
    def _close_position(self, current_price: float, current_date, reason: str):
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
            'Capital': self.capital,
            'Exit_Reason': reason
        })
        
        self.position = None
        self.entry_price = 0
        self.peak_price = 0
    
    def run(self):
        print(f"\n{'='*70}")
        print(f"BACKTESTING V2 - INTERMEDIATE SWINGS")
        print(f"{'='*70}")
        print(f"Capital inicial: ${self.initial_capital:.2f}")
        print(f"Tamaño posición: {self.position_size_pct*100}%")
        print(f"Leverage: {self.leverage}x")
        print(f"Stop Loss: {self.stop_loss_pct}%" if self.use_stop_loss else "Stop Loss: Off")
        print(f"Take Profit: {self.take_profit_pct}%" if self.use_take_profit else "Take Profit: Off")
        print(f"Trailing Stop: {self.trailing_stop_pct}%" if self.use_trailing_stop else "Trailing: Off")
        print(f"Volume Filter: {'On' if self.use_volume_filter else 'Off'}")
        print(f"MTF Confirm: {'On (1h+4h)' if self.use_mtf_confirmation else 'Off'}")
        print(f"ATR Sizing: {'On' if self.use_atr_sizing else 'Off'}")
        print(f"Período: {self.data_1h.index[0]} - {self.data_1h.index[-1]}")
        print(f"Total velas: {len(self.data_1h)}")
        print(f"\n⏳ Ejecutando backtest...")
        
        for i in range(30, len(self.data_1h)):
            current_date = self.data_1h.index[i]
            current_price = self.data_1h['Close'].iloc[i]
            
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
            
            # Verificar stops
            if self.position:
                should_close, reason = self._check_stop_loss(current_price)
                if should_close:
                    self._close_position(current_price, current_date, reason)
                    continue
                
                should_close, reason = self._check_take_profit(current_price)
                if should_close:
                    self._close_position(current_price, current_date, reason)
                    continue
                
                should_close, reason = self._check_trailing_stop(current_price)
                if should_close:
                    self._close_position(current_price, current_date, reason)
                    continue
            
            # Señal
            signal, _ = self.detector_1h.get_signal_at_date(current_date)
            
            if signal is None:
                continue
            
            if not self._check_mtf_confirmation(signal, current_date):
                continue
            
            # Trading
            if self.position is None:
                self.position = 'LONG' if signal == 'BUY' else 'SHORT'
                self.entry_price = current_price
                self.entry_date = current_date
                self.peak_price = current_price
                
            elif (self.position == 'LONG' and signal == 'SELL') or \
                 (self.position == 'SHORT' and signal == 'BUY'):
                
                self._close_position(current_price, current_date, "Cambio estructura")
                
                self.position = 'LONG' if signal == 'BUY' else 'SHORT'
                self.entry_price = current_price
                self.entry_date = current_date
                self.peak_price = current_price
            
            if i % 2000 == 0:
                print(f"   {(i/len(self.data_1h)*100):.1f}% completado...")
        
        # Cerrar final
        if self.position:
            final_price = self.data_1h['Close'].iloc[-1]
            self._close_position(final_price, self.data_1h.index[-1], "Fin backtest")
        
        print("   ✓ Backtest completado")
        return self.calculate_metrics()
    
    def calculate_metrics(self):
        if len(self.trades) == 0:
            return {'Total_Trades': 0, 'Trades_DF': pd.DataFrame(), 'Equity_DF': pd.DataFrame()}
        
        trades_df = pd.DataFrame(self.trades)
        equity_df = pd.DataFrame(self.equity_curve)
        
        winning = trades_df[trades_df['PnL_Dollars'] > 0]
        losing = trades_df[trades_df['PnL_Dollars'] < 0]
        
        total_return = self.capital - self.initial_capital
        total_return_pct = (total_return / self.initial_capital) * 100
        
        equity_df['Peak'] = equity_df['Equity'].cummax()
        equity_df['Drawdown'] = (equity_df['Equity'] - equity_df['Peak']) / equity_df['Peak']
        max_dd = equity_df['Drawdown'].min() * 100
        
        returns = trades_df['PnL_Pct'].values
        sharpe = (returns.mean() / returns.std()) * np.sqrt(252/24) if len(returns) > 1 and returns.std() > 0 else 0
        
        gross_profit = winning['PnL_Dollars'].sum() if len(winning) > 0 else 0
        gross_loss = abs(losing['PnL_Dollars'].sum()) if len(losing) > 0 else 0.001
        
        return {
            'Total_Trades': len(trades_df),
            'Winning_Trades': len(winning),
            'Losing_Trades': len(losing),
            'Win_Rate': (len(winning) / len(trades_df) * 100) if len(trades_df) > 0 else 0,
            'Total_Return': total_return,
            'Total_Return_Pct': total_return_pct,
            'Max_Drawdown': max_dd,
            'Sharpe_Ratio': sharpe,
            'Profit_Factor': gross_profit / gross_loss,
            'Avg_Win': winning['PnL_Dollars'].mean() if len(winning) > 0 else 0,
            'Avg_Loss': losing['PnL_Dollars'].mean() if len(losing) > 0 else 0,
            'Trades_DF': trades_df,
            'Equity_DF': equity_df
        }


# ═══════════════════════════════════════════════════════════════════════════
#                        MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("\n" + "="*70)
    print("KRAKEN SWING BOT V2 - BACKTESTING AVANZADO")
    print("="*70)
    
    print("\n📊 Descargando datos de ADA-USD...")
    ticker = yf.Ticker("ADA-USD")
    
    print("  - Timeframe 1h (2 años)...")
    data_1h = ticker.history(period="2y", interval="1h")
    
    print("  - Timeframe 4h (2 años)...")
    data_4h = ticker.history(period="2y", interval="4h")
    
    if data_1h.empty or data_4h.empty:
        print("❌ Error descargando datos")
        return
    
    print(f"✓ {len(data_1h)} velas 1h, {len(data_4h)} velas 4h")
    
    bt = SwingBacktesterV2(
        data_1h=data_1h,
        data_4h=data_4h,
        initial_capital=40.0,
        position_size_pct=0.30,
        leverage=3,
        use_stop_loss=True,
        stop_loss_pct=4.0,
        use_take_profit=True,
        take_profit_pct=8.0,
        use_trailing_stop=True,
        trailing_stop_pct=2.5,
        min_profit_for_trailing=3.0,
        use_volume_filter=True,
        use_mtf_confirmation=True,
        use_atr_sizing=True
    )
    
    metrics = bt.run()
    
    print(f"\n{'='*70}")
    print("RESULTADOS V2")
    print(f"{'='*70}")
    print(f"Total trades:       {metrics['Total_Trades']}")
    print(f"Trades ganadores:   {metrics['Winning_Trades']}")
    print(f"Trades perdedores:  {metrics['Losing_Trades']}")
    print(f"Win rate:           {metrics['Win_Rate']:.2f}%")
    print(f"Retorno total:      ${metrics['Total_Return']:.2f} ({metrics['Total_Return_Pct']:.2f}%)")
    print(f"Capital final:      ${metrics['Total_Return'] + 40:.2f}")
    print(f"Drawdown máximo:    {metrics['Max_Drawdown']:.2f}%")
    print(f"Sharpe Ratio:       {metrics['Sharpe_Ratio']:.2f}")
    print(f"Profit Factor:      {metrics['Profit_Factor']:.2f}")
    print(f"Ganancia promedio:  ${metrics['Avg_Win']:.2f}")
    print(f"Pérdida promedio:   ${metrics['Avg_Loss']:.2f}")
    print(f"{'='*70}\n")
    
    if len(metrics['Trades_DF']) > 0:
        print("\nSalidas por razón:")
        for reason, count in metrics['Trades_DF']['Exit_Reason'].value_counts().items():
            print(f"  {reason}: {count}")
        
        print("\nÚltimos 10 trades:")
        print(metrics['Trades_DF'].tail(10)[['Exit_Date', 'Type', 'Exit_Price', 'PnL_Pct', 'Exit_Reason']].to_string(index=False))
    
    plot_results(metrics)


def plot_results(metrics):
    if len(metrics['Trades_DF']) == 0:
        print("\n⚠️  Sin trades")
        return
    
    trades_df = metrics['Trades_DF']
    equity_df = metrics['Equity_DF']
    
    fig, axes = plt.subplots(3, 2, figsize=(16, 12))
    
    # Equity
    axes[0,0].plot(equity_df['Date'], equity_df['Equity'], 'b-', linewidth=2)
    axes[0,0].axhline(y=40, color='r', linestyle='--', alpha=0.5)
    axes[0,0].fill_between(equity_df['Date'], equity_df['Equity'], alpha=0.3)
    axes[0,0].set_title('Capital', fontweight='bold')
    axes[0,0].set_ylabel('$')
    axes[0,0].grid(alpha=0.3)
    
    # Drawdown
    axes[0,1].fill_between(equity_df['Date'], equity_df['Drawdown']*100, 0, color='r', alpha=0.5)
    axes[0,1].set_title('Drawdown', fontweight='bold')
    axes[0,1].set_ylabel('%')
    axes[0,1].grid(alpha=0.3)
    
    # P&L dist
    wins = trades_df[trades_df['PnL_Dollars'] > 0]['PnL_Dollars']
    losses = trades_df[trades_df['PnL_Dollars'] <= 0]['PnL_Dollars']
    axes[1,0].hist([wins, losses], bins=20, label=['Wins', 'Losses'], color=['g', 'r'], alpha=0.7)
    axes[1,0].set_title('P&L Distribution', fontweight='bold')
    axes[1,0].legend()
    axes[1,0].grid(alpha=0.3)
    
    # Exit reasons
    exit_counts = trades_df['Exit_Reason'].value_counts()
    axes[1,1].bar(range(len(exit_counts)), exit_counts.values, color='steelblue')
    axes[1,1].set_xticks(range(len(exit_counts)))
    axes[1,1].set_xticklabels(exit_counts.index, rotation=45, ha='right')
    axes[1,1].set_title('Exit Reasons', fontweight='bold')
    axes[1,1].grid(alpha=0.3, axis='y')
    
    # Cumulative
    trades_df['Cumulative'] = trades_df['PnL_Dollars'].cumsum()
    axes[2,0].plot(trades_df['Cumulative'], 'g-', linewidth=2)
    axes[2,0].set_title('Cumulative Return', fontweight='bold')
    axes[2,0].set_ylabel('$')
    axes[2,0].grid(alpha=0.3)
    
    # Trade bars
    colors = ['g' if x > 0 else 'r' for x in trades_df['PnL_Dollars']]
    axes[2,1].bar(range(len(trades_df)), trades_df['PnL_Dollars'], color=colors, alpha=0.7)
    axes[2,1].axhline(y=0, color='k', linestyle='-', linewidth=0.5)
    axes[2,1].set_title('P&L per Trade', fontweight='bold')
    axes[2,1].grid(alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig('backtest_v2.png', dpi=150, bbox_inches='tight')
    print(f"\n✓ Gráficos: backtest_v2.png")
    plt.show()


if __name__ == "__main__":
    main()