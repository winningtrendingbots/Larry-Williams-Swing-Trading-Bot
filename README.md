# ═══════════════════════════════════════════════════════════════════════════
# ARCHIVO 4: README.md - INSTRUCCIONES COMPLETAS
# ═══════════════════════════════════════════════════════════════════════════

# README.md

# 🤖 Kraken Swing Trading Bot - Larry Williams Strategy

Bot de trading automatizado que implementa la estrategia de swing structure de Larry Williams para operar en Kraken con margen.

## ⚠️ ADVERTENCIAS IMPORTANTES

- **Este bot opera con dinero real en Kraken**
- El trading con margen amplifica tanto ganancias como pérdidas
- Nunca inviertas más de lo que puedas permitirte perder
- Siempre comienza con modo simulación (`DRY_RUN=true`)
- Los resultados pasados no garantizan rendimientos futuros
- Asegúrate de entender completamente la estrategia antes de usar el bot

## 📋 Requisitos Previos

### 1. Cuenta de Kraken
- Cuenta verificada en Kraken
- Trading en margen habilitado
- API keys generadas con permisos de:
  - ✅ Query Funds
  - ✅ Query Open Orders & Trades
  - ✅ Query Closed Orders & Trades
  - ✅ Create & Modify Orders
  - ✅ Cancel/Close Orders

### 2. Bot de Telegram
- Crear un bot con [@BotFather](https://t.me/botfather)
- Obtener el token del bot
- Obtener tu Chat ID (puedes usar [@userinfobot](https://t.me/userinfobot))

### 3. Repositorio de GitHub
- Fork o clone de este repositorio
- Actions habilitado en el repositorio

## 🔧 Configuración Paso a Paso

### Paso 1: Obtener API Keys de Kraken

1. Inicia sesión en Kraken
2. Ve a **Settings → API**
3. Clic en **Generate New Key**
4. Configura los permisos necesarios:
   - Query Funds ✅
   - Query Open Orders & Trades ✅
   - Create & Modify Orders ✅
5. **IMPORTANTE**: Guarda la API Key y Secret inmediatamente (solo se muestra una vez)

### Paso 2: Crear Bot de Telegram

1. Abre Telegram y busca [@BotFather](https://t.me/botfather)
2. Envía el comando `/newbot`
3. Sigue las instrucciones para nombrar tu bot
4. Guarda el **Token** que te proporciona
5. Busca [@userinfobot](https://t.me/userinfobot) para obtener tu **Chat ID**

### Paso 3: Configurar GitHub Secrets

En tu repositorio de GitHub:

1. Ve a **Settings → Secrets and variables → Actions**
2. Clic en **New repository secret**
3. Agrega los siguientes secrets:

#### Secrets OBLIGATORIOS:

| Nombre | Descripción | Ejemplo |
|--------|-------------|---------|
| `KRAKEN_API_KEY` | Tu API Key de Kraken | `abc123def456...` |
| `KRAKEN_API_SECRET` | Tu API Secret de Kraken | `xyz789uvw012...` |
| `TELEGRAM_BOT_TOKEN` | Token de tu bot de Telegram | `1234567890:ABCdefGHI...` |
| `TELEGRAM_CHAT_ID` | Tu Chat ID de Telegram | `123456789` |

#### Secrets OPCIONALES (con valores por defecto):

| Nombre | Descripción | Default | Rango |
|--------|-------------|---------|-------|
| `POSITION_SIZE_PCT` | % del capital a usar por operación | `0.25` | 0.0 - 1.0 |
| `LEVERAGE` | Multiplicador de apalancamiento | `3` | 1 - 5 |
| `SWING_LEVEL` | Nivel de swings (`intermediate` o `longterm`) | `intermediate` | - |
| `LOOKBACK_CANDLES` | Número de velas históricas a analizar | `500` | 100+ |
| `CANDLE_INTERVAL` | Intervalo de velas en minutos | `60` | 1, 5, 15, 60, 240, 1440 |
| `MAX_DRAWDOWN_PCT` | Drawdown máximo permitido | `20.0` | 0.0 - 100.0 |
| `MAX_LOSS_PER_TRADE_PCT` | Pérdida máxima por operación | `5.0` | 0.0 - 100.0 |
| `MIN_BALANCE_USD` | Balance mínimo requerido | `10.0` | > 0 |

### Paso 4: Configurar el Repositorio

1. Clona o haz fork de este repositorio
2. Asegúrate de tener esta estructura de archivos:

```
tu-repositorio/
├── .github/
│   └── workflows/
│       └── trading-bot.yml
├── kraken_trading_bot.py
├── requirements.txt
├── .gitignore
└── README.md
```
