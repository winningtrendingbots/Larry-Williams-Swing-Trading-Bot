"""
KRAKEN TRADING BOT CON SEGUIMIENTO DE POSICIONES
Versión sin estado - Compatible con GitHub Actions
"""

import os
import json
import time
import hmac
import hashlib
import base64
import urllib.parse
from datetime import datetime
import requests
import pandas as pd
from typing import Dict, Optional, Tuple

# ═══════════════════════════════════════════════════════════════════════════
#                          CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════════════════

class BotConfig:
    KRAKEN_API_KEY = os.getenv('KRAKEN_API_KEY', '')
    KRAKEN_API_SECRET = os.getenv('KRAKEN_API_SECRET', '')
    KRAKEN_API_URL = 'https://api.kraken.com'
    
    TRADING_PAIR = os.getenv('TRADING_PAIR', 'ADAUSD')
    FIAT_CURRENCY = os.getenv('FIAT_CURRENCY', 'AUTO')
    
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
    
    POSITION_SIZE_PCT = float(os.getenv('POSITION_SIZE_PCT', '0.10'))
    LEVERAGE = int(os.getenv('LEVERAGE', '3'))
    SWING_LEVEL = os.getenv('SWING_LEVEL', 'intermediate')
    LOOKBACK_CANDLES = int(os.getenv('LOOKBACK_CANDLES', '200'))
    CANDLE_INTERVAL = int(os.getenv('CANDLE_INTERVAL', '60'))
    
    # Stop Loss y Take Profit
    USE_STOP_LOSS = os.getenv('USE_STOP_LOSS', 'True').lower() == 'true'
    STOP_LOSS_PCT = float(os.getenv('STOP_LOSS_PCT', '5.0'))
    
    USE_TAKE_PROFIT = os.getenv('USE_TAKE_PROFIT', 'True').lower() == 'true'
    TAKE_PROFIT_PCT = float(os.getenv('TAKE_PROFIT_PCT', '10.0'))
    
    USE_TRAILING_STOP = os.getenv('USE_TRAILING_STOP', 'True').lower() == 'true'
    TRAILING_STOP_PCT = float(os.getenv('TRAILING_STOP_PCT', '3.0'))
    MIN_PROFIT_FOR_TRAILING = float(os.getenv('MIN_PROFIT_FOR_TRAILING', '2.0'))
    
    MAX_DRAWDOWN_PCT = float(os.getenv('MAX_DRAWDOWN_PCT', '20.0'))
    MIN_BALANCE_USD = float(os.getenv('MIN_BALANCE_USD', '10.0'))
    
    DRY_RUN = os.getenv('DRY_RUN', 'True').lower() == 'true'


# ═══════════════════════════════════════════════════════════════════════════
#                        CLIENTE DE KRAKEN
# ═══════════════════════════════════════════════════════════════════════════

class KrakenClient:
    def __init__(self, api_key: str, api_secret: str, api_url: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_url = api_url
        self.session = requests.Session()
        
    def _get_kraken_signature(self, urlpath: str, data: Dict) -> str:
        postdata = urllib.parse.urlencode(data)
        encoded = (str(data['nonce']) + postdata).encode()
        message = urlpath.encode() + hashlib.sha256(encoded).digest()
        signature = hmac.new(base64.b64decode(self.api_secret), message, hashlib.sha512)
        return base64.b64encode(signature.digest()).decode()
    
    def _request(self, endpoint: str, data: Dict = None, private: bool = False) -> Dict:
        url = self.api_url + endpoint
        
        if private:
            data = data or {}
            data['nonce'] = int(time.time() * 1000)
            headers = {
                'API-Key': self.api_key,
                'API-Sign': self._get_kraken_signature(endpoint, data)
            }
            response = self.session.post(url, data=data, headers=headers, timeout=30)
        else:
            response = self.session.get(url, params=data, timeout=30)
        
        response.raise_for_status()
        result = response.json()
        
        if result.get('error') and len(result['error']) > 0:
            raise Exception(f"Kraken API error: {result['error']}")
        
        return result.get('result', {})
    
    def get_ohlc_data(self, pair: str, interval: int = 60) -> pd.DataFrame:
        result = self._request('/0/public/OHLC', data={'pair': pair, 'interval': interval})
        
        pair_key = None
        for key in result.keys():
            if key != 'last':
                pair_key = key
                break
        
        if not pair_key:
            raise Exception(f"No se encontró el par {pair}")
        
        df = pd.DataFrame(result[pair_key], columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'vwap', 'volume', 'count'
        ])
        
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])
        
        df.set_index('timestamp', inplace=True)
        df = df[['open', 'high', 'low', 'close', 'volume']]
        df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        
        return df
    
    def get_fiat_balance(self) -> Tuple[float, str]:
        result = self._request('/0/private/Balance', private=True)
        balances = {k: float(v) for k, v in result.items()}
        
        fiat_keys = {
            'ZUSD': 'USD', 'USD': 'USD',
            'ZEUR': 'EUR', 'EUR': 'EUR',
            'ZGBP': 'GBP', 'GBP': 'GBP',
        }
        
        for key, currency in fiat_keys.items():
            if key in balances and balances[key] > 0:
                return balances[key], currency
        
        return 0.0, 'USD'
    
    def get_open_positions(self) -> Dict:
        """Obtiene posiciones abiertas. Retorna dict vacío si no hay."""
        try:
            result = self._request('/0/private/OpenPositions', private=True)
            return result
        except Exception as e:
            if "No open positions" in str(e) or "EAPI:Invalid key" in str(e):
                return {}
            raise
    
    def close_position(self, position_id: str) -> Dict:
        """Cierra una posición por su ID."""
        data = {'txid': position_id, 'type': 'market'}
        return self._request('/0/private/ClosePosition', data=data, private=True)
    
    def place_market_order(self, pair: str, order_type: str, volume: float, leverage: int = None) -> Dict:
        data = {
            'pair': pair,
            'type': order_type,
            'ordertype': 'market',
            'volume': str(volume)
        }
        
        if leverage and leverage > 1:
            data['leverage'] = str(leverage)
        
        return self._request('/0/private/AddOrder', data=data, private=True)


# ═══════════════════════════════════════════════════════════════════════════
#                        TELEGRAM
# ═══════════════════════════════════════════════════════════════════════════

class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}"
    
    def send_message(self, message: str, parse_mode: str = 'HTML') -> bool:
        if not self.bot_token or not self.chat_id:
            print(f"📝 Telegram: {message}")
            return False
        
        try:
            if len(message) > 4000:
                message = message[:3900] + "\n\n... (truncado)"
            
            data = {'chat_id': self.chat_id, 'text': message, 'parse_mode': parse_mode}
            response = requests.post(f"{self.api_url}/sendMessage", data=data, timeout=10)
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"❌ Error Telegram: {e}")
            return False


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
        self.long_term_highs = pd.Series(index=data.index, dtype=float)
        self.long_term_lows = pd.Series(index=data.index, dtype=float)
    
    def detect_short_term_swings(self):
        highs = self.data['High'].values
        lows = self.data['Low'].values
        
        for i in range(1, len(lows) - 1):
            if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                self.short_term_lows.iloc[i] = lows[i]
        
        for i in range(1, len(highs) - 1):
            if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                self.short_term_highs.iloc[i] = highs[i]
        
        return self.short_term_highs, self.short_term_lows
    
    def detect_intermediate_swings(self):
        if self.short_term_highs.isna().all():
            self.detect_short_term_swings()
        
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
    
    def detect_long_term_swings(self):
        if self.intermediate_highs.isna().all():
            self.detect_intermediate_swings()
        
        int_high_indices = self.intermediate_highs.dropna().index.tolist()
        for i in range(1, len(int_high_indices) - 1):
            prev_idx = int_high_indices[i-1]
            curr_idx = int_high_indices[i]
            next_idx = int_high_indices[i+1]
            
            curr_val = self.intermediate_highs[curr_idx]
            prev_val = self.intermediate_highs[prev_idx]
            next_val = self.intermediate_highs[next_idx]
            
            if curr_val > prev_val and curr_val > next_val:
                self.long_term_highs[curr_idx] = curr_val
        
        int_low_indices = self.intermediate_lows.dropna().index.tolist()
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
    
    def get_latest_signal(self, level: str = 'intermediate') -> Tuple[Optional[str], Optional[float]]:
        self.detect_long_term_swings()
        
        if level == 'longterm':
            highs = self.long_term_highs
            lows = self.long_term_lows
        else:
            highs = self.intermediate_highs
            lows = self.intermediate_lows
        
        last_high_idx = highs.last_valid_index()
        last_low_idx = lows.last_valid_index()
        
        if last_high_idx is None and last_low_idx is None:
            return None, None
        
        if last_low_idx is None:
            return 'SELL', highs[last_high_idx]
        elif last_high_idx is None:
            return 'BUY', lows[last_low_idx]
        else:
            if last_low_idx > last_high_idx:
                return 'BUY', lows[last_low_idx]
            else:
                return 'SELL', highs[last_high_idx]


# ═══════════════════════════════════════════════════════════════════════════
#                        BOT PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════

class SwingTradingBot:
    def __init__(self, config: BotConfig):
        self.config = config
        self.kraken = KrakenClient(config.KRAKEN_API_KEY, config.KRAKEN_API_SECRET, config.KRAKEN_API_URL)
        self.telegram = TelegramNotifier(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID)
        
    def analyze_position(self, position_data: Dict, current_price: float) -> Tuple[bool, str]:
        """
        Analiza una posición abierta y determina si debe cerrarse.
        
        Returns:
            (should_close, reason)
        """
        # Extraer información de la posición
        pos_type = position_data.get('type', 'long')  # 'long' o 'short'
        entry_price = float(position_data.get('cost', 0)) / float(position_data.get('vol', 1))
        leverage = float(position_data.get('leverage', 1))
        
        # Calcular PnL
        if pos_type == 'long':
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            pnl_pct = ((entry_price - current_price) / entry_price) * 100
        
        pnl_with_leverage = pnl_pct * leverage
        
        print(f"   Posición {pos_type.upper()}: entrada ${entry_price:.4f}, actual ${current_price:.4f}")
        print(f"   PnL: {pnl_with_leverage:+.2f}% (leverage {leverage}x)")
        
        # Stop Loss
        if self.config.USE_STOP_LOSS and pnl_with_leverage <= -self.config.STOP_LOSS_PCT:
            return True, f"🛑 STOP LOSS: {pnl_with_leverage:.2f}%"
        
        # Take Profit
        if self.config.USE_TAKE_PROFIT and pnl_with_leverage >= self.config.TAKE_PROFIT_PCT:
            return True, f"🎯 TAKE PROFIT: {pnl_with_leverage:.2f}%"
        
        # Trailing Stop (simplificado sin peak tracking)
        if self.config.USE_TRAILING_STOP and pnl_with_leverage >= self.config.MIN_PROFIT_FOR_TRAILING:
            # Si ya estamos en ganancia pero el precio retrocede demasiado
            if pnl_with_leverage < (self.config.MIN_PROFIT_FOR_TRAILING / 2):
                return True, f"📉 TRAILING STOP: {pnl_with_leverage:.2f}%"
        
        return False, ""
    
    def close_position(self, position_id: str, reason: str, position_data: Dict, current_price: float):
        """Cierra una posición."""
        print(f"\n🔴 Cerrando posición: {position_id}")
        print(f"   Razón: {reason}")
        
        if not self.config.DRY_RUN:
            try:
                result = self.kraken.close_position(position_id)
                print(f"   ✓ Posición cerrada: {result}")
            except Exception as e:
                print(f"   ❌ Error: {e}")
                self.telegram.send_message(f"❌ Error cerrando posición: {e}")
                return
        else:
            print(f"   🧪 [SIMULACIÓN] Posición cerrada")
        
        # Notificar
        pos_type = position_data.get('type', 'unknown')
        entry_price = float(position_data.get('cost', 0)) / float(position_data.get('vol', 1))
        
        message = f"""
🔴 <b>POSICIÓN CERRADA</b>

<b>Tipo:</b> {pos_type.upper()}
<b>Entrada:</b> ${entry_price:.4f}
<b>Salida:</b> ${current_price:.4f}

<b>Razón:</b> {reason}
<b>Fecha:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        if self.config.DRY_RUN:
            message = "🧪 <b>SIMULACIÓN</b>\n" + message
        
        self.telegram.send_message(message)
    
    def open_position(self, signal: str, current_price: float, reason: str):
        """Abre una nueva posición."""
        try:
            balance_fiat, currency = self.kraken.get_fiat_balance()
            
            if balance_fiat < self.config.MIN_BALANCE_USD:
                print(f"⚠️  Balance insuficiente: {balance_fiat:.2f} {currency}")
                return
            
            # Calcular tamaño
            capital = balance_fiat * self.config.POSITION_SIZE_PCT
            effective_capital = capital * self.config.LEVERAGE
            volume = effective_capital / current_price
            volume = round(volume, 2)
            
            if volume <= 0:
                print("⚠️  Volumen = 0")
                return
            
            print(f"\n🟢 Abriendo posición {signal}")
            print(f"   Capital: {capital:.2f} {currency} (x{self.config.LEVERAGE})")
            print(f"   Volumen: {volume} @ ${current_price:.4f}")
            
            if not self.config.DRY_RUN:
                order_type = 'buy' if signal == 'BUY' else 'sell'
                result = self.kraken.place_market_order(
                    pair=self.config.TRADING_PAIR,
                    order_type=order_type,
                    volume=volume,
                    leverage=self.config.LEVERAGE
                )
                print(f"   ✓ Orden ejecutada: {result}")
            else:
                print(f"   🧪 [SIMULACIÓN]")
            
            # Notificar
            message = f"""
🟢 <b>NUEVA POSICIÓN</b>

<b>Par:</b> {self.config.TRADING_PAIR}
<b>Tipo:</b> {signal}
<b>Precio:</b> ${current_price:.4f}
<b>Cantidad:</b> {volume}
<b>Leverage:</b> {self.config.LEVERAGE}x

<b>Razón:</b> {reason}
<b>Fecha:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            if self.config.DRY_RUN:
                message = "🧪 <b>SIMULACIÓN</b>\n" + message
            
            self.telegram.send_message(message)
            
        except Exception as e:
            print(f"❌ Error abriendo posición: {e}")
            self.telegram.send_message(f"❌ Error: {e}")
    
    def run(self):
        print("\n" + "="*70)
        print("KRAKEN SWING BOT - CICLO DE EJECUCIÓN")
        print("="*70)
        print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Par: {self.config.TRADING_PAIR}")
        print(f"Modo: {'🧪 SIMULACIÓN' if self.config.DRY_RUN else '💰 REAL'}")
        print("="*70)
        
        try:
            # 1. VERIFICAR POSICIONES EXISTENTES
            print("\n📊 Consultando posiciones abiertas...")
            open_positions = self.kraken.get_open_positions()
            
            # Obtener precio actual
            ohlc_data = self.kraken.get_ohlc_data(self.config.TRADING_PAIR, interval=1)
            current_price = float(ohlc_data['Close'].iloc[-1])
            print(f"💰 Precio actual: ${current_price:.4f}")
            
            if open_positions:
                print(f"✓ {len(open_positions)} posición(es) abierta(s)")
                
                # Analizar cada posición
                for pos_id, pos_data in open_positions.items():
                    should_close, reason = self.analyze_position(pos_data, current_price)
                    
                    if should_close:
                        self.close_position(pos_id, reason, pos_data, current_price)
                    else:
                        print(f"   ✓ Posición OK, mantener")
                
                # Si tenemos posiciones, no abrir nuevas
                print("\nℹ️  Hay posiciones abiertas, no se buscan nuevas señales")
                return
            
            print("✓ No hay posiciones abiertas")
            
            # 2. BUSCAR NUEVAS SEÑALES
            print("\n🔍 Descargando datos históricos...")
            ohlc_data = self.kraken.get_ohlc_data(
                self.config.TRADING_PAIR,
                interval=self.config.CANDLE_INTERVAL
            )
            ohlc_data = ohlc_data.tail(self.config.LOOKBACK_CANDLES)
            print(f"✓ {len(ohlc_data)} velas descargadas")
            
            print("\n🔍 Detectando swing points...")
            detector = SwingDetector(ohlc_data)
            signal, signal_price = detector.get_latest_signal(level=self.config.SWING_LEVEL)
            
            if signal is None:
                print("ℹ️  No hay señales detectadas")
                return
            
            print(f"✓ Señal: {signal} @ ${signal_price:.4f}")
            
            # 3. ABRIR NUEVA POSICIÓN
            reason = f"Señal {signal} detectada en nivel {self.config.SWING_LEVEL}"
            self.open_position(signal, current_price, reason)
            
            print("\n✅ Ciclo completado")
            
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            print(f"\n❌ {error_msg}")
            self.telegram.send_message(f"❌ {error_msg}")
            raise


# ═══════════════════════════════════════════════════════════════════════════
#                              MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    config = BotConfig()
    
    if not config.KRAKEN_API_KEY or not config.KRAKEN_API_SECRET:
        print("❌ Falta configurar KRAKEN_API_KEY y KRAKEN_API_SECRET")
        return
    
    bot = SwingTradingBot(config)
    bot.run()


if __name__ == "__main__":
    main()
