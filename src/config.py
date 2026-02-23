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
# BARCODE APIs (Fallback)
# ==========================================
BARCODE_LOOKUP_API = "https://api.barcodebins.com/api/lookup"
BARCODE_LOOKUP_KEY = os.getenv("BARCODE_LOOKUP_KEY", "")

UPC_DATABASE_API = "https://api.upcitemdb.com/prod/trial/lookup"

# ==========================================
# POSTGRESQL - SUPABASE
# ==========================================
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError(
        "❌ DATABASE_URL no está configurado. \n"
        "En Render: Añade la variable de entorno DATABASE_URL con tu URL de Supabase. \n"
        "Formato esperado: postgresql://user:password@host:5432/database"
    )

# Validar que DATABASE_URL no sea un placeholder
if "your_password" in DATABASE_URL or "xxxxx" in DATABASE_URL:
    raise ValueError(
        "❌ DATABASE_URL contiene placeholders (your_password, xxxxx). \n"
        "Reemplaza con tus credenciales reales de Supabase. \n"
        "En Render: Usa el valor real de tu base de datos."
    )

# Validar formato básico
if not DATABASE_URL.startswith("postgresql://"):
    raise ValueError(
        "❌ DATABASE_URL debe comenzar con 'postgresql://'. \n"
        "Valor actual: " + DATABASE_URL[:30] + "..."
    )

# ==========================================
# LÓGICA DEL "DÍA" (Nutrición)
# ==========================================
# El día nutricional comienza a las 3:00 AM en lugar de las 00:00 AM
# Esto permite que los usuarios finales durmiendo no pierdan sus datos
# Ejemplo: Un usuario que se duerme a las 2 AM sigue en el "día anterior"
# Así sus datos nocturno no se dividen en dos días
LOGICAL_DAY_START_HOUR = int(os.getenv("LOGICAL_DAY_START_HOUR", 3))
