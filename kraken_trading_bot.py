"""
═══════════════════════════════════════════════════════════════════════════
    KRAKEN MARGIN TRADING BOT - LARRY WILLIAMS SWING STRATEGY
    VERSION 2.0 - FIXED PAIR NOMENCLATURE
═══════════════════════════════════════════════════════════════════════════

⚠️  ADVERTENCIA IMPORTANTE ⚠️
Este bot realiza operaciones reales con dinero real en Kraken.
- Operar con margen puede resultar en pérdidas superiores a tu inversión inicial
- Siempre comienza con cantidades pequeñas y en modo testnet si está disponible
- Nunca inviertas más de lo que puedas permitirte perder
- El trading automatizado conlleva riesgos significativos
- Los resultados pasados no garantizan rendimientos futuros

Asegúrate de entender completamente cómo funciona el bot antes de usarlo.
═══════════════════════════════════════════════════════════════════════════
"""

import os
import json
import time
import hmac
import hashlib
import base64
import urllib.parse
from datetime import datetime, timedelta
import requests
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple

# ═══════════════════════════════════════════════════════════════════════════
#                          CONFIGURACIÓN DEL BOT
# ═══════════════════════════════════════════════════════════════════════════

class BotConfig:
    """
    Configuración centralizada del bot.
    Estos valores se pueden sobrescribir con variables de entorno.
    """
    
    # ──────────────────────────────────────────────────────────────────────
    # CONFIGURACIÓN DE KRAKEN
    # ──────────────────────────────────────────────────────────────────────
    KRAKEN_API_KEY = os.getenv('KRAKEN_API_KEY', '')
    KRAKEN_API_SECRET = os.getenv('KRAKEN_API_SECRET', '')
    KRAKEN_API_URL = 'https://api.kraken.com'
    
    # Par de trading en formato Kraken
    # IMPORTANTE: Usar nomenclatura correcta de Kraken
    # Ejemplos válidos: 'ADAUSD', 'SOLUSD', 'BTCUSD', 'ETHUSD'
    TRADING_PAIR = os.getenv('TRADING_PAIR', 'ADAUSD')  # Cardano/USD
    
    # ──────────────────────────────────────────────────────────────────────
    # CONFIGURACIÓN DE TELEGRAM
    # ──────────────────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
    
    # ──────────────────────────────────────────────────────────────────────
    # PARÁMETROS DE TRADING
    # ──────────────────────────────────────────────────────────────────────
    
    # Porcentaje del capital disponible a usar por operación (0.0 a 1.0)
    POSITION_SIZE_PCT = float(os.getenv('POSITION_SIZE_PCT', '0.10'))
    
    # Leverage a utilizar (2, 3, 5, etc.)
    LEVERAGE = int(os.getenv('LEVERAGE', '4'))
    
    # Nivel de swings a usar: 'intermediate' o 'longterm'
    SWING_LEVEL = os.getenv('SWING_LEVEL', 'intermediate')
    
    # Número de velas históricas a analizar
    LOOKBACK_CANDLES = int(os.getenv('LOOKBACK_CANDLES', '200'))
    
    # Intervalo de las velas en minutos
    CANDLE_INTERVAL = int(os.getenv('CANDLE_INTERVAL', '60'))
    
    # ──────────────────────────────────────────────────────────────────────
    # GESTIÓN DE RIESGO
    # ──────────────────────────────────────────────────────────────────────
    
    MAX_DRAWDOWN_PCT = float(os.getenv('MAX_DRAWDOWN_PCT', '20.0'))
    MAX_LOSS_PER_TRADE_PCT = float(os.getenv('MAX_LOSS_PER_TRADE_PCT', '5.0'))
    MIN_BALANCE_USD = float(os.getenv('MIN_BALANCE_USD', '10.0'))
    
    # ──────────────────────────────────────────────────────────────────────
    # MODO DEBUG
    # ──────────────────────────────────────────────────────────────────────
    
    DRY_RUN = os.getenv('DRY_RUN', 'False').lower() == 'false'


# ═══════════════════════════════════════════════════════════════════════════
#                        MAPEO DE PARES DE KRAKEN
# ═══════════════════════════════════════════════════════════════════════════

class KrakenPairMapper:
    """
    Maneja el mapeo entre diferentes formatos de pares en Kraken.
    Kraken a veces devuelve pares en diferentes formatos dependiendo del endpoint.
    """
    
    # Mapeo de pares simplificados a posibles respuestas de Kraken
    PAIR_MAPPINGS = {
        'ADAUSD': ['ADAUSD', 'ADA/USD'],
        'SOLUSD': ['SOLUSD', 'SOL/USD'],
        'BTCUSD': ['BTCUSD', 'XBT/USD', 'XXBTZUSD'],
        'ETHUSD': ['ETHUSD', 'ETH/USD', 'XETHZUSD'],
        'DOTUSD': ['DOTUSD', 'DOT/USD'],
        'MATICUSD': ['MATICUSD', 'MATIC/USD'],
        'LINKUSD': ['LINKUSD', 'LINK/USD'],
    }
    
    @classmethod
    def find_pair_in_result(cls, pair: str, result: dict) -> Optional[str]:
        """
        Busca el par en el resultado de la API, probando diferentes formatos.
        
        Args:
            pair: Par solicitado (ej: 'ADAUSD')
            result: Resultado de la API de Kraken
        
        Returns:
            La clave correcta encontrada en el resultado, o None
        """
        # Primero intentar el par tal cual
        if pair in result:
            return pair
        
        # Buscar en los posibles formatos
        possible_formats = cls.PAIR_MAPPINGS.get(pair, [pair])
        for format_pair in possible_formats:
            if format_pair in result:
                return format_pair
        
        # Si no se encuentra, buscar cualquier clave similar
        pair_lower = pair.lower().replace('/', '')
        for key in result.keys():
            key_lower = key.lower().replace('/', '')
            if key_lower == pair_lower:
                return key
        
        return None


# ═══════════════════════════════════════════════════════════════════════════
#                        CLIENTE DE KRAKEN API
# ═══════════════════════════════════════════════════════════════════════════

class KrakenClient:
    """
    Cliente para interactuar con la API de Kraken.
    Maneja autenticación, solicitudes y operaciones de trading.
    """
    
    def __init__(self, api_key: str, api_secret: str, api_url: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_url = api_url
        self.session = requests.Session()
        self.pair_mapper = KrakenPairMapper()
        
    def _get_kraken_signature(self, urlpath: str, data: Dict) -> str:
        """Genera la firma criptográfica requerida por Kraken."""
        postdata = urllib.parse.urlencode(data)
        encoded = (str(data['nonce']) + postdata).encode()
        message = urlpath.encode() + hashlib.sha256(encoded).digest()
        
        signature = hmac.new(
            base64.b64decode(self.api_secret),
            message,
            hashlib.sha512
        )
        
        return base64.b64encode(signature.digest()).decode()
    
    def _request(self, endpoint: str, data: Dict = None, private: bool = False) -> Dict:
        """
        Realiza una solicitud a la API de Kraken.
        """
        url = self.api_url + endpoint
        
        if private:
            if not self.api_key or not self.api_secret:
                raise ValueError("Se requieren API key y secret para endpoints privados")
            
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
        
        if result.get('error'):
            error_msgs = result['error']
            raise Exception(f"Error de Kraken API: {error_msgs}")
        
        return result.get('result', {})
    
    def verify_pair(self, pair: str) -> bool:
        """
        Verifica que un par de trading es válido en Kraken.
        
        Returns:
            True si el par es válido, False si no
        """
        try:
            result = self._request('/0/public/AssetPairs', data={'pair': pair})
            return len(result) > 0
        except Exception as e:
            print(f"⚠️  Error verificando par {pair}: {e}")
            return False
    
    def get_ohlc_data(self, pair: str, interval: int = 60, since: int = None) -> pd.DataFrame:
        """
        Obtiene datos OHLC (velas) de Kraken.
        """
        data = {'pair': pair, 'interval': interval}
        if since:
            data['since'] = since
        
        result = self._request('/0/public/OHLC', data=data)
        
        # Buscar la clave correcta en el resultado
        pair_key = self.pair_mapper.find_pair_in_result(pair, result)
        
        if not pair_key:
            available_keys = list(result.keys())
            raise Exception(f"No se encontró el par {pair} en la respuesta. "
                          f"Claves disponibles: {available_keys}")
        
        ohlc_data = result[pair_key]
        
        df = pd.DataFrame(ohlc_data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'vwap', 'volume', 'count'
        ])
        
        # Convertir a tipos numéricos
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])
        
        df.set_index('timestamp', inplace=True)
        df = df[['open', 'high', 'low', 'close', 'volume']]
        df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        
        return df
    
    def get_account_balance(self) -> Dict[str, float]:
        """Obtiene el balance de la cuenta."""
        result = self._request('/0/private/Balance', private=True)
        return {k: float(v) for k, v in result.items()}
    
    def get_open_positions(self) -> Dict:
        """Obtiene las posiciones abiertas actuales."""
        try:
            result = self._request('/0/private/OpenPositions', private=True)
            return result
        except Exception as e:
            # Si no hay posiciones abiertas, Kraken puede devolver error
            if "No open positions" in str(e):
                return {}
            raise
    
    def place_market_order(self, pair: str, order_type: str, volume: float, 
                          leverage: int = None) -> Dict:
        """
        Coloca una orden de mercado.
        """
        data = {
            'pair': pair,
            'type': order_type,
            'ordertype': 'market',
            'volume': str(volume)
        }
        
        if leverage and leverage > 1:
            data['leverage'] = str(leverage)
        
        result = self._request('/0/private/AddOrder', data=data, private=True)
        return result
    
    def close_position(self, position_id: str) -> Dict:
        """Cierra una posición específica."""
        data = {'txid': position_id}
        result = self._request('/0/private/ClosePosition', data=data, private=True)
        return result


# ═══════════════════════════════════════════════════════════════════════════
#                        NOTIFICADOR DE TELEGRAM
# ═══════════════════════════════════════════════════════════════════════════

class TelegramNotifier:
    """Envía notificaciones a Telegram sobre las operaciones del bot."""
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}"
    
    def send_message(self, message: str, parse_mode: str = 'HTML') -> bool:
        """Envía un mensaje a Telegram."""
        if not self.bot_token or not self.chat_id:
            print(f"⚠️  Telegram no configurado. Mensaje: {message}")
            return False
        
        try:
            url = f"{self.api_url}/sendMessage"
            data = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': parse_mode
            }
            
            response = requests.post(url, data=data, timeout=10)
            response.raise_for_status()
            return True
            
        except Exception as e:
            print(f"❌ Error enviando mensaje a Telegram: {e}")
            return False
    
    def send_trade_notification(self, trade_info: Dict):
        """Envía una notificación formateada sobre una operación."""
        emoji = "🟢" if trade_info['type'] == 'BUY' else "🔴"
        
        message = f"""
{emoji} <b>NUEVA OPERACIÓN</b> {emoji}

<b>Par:</b> {trade_info['pair']}
<b>Tipo:</b> {trade_info['type']}
<b>Precio:</b> ${trade_info['price']:.4f}
<b>Cantidad:</b> {trade_info['volume']:.2f}
<b>Leverage:</b> {trade_info.get('leverage', 1)}x
<b>Valor:</b> ${trade_info['value']:.2f}

<b>Razón:</b> {trade_info['reason']}
<b>Fecha:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        if trade_info.get('dry_run'):
            message = "🧪 <b>MODO SIMULACIÓN</b> 🧪\n" + message
        
        self.send_message(message)
    
    def send_alert(self, alert_type: str, message: str):
        """Envía una alerta importante."""
        emojis = {
            'error': '❌',
            'warning': '⚠️',
            'info': 'ℹ️',
            'success': '✅'
        }
        
        emoji = emojis.get(alert_type, 'ℹ️')
        formatted_message = f"{emoji} <b>{alert_type.upper()}</b>\n\n{message}"
        self.send_message(formatted_message)


# ═══════════════════════════════════════════════════════════════════════════
#                        DETECTOR DE SWING POINTS
# ═══════════════════════════════════════════════════════════════════════════

class SwingDetector:
    """
    Implementa la lógica de detección de swing points de Larry Williams.
    """
    
    def __init__(self, data: pd.DataFrame):
        self.data = data.copy()
        self.short_term_highs = pd.Series(index=data.index, dtype=float)
        self.short_term_lows = pd.Series(index=data.index, dtype=float)
        self.intermediate_highs = pd.Series(index=data.index, dtype=float)
        self.intermediate_lows = pd.Series(index=data.index, dtype=float)
        self.long_term_highs = pd.Series(index=data.index, dtype=float)
        self.long_term_lows = pd.Series(index=data.index, dtype=float)
    
    def detect_short_term_swings(self):
        """Detecta swing points de corto plazo usando la regla de 3 barras."""
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
        """Construye intermediate swings a partir de short-term swings."""
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
        """Construye long-term swings a partir de intermediate swings."""
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
        """
        Obtiene la última señal de trading basada en los swing points.
        
        Returns:
            Tupla (tipo_señal, precio) donde tipo_señal es 'BUY', 'SELL' o None
        """
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
#                        BOT DE TRADING PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════

class SwingTradingBot:
    """Bot principal que coordina todas las operaciones de trading."""
    
    def __init__(self, config: BotConfig):
        self.config = config
        
        self.kraken = KrakenClient(
            config.KRAKEN_API_KEY,
            config.KRAKEN_API_SECRET,
            config.KRAKEN_API_URL
        )
        
        self.telegram = TelegramNotifier(
            config.TELEGRAM_BOT_TOKEN,
            config.TELEGRAM_CHAT_ID
        )
        
        self.current_position = None
        self.position_entry_price = None
        self.initial_balance = None
        self.peak_balance = None
        
        print("✓ Bot inicializado correctamente")
    
    def check_safety_conditions(self, balance_usd: float) -> Tuple[bool, str]:
        """Verifica las condiciones de seguridad antes de operar."""
        if balance_usd < self.config.MIN_BALANCE_USD:
            return False, f"Balance insuficiente: ${balance_usd:.2f} < ${self.config.MIN_BALANCE_USD}"
        
        if self.initial_balance and self.peak_balance:
            current_drawdown = ((self.peak_balance - balance_usd) / self.peak_balance) * 100
            if current_drawdown > self.config.MAX_DRAWDOWN_PCT:
                return False, f"Drawdown excedido: {current_drawdown:.2f}% > {self.config.MAX_DRAWDOWN_PCT}%"
        
        return True, "Condiciones de seguridad OK"
    
    def calculate_position_size(self, balance_usd: float, current_price: float) -> float:
        """Calcula el tamaño de la posición."""
        capital_to_use = balance_usd * self.config.POSITION_SIZE_PCT
        effective_capital = capital_to_use * self.config.LEVERAGE
        volume = effective_capital / current_price
        return round(volume, 2)
    
    def execute_trade(self, signal: str, current_price: float, reason: str):
        """Ejecuta una operación de trading."""
        try:
            balances = self.kraken.get_account_balance()
            balance_usd = balances.get('ZUSD', 0)
            
            is_safe, safety_msg = self.check_safety_conditions(balance_usd)
            if not is_safe:
                self.telegram.send_alert('warning', f"Operación cancelada: {safety_msg}")
                print(f"⚠️  {safety_msg}")
                return
            
            volume = self.calculate_position_size(balance_usd, current_price)
            
            if volume <= 0:
                print("⚠️  Volumen calculado es 0, no se ejecuta operación")
                return
            
            trade_info = {
                'pair': self.config.TRADING_PAIR,
                'type': signal,
                'price': current_price,
                'volume': volume,
                'leverage': self.config.LEVERAGE,
                'value': volume * current_price,
                'reason': reason,
                'dry_run': self.config.DRY_RUN
            }
            
            if not self.config.DRY_RUN:
                order_type = 'buy' if signal == 'BUY' else 'sell'
                result = self.kraken.place_market_order(
                    pair=self.config.TRADING_PAIR,
                    order_type=order_type,
                    volume=volume,
                    leverage=self.config.LEVERAGE
                )
                
                print(f"✓ Orden ejecutada: {result}")
                trade_info['order_id'] = result.get('txid', [''])[0]
            else:
                print(f"🧪 [SIMULACIÓN] Orden {signal}: {volume} @ ${current_price}")
            
            self.current_position = 'LONG' if signal == 'BUY' else 'SHORT'
            self.position_entry_price = current_price
            
            if self.initial_balance is None:
                self.initial_balance = balance_usd
                self.peak_balance = balance_usd
            elif balance_usd > self.peak_balance:
                self.peak_balance = balance_usd
            
            self.telegram.send_trade_notification(trade_info)
            
        except Exception as e:
            error_msg = f"Error ejecutando operación: {str(e)}"
            print(f"❌ {error_msg}")
            self.telegram.send_alert('error', error_msg)
    
    def run(self):
        """Ejecuta un ciclo completo del bot."""
        print("\n" + "="*70)
        print("INICIANDO CICLO DE TRADING")
        print("="*70)
        print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Par: {self.config.TRADING_PAIR}")
        print(f"Leverage: {self.config.LEVERAGE}x")
        print(f"Nivel de swings: {self.config.SWING_LEVEL}")
        print(f"Modo: {'SIMULACIÓN' if self.config.DRY_RUN else 'REAL'}")
        print("="*70)
        
        try:
            # Verificar que el par es válido
            print(f"\n🔍 Verificando par {self.config.TRADING_PAIR}...")
            if not self.kraken.verify_pair(self.config.TRADING_PAIR):
                raise Exception(f"Par {self.config.TRADING_PAIR} no válido en Kraken. "
                              f"Usa formato como: ADAUSD, SOLUSD, BTCUSD, ETHUSD")
            print(f"✓ Par {self.config.TRADING_PAIR} verificado")
            
            # Descargar datos históricos
            print("\n📊 Descargando datos históricos...")
            ohlc_data = self.kraken.get_ohlc_data(
                pair=self.config.TRADING_PAIR,
                interval=self.config.CANDLE_INTERVAL
            )
            
            ohlc_data = ohlc_data.tail(self.config.LOOKBACK_CANDLES)
            print(f"✓ Descargadas {len(ohlc_data)} velas")
            
            # Detectar swing points
            print("\n🔍 Detectando swing points...")
            detector = SwingDetector(ohlc_data)
            signal, signal_price = detector.get_latest_signal(level=self.config.SWING_LEVEL)
            
            if signal is None:
                print("ℹ️  No se detectaron señales de trading")
                return
            
            print(f"✓ Señal detectada: {signal} @ ${signal_price:.4f}")
            
            # Obtener precio actual
            current_price = ohlc_data['Close'].iloc[-1]
            print(f"💰 Precio actual: ${current_price:.4f}")
            
            # Verificar si necesitamos cambiar de posición
            needs_trade = False
            reason = ""
            
            if self.current_position is None:
                needs_trade = True
                reason = f"Nuevo {signal} signal detectado en nivel {self.config.SWING_LEVEL}"
            elif self.current_position == 'LONG' and signal == 'SELL':
                needs_trade = True
                reason = f"Cambio de estructura: SELL signal detectado (cerrando LONG)"
            elif self.current_position == 'SHORT' and signal == 'BUY':
                needs_trade = True
                reason = f"Cambio de estructura: BUY signal detectado (cerrando SHORT)"
            else:
                print(f"ℹ️  Posición actual ({self.current_position}) alineada con señal ({signal})")
            
            # Ejecutar operación si es necesario
            if needs_trade:
                print(f"\n📈 Ejecutando operación: {signal}")
                self.execute_trade(signal, current_price, reason)
            
            print("\n✓ Ciclo completado exitosamente")
            
        except Exception as e:
            error_msg = f"Error en el ciclo de trading: {str(e)}"
            print(f"\n❌ {error_msg}")
            self.telegram.send_alert('error', error_msg)
            raise


# ═══════════════════════════════════════════════════════════════════════════
#                              MAIN EXECUTION
# ═══════════════════════════════════════════════════════════════════════════

def main():
    """Función principal que inicia el bot."""
    print("""
    ╔═══════════════════════════════════════════════════════════════════════╗
    ║                                                                       ║
    ║         KRAKEN MARGIN TRADING BOT - LARRY WILLIAMS STRATEGY          ║
    ║                         VERSION 2.0 - FIXED                          ║
    ║                                                                       ║
    ╚═══════════════════════════════════════════════════════════════════════╝
    """)
    
    config = BotConfig()
    
    if not config.KRAKEN_API_KEY or not config.KRAKEN_API_SECRET:
        print("❌ ERROR: Credenciales de Kraken no configuradas")
        print("   Configura las variables de entorno KRAKEN_API_KEY y KRAKEN_API_SECRET")
        return
    
    if config.DRY_RUN:
        print("\n⚠️  MODO SIMULACIÓN ACTIVADO - No se ejecutarán órdenes reales\n")
    
    bot = SwingTradingBot(config)
    bot.run()
    
    print("\n✓ Ejecución finalizada")


if __name__ == "__main__":
    main()
