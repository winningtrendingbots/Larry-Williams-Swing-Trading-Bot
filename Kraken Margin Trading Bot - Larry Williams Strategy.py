"""
═══════════════════════════════════════════════════════════════════════════
    KRAKEN MARGIN TRADING BOT - LARRY WILLIAMS SWING STRATEGY
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
    TRADING_PAIR = 'XADAZUSD'  # Cardano/USD
    
    # ──────────────────────────────────────────────────────────────────────
    # CONFIGURACIÓN DE TELEGRAM
    # ──────────────────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
    
    # ──────────────────────────────────────────────────────────────────────
    # PARÁMETROS DE TRADING
    # ──────────────────────────────────────────────────────────────────────
    
    # Porcentaje del capital disponible a usar por operación (0.0 a 1.0)
    # Ejemplo: 0.25 = usar el 25% del capital disponible
    POSITION_SIZE_PCT = float(os.getenv('POSITION_SIZE_PCT', '0.25'))
    
    # Leverage a utilizar (2, 3, 5, etc.) - Kraken permite hasta 5x en la mayoría de pares
    LEVERAGE = int(os.getenv('LEVERAGE', '3'))
    
    # Nivel de swings a usar: 'intermediate' o 'longterm'
    SWING_LEVEL = os.getenv('SWING_LEVEL', 'intermediate')
    
    # Número de velas históricas a analizar
    LOOKBACK_CANDLES = int(os.getenv('LOOKBACK_CANDLES', '500'))
    
    # Intervalo de las velas en minutos (60 = 1 hora, 240 = 4 horas, 1440 = 1 día)
    CANDLE_INTERVAL = int(os.getenv('CANDLE_INTERVAL', '60'))
    
    # ──────────────────────────────────────────────────────────────────────
    # GESTIÓN DE RIESGO
    # ──────────────────────────────────────────────────────────────────────
    
    # Máximo drawdown permitido antes de detener el bot (en porcentaje)
    MAX_DRAWDOWN_PCT = float(os.getenv('MAX_DRAWDOWN_PCT', '20.0'))
    
    # Pérdida máxima por operación (en porcentaje del capital)
    MAX_LOSS_PER_TRADE_PCT = float(os.getenv('MAX_LOSS_PER_TRADE_PCT', '5.0'))
    
    # Mínimo balance requerido para operar (en USD)
    MIN_BALANCE_USD = float(os.getenv('MIN_BALANCE_USD', '100.0'))
    
    # ──────────────────────────────────────────────────────────────────────
    # MODO DEBUG
    # ──────────────────────────────────────────────────────────────────────
    
    # Si está en True, no ejecuta órdenes reales, solo simula
    DRY_RUN = os.getenv('DRY_RUN', 'False').lower() == 'true'


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
        
    def _get_kraken_signature(self, urlpath: str, data: Dict) -> str:
        """
        Genera la firma criptográfica requerida por Kraken para autenticar requests.
        
        Kraken requiere una firma HMAC-SHA512 que incluye:
        - El nonce (timestamp único)
        - Los datos del request
        - La ruta del endpoint
        """
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
        
        Args:
            endpoint: Ruta del endpoint (ej: '/0/private/Balance')
            data: Datos a enviar en el request
            private: Si True, usa autenticación (para endpoints privados)
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
            
            response = self.session.post(url, data=data, headers=headers)
        else:
            response = self.session.get(url, params=data)
        
        response.raise_for_status()
        result = response.json()
        
        if result.get('error'):
            raise Exception(f"Error de Kraken API: {result['error']}")
        
        return result.get('result', {})
    
    def get_ohlc_data(self, pair: str, interval: int = 60, since: int = None) -> pd.DataFrame:
        """
        Obtiene datos OHLC (velas) de Kraken.
        
        Args:
            pair: Par de trading (ej: 'XADAZUSD')
            interval: Intervalo en minutos (1, 5, 15, 30, 60, 240, 1440, etc.)
            since: Timestamp desde el cual obtener datos
        
        Returns:
            DataFrame con columnas: timestamp, open, high, low, close, volume
        """
        data = {'pair': pair, 'interval': interval}
        if since:
            data['since'] = since
        
        result = self._request('/0/public/OHLC', data=data)
        
        # Kraken devuelve datos en un formato específico
        ohlc_data = result[pair]
        
        df = pd.DataFrame(ohlc_data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'vwap', 'volume', 'count'
        ])
        
        # Convertir a tipos numéricos apropiados
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])
        
        df.set_index('timestamp', inplace=True)
        df = df[['open', 'high', 'low', 'close', 'volume']]
        df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        
        return df
    
    def get_account_balance(self) -> Dict[str, float]:
        """
        Obtiene el balance de la cuenta.
        
        Returns:
            Diccionario con los balances de cada asset
        """
        result = self._request('/0/private/Balance', private=True)
        return {k: float(v) for k, v in result.items()}
    
    def get_open_positions(self) -> Dict:
        """
        Obtiene las posiciones abiertas actuales.
        """
        result = self._request('/0/private/OpenPositions', private=True)
        return result
    
    def place_market_order(self, pair: str, order_type: str, volume: float, 
                          leverage: int = None) -> Dict:
        """
        Coloca una orden de mercado.
        
        Args:
            pair: Par de trading
            order_type: 'buy' o 'sell'
            volume: Cantidad a comprar/vender
            leverage: Leverage a usar (opcional)
        
        Returns:
            Información de la orden colocada
        """
        data = {
            'pair': pair,
            'type': order_type,
            'ordertype': 'market',
            'volume': str(volume)
        }
        
        if leverage:
            data['leverage'] = str(leverage)
        
        result = self._request('/0/private/AddOrder', data=data, private=True)
        return result
    
    def close_position(self, position_id: str) -> Dict:
        """
        Cierra una posición específica.
        """
        data = {'txid': position_id}
        result = self._request('/0/private/ClosePosition', data=data, private=True)
        return result


# ═══════════════════════════════════════════════════════════════════════════
#                        NOTIFICADOR DE TELEGRAM
# ═══════════════════════════════════════════════════════════════════════════

class TelegramNotifier:
    """
    Envía notificaciones a Telegram sobre las operaciones del bot.
    """
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}"
    
    def send_message(self, message: str, parse_mode: str = 'HTML') -> bool:
        """
        Envía un mensaje a Telegram.
        
        Args:
            message: Texto del mensaje (puede incluir HTML)
            parse_mode: Formato del mensaje ('HTML' o 'Markdown')
        """
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
            
            response = requests.post(url, data=data)
            response.raise_for_status()
            return True
            
        except Exception as e:
            print(f"❌ Error enviando mensaje a Telegram: {e}")
            return False
    
    def send_trade_notification(self, trade_info: Dict):
        """
        Envía una notificación formateada sobre una operación.
        """
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
        """
        Envía una alerta importante.
        """
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
    Identifica puntos de giro en tres niveles: short-term, intermediate, long-term.
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
        """
        Detecta swing points de corto plazo usando la regla de 3 barras.
        """
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
        """
        Construye intermediate swings a partir de short-term swings.
        """
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
        """
        Construye long-term swings a partir de intermediate swings.
        """
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
        
        Args:
            level: Nivel de swings a usar ('intermediate' o 'longterm')
        
        Returns:
            Tupla (tipo_señal, precio) donde tipo_señal es 'BUY', 'SELL' o None
        """
        self.detect_long_term_swings()  # Esto también detecta todos los niveles anteriores
        
        if level == 'longterm':
            highs = self.long_term_highs
            lows = self.long_term_lows
        else:
            highs = self.intermediate_highs
            lows = self.intermediate_lows
        
        # Obtener el último swing point (high o low)
        last_high_idx = highs.last_valid_index()
        last_low_idx = lows.last_valid_index()
        
        if last_high_idx is None and last_low_idx is None:
            return None, None
        
        # Determinar cuál ocurrió más recientemente
        if last_low_idx is None:
            return 'SELL', highs[last_high_idx]
        elif last_high_idx is None:
            return 'BUY', lows[last_low_idx]
        else:
            # El más reciente determina la señal
            if last_low_idx > last_high_idx:
                return 'BUY', lows[last_low_idx]
            else:
                return 'SELL', highs[last_high_idx]


# ═══════════════════════════════════════════════════════════════════════════
#                        BOT DE TRADING PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════

class SwingTradingBot:
    """
    Bot principal que coordina todas las operaciones de trading.
    """
    
    def __init__(self, config: BotConfig):
        self.config = config
        
        # Inicializar componentes
        self.kraken = KrakenClient(
            config.KRAKEN_API_KEY,
            config.KRAKEN_API_SECRET,
            config.KRAKEN_API_URL
        )
        
        self.telegram = TelegramNotifier(
            config.TELEGRAM_BOT_TOKEN,
            config.TELEGRAM_CHAT_ID
        )
        
        # Estado del bot
        self.current_position = None  # 'LONG', 'SHORT', o None
        self.position_entry_price = None
        self.initial_balance = None
        self.peak_balance = None
        
        print("✓ Bot inicializado correctamente")
    
    def check_safety_conditions(self, balance_usd: float) -> Tuple[bool, str]:
        """
        Verifica las condiciones de seguridad antes de operar.
        
        Returns:
            Tupla (es_seguro, mensaje_razón)
        """
        # Verificar balance mínimo
        if balance_usd < self.config.MIN_BALANCE_USD:
            return False, f"Balance insuficiente: ${balance_usd:.2f} < ${self.config.MIN_BALANCE_USD}"
        
        # Verificar drawdown máximo
        if self.initial_balance and self.peak_balance:
            current_drawdown = ((self.peak_balance - balance_usd) / self.peak_balance) * 100
            if current_drawdown > self.config.MAX_DRAWDOWN_PCT:
                return False, f"Drawdown excedido: {current_drawdown:.2f}% > {self.config.MAX_DRAWDOWN_PCT}%"
        
        return True, "Condiciones de seguridad OK"
    
    def calculate_position_size(self, balance_usd: float, current_price: float) -> float:
        """
        Calcula el tamaño de la posición basado en el balance y configuración.
        
        Returns:
            Cantidad de ADA a comprar/vender
        """
        # Capital a usar en esta operación
        capital_to_use = balance_usd * self.config.POSITION_SIZE_PCT
        
        # Con leverage, podemos controlar más capital
        effective_capital = capital_to_use * self.config.LEVERAGE
        
        # Calcular cantidad de ADA
        volume = effective_capital / current_price
        
        # Redondear a 2 decimales (Kraken requiere cierta precisión)
        volume = round(volume, 2)
        
        return volume
    
    def execute_trade(self, signal: str, current_price: float, reason: str):
        """
        Ejecuta una operación de trading.
        
        Args:
            signal: 'BUY' o 'SELL'
            current_price: Precio actual del mercado
            reason: Razón de la operación (para logging)
        """
        try:
            # Obtener balance actual
            balances = self.kraken.get_account_balance()
            balance_usd = balances.get('ZUSD', 0)
            
            # Verificar condiciones de seguridad
            is_safe, safety_msg = self.check_safety_conditions(balance_usd)
            if not is_safe:
                self.telegram.send_alert('warning', f"Operación cancelada: {safety_msg}")
                print(f"⚠️  {safety_msg}")
                return
            
            # Calcular tamaño de posición
            volume = self.calculate_position_size(balance_usd, current_price)
            
            if volume <= 0:
                print("⚠️  Volumen calculado es 0, no se ejecuta operación")
                return
            
            # Información de la operación
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
            
            # Ejecutar operación (o simular si DRY_RUN)
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
                print(f"🧪 [SIMULACIÓN] Orden {signal}: {volume} ADA @ ${current_price}")
            
            # Actualizar estado del bot
            self.current_position = 'LONG' if signal == 'BUY' else 'SHORT'
            self.position_entry_price = current_price
            
            # Actualizar métricas de balance
            if self.initial_balance is None:
                self.initial_balance = balance_usd
                self.peak_balance = balance_usd
            elif balance_usd > self.peak_balance:
                self.peak_balance = balance_usd
            
            # Notificar
            self.telegram.send_trade_notification(trade_info)
            
        except Exception as e:
            error_msg = f"Error ejecutando operación: {str(e)}"
            print(f"❌ {error_msg}")
            self.telegram.send_alert('error', error_msg)
    
    def run(self):
        """
        Ejecuta un ciclo completo del bot.
        """
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
            # 1. Descargar datos históricos
            print("\n📊 Descargando datos históricos...")
            ohlc_data = self.kraken.get_ohlc_data(
                pair=self.config.TRADING_PAIR,
                interval=self.config.CANDLE_INTERVAL
            )
            
            # Tomar solo las últimas N velas
            ohlc_data = ohlc_data.tail(self.config.LOOKBACK_CANDLES)
            print(f"✓ Descargadas {len(ohlc_data)} velas")
            
            # 2. Detectar swing points
            print("\n🔍 Detectando swing points...")
            detector = SwingDetector(ohlc_data)
            signal, signal_price = detector.get_latest_signal(level=self.config.SWING_LEVEL)
            
            if signal is None:
                print("ℹ️  No se detectaron señales de trading")
                return
            
            print(f"✓ Señal detectada: {signal} @ ${signal_price:.4f}")
            
            # 3. Obtener precio actual
            current_price = ohlc_data['Close'].iloc[-1]
            print(f"💰 Precio actual: ${current_price:.4f}")
            
            # 4. Verificar si necesitamos cambiar de posición
            needs_trade = False
            reason = ""
            
            if self.current_position is None:
                # No tenemos posición, abrir una nueva
                needs_trade = True
                reason = f"Nuevo {signal} signal detectado en nivel {self.config.SWING_LEVEL}"
            
            elif self.current_position == 'LONG' and signal == 'SELL':
                # Cerrar long y abrir short
                needs_trade = True
                reason = f"Cambio de estructura: SELL signal detectado (cerrando LONG)"
            
            elif self.current_position == 'SHORT' and signal == 'BUY':
                # Cerrar short y abrir long
                needs_trade = True
                reason = f"Cambio de estructura: BUY signal detectado (cerrando SHORT)"
            
            else:
                print(f"ℹ️  Posición actual ({self.current_position}) alineada con señal ({signal})")
            
            # 5. Ejecutar operación si es necesario
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
    """
    Función principal que inicia el bot.
    """
    print("""
    ╔═══════════════════════════════════════════════════════════════════════╗
    ║                                                                       ║
    ║         KRAKEN MARGIN TRADING BOT - LARRY WILLIAMS STRATEGY          ║
    ║                                                                       ║
    ╚═══════════════════════════════════════════════════════════════════════╝
    """)
    
    # Validar configuración
    config = BotConfig()
    
    if not config.KRAKEN_API_KEY or not config.KRAKEN_API_SECRET:
        print("❌ ERROR: Credenciales de Kraken no configuradas")
        print("   Configura las variables de entorno KRAKEN_API_KEY y KRAKEN_API_SECRET")
        return
    
    if config.DRY_RUN:
        print("\n⚠️  MODO SIMULACIÓN ACTIVADO - No se ejecutarán órdenes reales\n")
    
    # Crear y ejecutar bot
    bot = SwingTradingBot(config)
    bot.run()
    
    print("\n✓ Ejecución finalizada")


if __name__ == "__main__":
    main()
