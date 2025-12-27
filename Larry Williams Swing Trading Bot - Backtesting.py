#pip install yfinance==1.0 pandas numpy matplotlib plotly

"""
Larry Williams Market Structure Backtesting Bot
Implementación de la estrategia de swing points para backtesting en múltiples criptos
"""

# ==================== INSTALACIÓN DE DEPENDENCIAS ====================
#!pip install yfinance==0.1.70 pandas numpy matplotlib plotly --quiet

# ==================== IMPORTS ====================
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

print("✓ Librerías cargadas correctamente")

# ==================== CLASE PARA DETECTAR SWING POINTS ====================
class SwingDetector:
    """
    Detecta swing points (puntos de giro) según la metodología de Larry Williams
    """
    
    def __init__(self, data):
        """
        Inicializa el detector con datos OHLC
        
        Args:
            data: DataFrame con columnas ['Open', 'High', 'Low', 'Close']
        """
        self.data = data.copy()
        self.short_term_highs = pd.Series(index=data.index, dtype=float)
        self.short_term_lows = pd.Series(index=data.index, dtype=float)
        self.intermediate_highs = pd.Series(index=data.index, dtype=float)
        self.intermediate_lows = pd.Series(index=data.index, dtype=float)
        self.long_term_highs = pd.Series(index=data.index, dtype=float)
        self.long_term_lows = pd.Series(index=data.index, dtype=float)
    
    def detect_short_term_swings(self):
        """
        Detecta swing highs y lows de corto plazo
        Un short-term low ocurre cuando: low[i] < low[i-1] AND low[i] < low[i+1]
        Un short-term high ocurre cuando: high[i] > high[i-1] AND high[i] > high[i+1]
        """
        highs = self.data['High'].values
        lows = self.data['Low'].values
        
        # Detectar short-term lows (mínimos locales)
        for i in range(1, len(lows) - 1):
            if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                self.short_term_lows.iloc[i] = lows[i]
        
        # Detectar short-term highs (máximos locales)
        for i in range(1, len(highs) - 1):
            if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                self.short_term_highs.iloc[i] = highs[i]
        
        return self.short_term_highs, self.short_term_lows
    
    def detect_intermediate_swings(self):
        """
        Detecta swing points intermedios a partir de los swing points de corto plazo
        Un intermediate high es un short-term high mayor que sus vecinos short-term highs
        """
        # Primero detectar short-term swings si no se han detectado
        if self.short_term_highs.isna().all():
            self.detect_short_term_swings()
        
        # Obtener índices donde hay short-term highs
        st_high_indices = self.short_term_highs.dropna().index.tolist()
        
        # Detectar intermediate highs
        for i in range(1, len(st_high_indices) - 1):
            prev_idx = st_high_indices[i-1]
            curr_idx = st_high_indices[i]
            next_idx = st_high_indices[i+1]
            
            curr_val = self.short_term_highs[curr_idx]
            prev_val = self.short_term_highs[prev_idx]
            next_val = self.short_term_highs[next_idx]
            
            # Si el high actual es mayor que sus vecinos, es intermediate
            if curr_val > prev_val and curr_val > next_val:
                self.intermediate_highs[curr_idx] = curr_val
        
        # Obtener índices donde hay short-term lows
        st_low_indices = self.short_term_lows.dropna().index.tolist()
        
        # Detectar intermediate lows
        for i in range(1, len(st_low_indices) - 1):
            prev_idx = st_low_indices[i-1]
            curr_idx = st_low_indices[i]
            next_idx = st_low_indices[i+1]
            
            curr_val = self.short_term_lows[curr_idx]
            prev_val = self.short_term_lows[prev_idx]
            next_val = self.short_term_lows[next_idx]
            
            # Si el low actual es menor que sus vecinos, es intermediate
            if curr_val < prev_val and curr_val < next_val:
                self.intermediate_lows[curr_idx] = curr_val
        
        return self.intermediate_highs, self.intermediate_lows
    
    def detect_long_term_swings(self):
        """
        Detecta swing points de largo plazo a partir de los intermediate swings
        """
        # Primero detectar intermediate swings si no se han detectado
        if self.intermediate_highs.isna().all():
            self.detect_intermediate_swings()
        
        # Obtener índices donde hay intermediate highs
        int_high_indices = self.intermediate_highs.dropna().index.tolist()
        
        # Detectar long-term highs
        for i in range(1, len(int_high_indices) - 1):
            prev_idx = int_high_indices[i-1]
            curr_idx = int_high_indices[i]
            next_idx = int_high_indices[i+1]
            
            curr_val = self.intermediate_highs[curr_idx]
            prev_val = self.intermediate_highs[prev_idx]
            next_val = self.intermediate_highs[next_idx]
            
            if curr_val > prev_val and curr_val > next_val:
                self.long_term_highs[curr_idx] = curr_val
        
        # Obtener índices donde hay intermediate lows
        int_low_indices = self.intermediate_lows.dropna().index.tolist()
        
        # Detectar long-term lows
        for i in range(1, len(int_low_indices) - 1):
            prev_idx = int_low_indices[i-1]
            curr_idx = int_low_indices[i]
            next_idx = int_low_indices[i+1]
            
            curr_val = self.intermediate_lows[curr_idx]
            prev_val = self.intermediate_lows[prev_idx]
            next_val = self.intermediate_lows[next_idx]
            
            if curr_val < prev_val and curr_val < next_val:
                self.long_term_lows[curr_idx] = curr_val
        
        return self.long_term_highs, self.long_term_lows
    
    def get_all_swings(self):
        """
        Detecta todos los niveles de swing points y los retorna en un DataFrame
        """
        self.detect_short_term_swings()
        self.detect_intermediate_swings()
        self.detect_long_term_swings()
        
        result = self.data.copy()
        result['ST_High'] = self.short_term_highs
        result['ST_Low'] = self.short_term_lows
        result['INT_High'] = self.intermediate_highs
        result['INT_Low'] = self.intermediate_lows
        result['LT_High'] = self.long_term_highs
        result['LT_Low'] = self.long_term_lows
        
        return result


# ==================== CLASE PARA BACKTESTING ====================
class SwingBacktester:
    """
    Sistema de backtesting para estrategias basadas en swing structure
    """
    
    def __init__(self, data_with_swings, initial_capital=10000, 
                 use_intermediate=True, use_long_term=False):
        """
        Args:
            data_with_swings: DataFrame con datos OHLC y swing points
            initial_capital: Capital inicial para el backtesting
            use_intermediate: Si True, usa intermediate swings para señales
            use_long_term: Si True, usa long-term swings para señales
        """
        self.data = data_with_swings.copy()
        self.initial_capital = initial_capital
        self.use_intermediate = use_intermediate
        self.use_long_term = use_long_term
        
        # Variables de estado
        self.position = 0  # 1 = long, -1 = short, 0 = sin posición
        self.entry_price = 0
        self.capital = initial_capital
        self.trades = []
        self.equity_curve = []
    
    def generate_signals(self):
        """
        Genera señales de trading basadas en swing points
        Long signal: cuando se forma un swing low (comprar en soporte)
        Short signal: cuando se forma un swing high (vender en resistencia)
        """
        signals = pd.DataFrame(index=self.data.index)
        signals['Signal'] = 0  # 0 = no signal, 1 = long, -1 = short
        
        # Determinar qué nivel de swings usar
        if self.use_long_term:
            high_col = 'LT_High'
            low_col = 'LT_Low'
        elif self.use_intermediate:
            high_col = 'INT_High'
            low_col = 'INT_Low'
        else:
            high_col = 'ST_High'
            low_col = 'ST_Low'
        
        # Generar señales: Long en swing lows, Short en swing highs
        signals.loc[self.data[low_col].notna(), 'Signal'] = 1   # Long signal
        signals.loc[self.data[high_col].notna(), 'Signal'] = -1  # Short signal
        
        return signals
    
    def run_backtest(self):
        """
        Ejecuta el backtesting completo
        """
        signals = self.generate_signals()
        
        for i in range(len(self.data)):
            current_price = self.data['Close'].iloc[i]
            signal = signals['Signal'].iloc[i]
            
            # Registrar equity actual
            if self.position != 0:
                unrealized_pnl = (current_price - self.entry_price) * self.position
                current_equity = self.capital + unrealized_pnl
            else:
                current_equity = self.capital
            
            self.equity_curve.append({
                'Date': self.data.index[i],
                'Equity': current_equity,
                'Position': self.position
            })
            
            # Gestión de posiciones
            if signal == 1 and self.position <= 0:  # Señal LONG
                # Cerrar short si existe
                if self.position == -1:
                    pnl = (self.entry_price - current_price)
                    self.capital += pnl
                    self.trades.append({
                        'Entry_Date': self.entry_date,
                        'Exit_Date': self.data.index[i],
                        'Type': 'SHORT',
                        'Entry_Price': self.entry_price,
                        'Exit_Price': current_price,
                        'PnL': pnl,
                        'Capital': self.capital
                    })
                
                # Abrir long
                self.position = 1
                self.entry_price = current_price
                self.entry_date = self.data.index[i]
            
            elif signal == -1 and self.position >= 0:  # Señal SHORT
                # Cerrar long si existe
                if self.position == 1:
                    pnl = (current_price - self.entry_price)
                    self.capital += pnl
                    self.trades.append({
                        'Entry_Date': self.entry_date,
                        'Exit_Date': self.data.index[i],
                        'Type': 'LONG',
                        'Entry_Price': self.entry_price,
                        'Exit_Price': current_price,
                        'PnL': pnl,
                        'Capital': self.capital
                    })
                
                # Abrir short
                self.position = -1
                self.entry_price = current_price
                self.entry_date = self.data.index[i]
        
        # Cerrar posición final si existe
        if self.position != 0:
            final_price = self.data['Close'].iloc[-1]
            if self.position == 1:
                pnl = (final_price - self.entry_price)
            else:
                pnl = (self.entry_price - final_price)
            
            self.capital += pnl
            self.trades.append({
                'Entry_Date': self.entry_date,
                'Exit_Date': self.data.index[-1],
                'Type': 'LONG' if self.position == 1 else 'SHORT',
                'Entry_Price': self.entry_price,
                'Exit_Price': final_price,
                'PnL': pnl,
                'Capital': self.capital
            })
        
        return self.calculate_metrics()
    
    def calculate_metrics(self):
        """
        Calcula métricas de rendimiento del backtest
        """
        if len(self.trades) == 0:
            return {
                'Total_Trades': 0,
                'Winning_Trades': 0,
                'Losing_Trades': 0,
                'Win_Rate': 0,
                'Total_Return': 0,
                'Total_Return_Pct': 0,
                'Max_Drawdown': 0,
                'Profit_Factor': 0,
                'Average_Win': 0,
                'Average_Loss': 0
            }
        
        trades_df = pd.DataFrame(self.trades)
        equity_df = pd.DataFrame(self.equity_curve)
        
        winning_trades = trades_df[trades_df['PnL'] > 0]
        losing_trades = trades_df[trades_df['PnL'] < 0]
        
        total_return = self.capital - self.initial_capital
        total_return_pct = (total_return / self.initial_capital) * 100
        
        # Calcular drawdown
        equity_df['Peak'] = equity_df['Equity'].cummax()
        equity_df['Drawdown'] = (equity_df['Equity'] - equity_df['Peak']) / equity_df['Peak']
        max_drawdown = equity_df['Drawdown'].min() * 100
        
        # Profit factor
        gross_profit = winning_trades['PnL'].sum() if len(winning_trades) > 0 else 0
        gross_loss = abs(losing_trades['PnL'].sum()) if len(losing_trades) > 0 else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        metrics = {
            'Total_Trades': len(trades_df),
            'Winning_Trades': len(winning_trades),
            'Losing_Trades': len(losing_trades),
            'Win_Rate': (len(winning_trades) / len(trades_df) * 100) if len(trades_df) > 0 else 0,
            'Total_Return': total_return,
            'Total_Return_Pct': total_return_pct,
            'Max_Drawdown': max_drawdown,
            'Profit_Factor': profit_factor,
            'Average_Win': winning_trades['PnL'].mean() if len(winning_trades) > 0 else 0,
            'Average_Loss': losing_trades['PnL'].mean() if len(losing_trades) > 0 else 0,
            'Trades_DF': trades_df,
            'Equity_DF': equity_df
        }
        
        return metrics


# ==================== FUNCIÓN PRINCIPAL DE DESCARGA Y ANÁLISIS ====================
def download_and_analyze(symbol, period='2y', interval='1h'):
    """
    Descarga datos y ejecuta análisis de swing structure
    
    Args:
        symbol: Símbolo del activo (ej: 'BTC-USD')
        period: Período de datos ('1y', '2y', 'max')
        interval: Intervalo temporal ('1h', '1d', etc)
    """
    print(f"\n{'='*60}")
    print(f"Analizando {symbol}")
    print(f"{'='*60}")
    
    try:
        # Descargar datos
        print(f"Descargando datos {interval} de {symbol} (período: {period})...")
        ticker = yf.Ticker(symbol)
        data = ticker.history(period=period, interval=interval)
        
        if data.empty:
            print(f"❌ No se pudieron descargar datos para {symbol}")
            return None
        
        print(f"✓ Datos descargados: {len(data)} velas")
        
        # Detectar swing points
        print("Detectando swing points...")
        detector = SwingDetector(data)
        data_with_swings = detector.get_all_swings()
        
        # Contar swing points detectados
        st_highs = data_with_swings['ST_High'].notna().sum()
        st_lows = data_with_swings['ST_Low'].notna().sum()
        int_highs = data_with_swings['INT_High'].notna().sum()
        int_lows = data_with_swings['INT_Low'].notna().sum()
        lt_highs = data_with_swings['LT_High'].notna().sum()
        lt_lows = data_with_swings['LT_Low'].notna().sum()
        
        print(f"✓ Short-term: {st_highs} highs, {st_lows} lows")
        print(f"✓ Intermediate: {int_highs} highs, {int_lows} lows")
        print(f"✓ Long-term: {lt_highs} highs, {lt_lows} lows")
        
        # Ejecutar backtesting con intermediate swings
        print("\nEjecutando backtesting (Intermediate Swings)...")
        bt_int = SwingBacktester(data_with_swings, use_intermediate=True, use_long_term=False)
        metrics_int = bt_int.run_backtest()
        
        print("\n--- RESULTADOS (Intermediate Swings) ---")
        print(f"Total de operaciones: {metrics_int['Total_Trades']}")
        print(f"Operaciones ganadoras: {metrics_int['Winning_Trades']}")
        print(f"Operaciones perdedoras: {metrics_int['Losing_Trades']}")
        print(f"Tasa de acierto: {metrics_int['Win_Rate']:.2f}%")
        print(f"Retorno total: ${metrics_int['Total_Return']:.2f} ({metrics_int['Total_Return_Pct']:.2f}%)")
        print(f"Drawdown máximo: {metrics_int['Max_Drawdown']:.2f}%")
        print(f"Profit Factor: {metrics_int['Profit_Factor']:.2f}")
        
        # Ejecutar backtesting con long-term swings
        print("\nEjecutando backtesting (Long-term Swings)...")
        bt_lt = SwingBacktester(data_with_swings, use_intermediate=False, use_long_term=True)
        metrics_lt = bt_lt.run_backtest()
        
        print("\n--- RESULTADOS (Long-term Swings) ---")
        print(f"Total de operaciones: {metrics_lt['Total_Trades']}")
        print(f"Operaciones ganadoras: {metrics_lt['Winning_Trades']}")
        print(f"Operaciones perdedoras: {metrics_lt['Losing_Trades']}")
        print(f"Tasa de acierto: {metrics_lt['Win_Rate']:.2f}%")
        print(f"Retorno total: ${metrics_lt['Total_Return']:.2f} ({metrics_lt['Total_Return_Pct']:.2f}%)")
        print(f"Drawdown máximo: {metrics_lt['Max_Drawdown']:.2f}%")
        print(f"Profit Factor: {metrics_lt['Profit_Factor']:.2f}")
        
        return {
            'symbol': symbol,
            'data': data_with_swings,
            'metrics_intermediate': metrics_int,
            'metrics_longterm': metrics_lt,
            'backtester_int': bt_int,
            'backtester_lt': bt_lt
        }
        
    except Exception as e:
        print(f"❌ Error procesando {symbol}: {str(e)}")
        return None


# ==================== FUNCIÓN DE VISUALIZACIÓN ====================
def plot_results(results, show_swings='intermediate'):
    """
    Visualiza resultados del backtesting con plotly
    
    Args:
        results: Diccionario de resultados de download_and_analyze
        show_swings: 'short', 'intermediate', o 'longterm'
    """
    data = results['data']
    symbol = results['symbol']
    
    if show_swings == 'longterm':
        metrics = results['metrics_longterm']
        equity_df = results['backtester_lt'].equity_curve
        high_col, low_col = 'LT_High', 'LT_Low'
        title_suffix = 'Long-term Swings'
    else:
        metrics = results['metrics_intermediate']
        equity_df = results['backtester_int'].equity_curve
        high_col, low_col = 'INT_High', 'INT_Low'
        title_suffix = 'Intermediate Swings'
    
    # Crear subplots
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        subplot_titles=(f'{symbol} - Precio y Swing Points ({title_suffix})', 
                       'Curva de Capital'),
        row_heights=[0.7, 0.3]
    )
    
    # Gráfico de velas
    fig.add_trace(
        go.Candlestick(
            x=data.index,
            open=data['Open'],
            high=data['High'],
            low=data['Low'],
            close=data['Close'],
            name='Precio'
        ),
        row=1, col=1
    )
    
    # Swing highs
    swing_highs = data[data[high_col].notna()]
    fig.add_trace(
        go.Scatter(
            x=swing_highs.index,
            y=swing_highs[high_col],
            mode='markers',
            marker=dict(size=12, color='red', symbol='triangle-down'),
            name='Swing Highs'
        ),
        row=1, col=1
    )
    
    # Swing lows
    swing_lows = data[data[low_col].notna()]
    fig.add_trace(
        go.Scatter(
            x=swing_lows.index,
            y=swing_lows[low_col],
            mode='markers',
            marker=dict(size=12, color='green', symbol='triangle-up'),
            name='Swing Lows'
        ),
        row=1, col=1
    )
    
    # Curva de capital
    equity_df_plot = pd.DataFrame(equity_df)
    fig.add_trace(
        go.Scatter(
            x=equity_df_plot['Date'],
            y=equity_df_plot['Equity'],
            mode='lines',
            name='Capital',
            line=dict(color='blue', width=2)
        ),
        row=2, col=1
    )
    
    # Actualizar layout
    fig.update_layout(
        title=f'{symbol} - Backtesting Strategy ({title_suffix})',
        xaxis_rangeslider_visible=False,
        height=800,
        showlegend=True
    )
    
    fig.update_yaxes(title_text="Precio", row=1, col=1)
    fig.update_yaxes(title_text="Capital ($)", row=2, col=1)
    
    fig.show()
    
    # Mostrar resumen de métricas
    print(f"\n{'='*60}")
    print(f"RESUMEN DE RESULTADOS - {symbol} ({title_suffix})")
    print(f"{'='*60}")
    print(f"Retorno Total: ${metrics['Total_Return']:.2f} ({metrics['Total_Return_Pct']:.2f}%)")
    print(f"Total Operaciones: {metrics['Total_Trades']}")
    print(f"Tasa de Acierto: {metrics['Win_Rate']:.2f}%")
    print(f"Profit Factor: {metrics['Profit_Factor']:.2f}")
    print(f"Drawdown Máximo: {metrics['Max_Drawdown']:.2f}%")
    print(f"{'='*60}\n")


# ==================== EJECUTAR ANÁLISIS MULTI-CRYPTO ====================
print("\n" + "="*80)
print("LARRY WILLIAMS SWING STRUCTURE BACKTESTING SYSTEM")
print("="*80)

# Lista de criptomonedas para analizar
cryptos = ['BTC-USD', 'ETH-USD', 'BNB-USD', 'SOL-USD', 'ADA-USD']

# Almacenar resultados
all_results = {}

# Analizar cada crypto
for crypto in cryptos:
    result = download_and_analyze(crypto, period='2y', interval='1h')
    if result:
        all_results[crypto] = result

# Mostrar tabla comparativa
print("\n" + "="*80)
print("COMPARACIÓN DE RESULTADOS (Intermediate Swings)")
print("="*80)
print(f"{'Símbolo':<12} {'Retorno %':<12} {'Win Rate %':<12} {'Trades':<10} {'Profit Factor':<15}")
print("-"*80)

for symbol, result in all_results.items():
    metrics = result['metrics_intermediate']
    print(f"{symbol:<12} {metrics['Total_Return_Pct']:>10.2f}%  {metrics['Win_Rate']:>10.2f}%  {metrics['Total_Trades']:>8}  {metrics['Profit_Factor']:>13.2f}")

print("="*80)

# Visualizar el mejor resultado
if all_results:
    best_symbol = max(all_results.items(), 
                     key=lambda x: x[1]['metrics_intermediate']['Total_Return_Pct'])
    print(f"\n📊 Mostrando gráficos para el mejor resultado: {best_symbol[0]}")
    plot_results(best_symbol[1], show_swings='intermediate')
