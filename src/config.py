"""
Configuración centralizada del bot de nutrición.

Este módulo carga todas las variables de entorno y proporciona una
interfaz consistente para acceder a la configuración en toda la aplicación.

POR QUÉ ESTO ES IMPORTANTE:
- Mantiene las credenciales fuera del código
- Proporciona valores por defecto seguros
- Centraliza la configuración (fácil de cambiar sin editar código)
- Soporta diferentes ambientes (desarrollo, producción)
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

# ==========================================
# RUTAS DEL PROYECTO
# ==========================================
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# ==========================================
# TELEGRAM
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError(
        "TELEGRAM_BOT_TOKEN no está configurado. "
        "Crea un archivo .env con esta variable."
    )

# ==========================================
# GROQ API
# ==========================================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError(
        "GROQ_API_KEY no está configurado. "
        "Crea un archivo .env con esta variable."
    )

# Modelo de LLM a usar
GROQ_MODEL = "llama-3.3-70b-versatile"  # Mejor modelo activo en Groq (febrero 2025)

# ==========================================
# OPEN FOOD FACTS (Sin autenticación)
# ==========================================
OFF_API_ENDPOINT = os.getenv(
    "OFF_API_ENDPOINT",
    "https://world.openfoodfacts.org/api/v3/product"
)

# ==========================================
# USDA FoodData Central (Sin autenticación)
# ==========================================
USDA_API_ENDPOINT = os.getenv(
    "USDA_API_ENDPOINT",
    "https://fdc.nal.usda.gov/api/v1/foods/search"
)

# ==========================================
# BARCODE LOOKUP API (Sin autenticación, 500 req/día gratis)
# ==========================================
BARCODE_LOOKUP_API = "https://api.barcodebins.com/api/lookup"
BARCODE_LOOKUP_KEY = os.getenv("BARCODE_LOOKUP_KEY", "")  # Opcional

# ==========================================
# UPC DATABASE (Alternativa si Barcode Lookup falla)
# ==========================================
UPC_DATABASE_API = "https://api.upcitemdb.com/prod/trial/lookup"

# ==========================================
# BARCODE LOOKUP API (Sin autenticación, 500 req/día gratis)
# ==========================================
BARCODE_LOOKUP_API = "https://api.barcodebins.com/api/lookup"
BARCODE_LOOKUP_KEY = os.getenv("BARCODE_LOOKUP_KEY", "")  # Opcional

# ==========================================
# UPC DATABASE (Alternativa si Barcode Lookup falla)
# ==========================================
UPC_DATABASE_API = "https://api.upcitemdb.com/prod/trial/lookup"

# ==========================================
# BASE DE DATOS
# ==========================================
DB_PATH = os.getenv("DB_PATH", str(DATA_DIR / "nutrition_bot.db"))

# ==========================================
# LOGGING
# ==========================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ==========================================
# FECHA Y HORA - LÓGICA DEL DÍA
# ==========================================
# El "día lógico" comienza a las 3:00 AM y termina a las 2:59:59 AM
# Esto es importante para las consultas de calorías diarias
LOGICAL_DAY_START_HOUR = 3

# ==========================================
# CONSTANTES DE LA APLICACIÓN
# ==========================================
# Cambios menores que se pueden hacer sin recargar el bot
DEFAULT_MACROS = {
    "carbs": 300,      # Carbohidratos
    "protein": 150,    # Proteínas
    "fat": 80,         # Grasas
}
