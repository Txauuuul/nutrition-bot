# 🏗️ ARQUITECTURA TÉCNICA DETALLADA

Documento que explica en profundidad cómo está construido el bot, por qué cada cosa está donde está, y cómo todo se conecta.

---

## 📊 DIAGRAMA GENERAL

```
┌────────────────────────────────────────────────────────────┐
│                    USUARIO DE TELEGRAM                     │
└─────────────────────────────┬──────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   Telegram    │
                    │   Bot API     │
                    └────────┬────────┘
                             │
                ┌────────────┼────────────┐
                │                        │
                ▼                        ▼
         Polling de Updates      Envío de Mensajes
         (Nuevo mensaje llega)    (Bot responde)
                │                        ▲
                │                        │
                └────────────┬───────────┘
                             │
                    ┌────────▼────────┐
                    │  aiogram 3.x   │
                    │  (BOT FRAMEWORK)│
                    └────────┬────────┘
                             │
                ┌────────────┼────────────┐
                │            │            │
                ▼            ▼            ▼
         ┌──────────┐ ┌──────────┐ ┌──────────┐
         │ Routers  │ │   FSM    │ │Handlers │
         │ (Comandos)│ │(Estados) │ │(Lógica) │
         └──────────┘ └──────────┘ └──────────┘
                             │
                    ┌────────▼────────┐
                    │   API Services  │
                    │ (Gemini/OFF/Ed) │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   Database      │
                    │  (SQLite 3)     │
                    └─────────────────┘
```

---

## 📁 ORGANIZACIÓN DE ARCHIVOS

### Raíz del Proyecto
```
nutrition_bot/
│
├── src/                          # Código principal
├── data/                         # Datos (BD, logs)
├── run.py                        # Script de inicio
├── requirements.txt              # Dependencias
├── .env                          # Variables (NO en Git)
├── .env.example                  # Plantilla
├── .gitignore                    # Git ignore
├── README.md                     # Guía usuario
├── API_SETUP.md                  # Setup de APIs
└── ARQUITECTURA.md               # Este archivo
```

### Estructura `src/`

#### `src/config.py` - CONFIGURACIÓN CENTRALIZADA
**Responsabilidad**: Cargar y validar todas las variables de entorno

```python
# Ejemplo de lo que hace:
- Lee .env
- Define rutas absolutos
- Valida que las claves API existan
- Define constantes (horarios, valores por defecto)
```

**POR QUÉ CENTRALIZAR:**
- Un único lugar donde cambiar configuración
- Fácil de testear
- Seguro: no hardcodea credenciales

**Usos:**
```python
# En otros archivos:
from src.config import TELEGRAM_BOT_TOKEN, DB_PATH, LOGICAL_DAY_START_HOUR
```

---

#### `src/main.py` - PUNTO DE ENTRADA Y LÓGICA DEL BOT
**Responsabilidad**: Define los handlers, routers y flujo del bot

```
COMPONENTES CLAVE:
├── FSM States (NutritionFSM)
├── Routers (main_router, commands_router, fsm_router)
├── Handlers (funciones que responden a mensajes)
└── Setup y ejecución
```

**ESTRUCTURA DE HANDLERS:**

```
handle_text_or_barcode()  ──┬──→ ¿Código de barras?
                             │   └─→ search_open_food_facts_by_barcode()
                             │       └─→ FSM: waiting_quantity
                             │
                             └──→ ¿Texto normal?
                                 └─→ process_with_gemini()
                                     └─→ process_gemini_and_enrich()
                                         └─→ db.log_food()

handle_photo()  ──→ Descargar foto
                ├─→ process_with_gemini(caption + imagen)
                ├─→ process_gemini_and_enrich()
                └─→ db.log_food()

cmd_estado()  ──→ db.get_today_totals()
             └─→ format_nutrition_summary()

cmd_historial()  ──→ Parse fecha
                ├─→ db.get_day_history()
                └─→ format_food_list()

handle_barcode_quantity()  ──→ FSM: waiting_quantity (usuario escribe)
                          ├─→ Parse cantidad
                          ├─→ db.log_food()
                          └─→ state.clear()
```

**POR QUÉ ESTA ESTRUCTURA:**
- Separación clara: cada handler hace una cosa
- FSM para workflows de múltiples pasos
- Reusable: funciones auxiliares (format_*)

---

#### `src/database/db.py` - GESTOR DE BASE DE DATOS
**Responsabilidad**: Toda lógica de persistencia de datos

```python
CLASES Y FUNCIONES:

1. Dataclasses (User, FoodLog, SavedMeal)
   └─→ Representan datos de tablas

2. Funciones de utilidad
   ├─→ get_logical_day_start()
   ├─→ get_logical_day_end()
   └─→ Cálculos de "día lógico"

3. Clase Database
   ├─→ initialize()           # Crear tablas
   ├─→ get_or_create_user()   # CRU de usuarios
   ├─→ log_food()             # Registrar alimento
   ├─→ get_today_totals()     # Resumen del día
   ├─→ get_day_history()      # Historial de un día
   ├─→ delete_last_entry()    # /deshacer
   ├─→ save_meal()            # /guardar_plato
   ├─→ get_saved_meal()       # Retrieval
   ├─→ list_saved_meals()     # /miaplatos
   └─→ delete_saved_meal()    # Eliminar plato

4. Instancia global
   └─→ db = Database()        # Se usa en main.py
```

**LÓGICA DEL DÍA LÓGICO (CRITICA):**

```python
# El día comienza a las 3:00 AM (configurable en src/config.py)

get_logical_day_start(date):
    """
    2:00 AM del 15 febrero → 3:00 AM del 14 febrero (día anterior)
    3:00 AM del 15 febrero → 3:00 AM del 15 febrero (hoy)
    5:00 AM del 15 febrero → 3:00 AM del 15 febrero (hoy)
    """

Ejemplo SQL:
    SELECT SUM(calories) 
    FROM food_logs
    WHERE user_id = 123
      AND timestamp >= "2024-02-14 03:00:00"
      AND timestamp <  "2024-02-15 03:00:00"
```

**POR QUÉ ASYNC:**
- No bloquea el bot mientras hace queries
- Múltiples usuarios simultáneos
- Compatible con aiogram (async-only)

---

#### `src/services/api_services.py` - INTEGRACIONES EXTERNAS
**Responsabilidad**: Comunicación con APIs externas

```python
FLUJOS:

1. Google Gemini
   process_with_gemini(text, image_bytes)
   ├─→ Envía a modelo gemini-1.5-flash
   ├─→ Parsea respuesta JSON
   └─→ Retorna: {"foods": [{name, estimated_grams, nutrition}]}

2. Open Food Facts (Búsqueda por código)
   search_open_food_facts_by_barcode(barcode)
   ├─→ GET /api/v3/product/{barcode}.json
   └─→ Retorna: NutritionalData

3. Open Food Facts (Búsqueda por nombre)
   search_open_food_facts_by_name(food_name)
   ├─→ GET /api/v3/product/search?q=...
   └─→ Retorna: NutritionalData

4. USDA FoodData Central (Fallback)
   search_usda_food_data(food_name)
   ├─→ GET /api/v1/foods/search?query=...
   └─→ Retorna: NutritionalData

5. Orquestación con Fallback
   get_nutrition_by_food_name(food_name)
   ├─→ Intenta OFF
   ├─→ Si falla, intenta USDA FoodData
   └─→ Si falla, retorna None

6. Enriquecimiento de datos Gemini
   process_gemini_and_enrich(gemini_response)
   ├─→ Para cada alimento de Gemini
   ├─→ Busca datos reales en APIs
   └─→ Retorna lista mejorada
```

**CLASE NutritionalData:**
```python
NutritionalData(
    food_name: str,
    calories_per_100g: float,
    protein_per_100g: float,
    carbs_per_100g: float,
    fat_per_100g: float,
    source: str  # "gemini" | "off" | "usda" | "estimated"
)

Métodos:
- calculate_totals(quantity_grams) → {calories, protein, carbs, fat}
- to_dict() → Convertir a JSON
```

**POR QUÉ ESTA ARQUITECTURA:**
- APIs desacopladas: cambiar una sin afectar otras
- Soporte para múltiples fuentes
- Pattern resiliente: es imposible que falle completamente
- Reutilizable: se usa en main.py sin duplicación

---

## 🔄 FLUJOS DE EJECUCIÓN

### Flujo A: Enviar Texto Simple

```
USUARIO: "Arroz con pollo"
    │
    ▼
main.py: handle_text_or_barcode()
    │
    ├─→ is_valid_barcode("Arroz con pollo") → False
    │
    ├─→ process_with_gemini("Arroz con pollo")
    │   └─→ Gemini API devuelve:
    │       {
    │         "foods": [
    │           {
    │             "name": "Arroz blanco",
    │             "estimated_grams": 150,
    │             "calories_per_100g": 130,
    │             ...
    │           },
    │           {
    │             "name": "Pollo a la plancha",
    │             "estimated_grams": 200,
    │             "calories_per_100g": 165,
    │             ...
    │           }
    │         ]
    │       }
    │
    ├─→ process_gemini_and_enrich(gemini_response)
    │   ├─→ Para cada alimento:
    │   │   ├─→ search_open_food_facts_by_name()
    │   │   │   └─→ Si no encuentra, search_usda_food_data()
    │   │   └─→ Retorna NutritionalData enriquecido
    │   │
    │   └─→ Retorna:
    │       [
    │         ("Arroz blanco", 150, NutritionalData),
    │         ("Pollo a la plancha", 200, NutritionalData)
    │       ]
    │
    ├─→ db.get_or_create_user(user_id, name)
    │
    ├─→ Para cada alimento:
    │   ├─→ nutrition.calculate_totals(grams)
    │   │   └─→ {calories: 195, protein: 3, carbs: 29, fat: 0}
    │   ├─→ db.log_food(user_id, name, grams, totals, ...)
    │   │   └─→ Registra en food_logs table
    │   └─→ Acumula totales
    │
    ├─→ db.get_today_totals(user_id)
    │   └─→ SUM de todos los alimentos desde las 03:00:00 AM
    │
    └─→ format_nutrition_summary()
        └─→ Retorna mensaje bonito con resumen


BOT RESPONDE:
✅ Alimentos registrados:
🍽️ Arroz blanco
   150g → 195 kcal | P:3g C:29g G:0g
🍽️ Pollo a la plancha
   200g → 330 kcal | P:66g C:0g G:6g

==================================================
📊 Subtotal añadido
🔥 525 kcal
🥩 69g proteína
🍞 29g carbohidratos
🧈 6g grasas

==================================================
📈 Hoy total:
🔥 1850 kcal
🥩 95g proteína
🍞 210g carbohidratos
🧈 65g grasas
```

---

### Flujo B: Escanear Código de Barras

```
USUARIO: "8431890069843"  (escanea con cámara)
    │
    ▼
main.py: handle_text_or_barcode()
    │
    ├─→ is_valid_barcode("8431890069843") → True
    │
    ├─→ search_open_food_facts_by_barcode("8431890069843")
    │   └─→ OFF API devuelve:
    │       {
    │         "product": {
    │           "product_name": "Yogurt Griego",
    │           "nutrients": {
    │             "energy_kcal_100g": 59,
    │             "proteins_100g": 10,
    │             "carbohydrates_100g": 3,
    │             "fat_100g": 0.5
    │           }
    │         }
    │       }
    │
    ├─→ Crear NutritionalData
    │   └─→ NutritionalData("Yogurt Griego", 59, 10, 3, 0.5)
    │
    ├─→ FSM: state.set_state(NutritionFSM.waiting_quantity)
    ├─→ state.update_data(nutrition_data=..., barcode=...)
    │
    └─→ BOT PREGUNTA: "¿Cuántos gramos consumiste?"


USUARIO RESPONDE: "150"
    │
    ▼
main.py: handle_barcode_quantity()
    │
    ├─→ state.get_data() → obtiene nutrition_data guardado
    │
    ├─→ Parsea "150" → int(150) gramos
    │
    ├─→ Calcula: nutrition.calculate_totals(150)
    │   └─→ {calories: 88, protein: 15, carbs: 4, fat: 0}
    │
    ├─→ db.log_food(
    │       user_id=123,
    │       food_name="Yogurt Griego",
    │       quantity_grams=150,
    │       calories=88,
    │       protein=15,
    │       carbs=4,
    │       fat=0,
    │       barcode="8431890069843"
    │   )
    │
    ├─→ db.get_today_totals()
    │
    ├─→ state.clear()  # Limpiar FSM
    │
    └─→ BOT RESPONDE con resumen


RESULTADO: El alimento está registrado en BD, vinculado a su código EAN
```

---

### Flujo C: El Comando /estado

```
USUARIO: /estado
    │
    ▼
main.py: cmd_estado()
    │
    ├─→ db.get_or_create_user(user_id)
    │
    ├─→ db.get_today_totals(user_id)
    │   └─→ Query SQL:
    │       SELECT SUM(calories), SUM(protein), ...
    │       WHERE user_id = ? 
    │         AND timestamp >= "2024-02-14T03:00:00"
    │         AND timestamp < "2024-02-15T03:00:00"
    │
    ├─→ format_nutrition_summary(totals, user)
    │   └─→ Calcula porcentajes vs objetivos
    │   └─→ Retorna string bonito con emojis
    │
    └─→ message.reply(response)


SI AHORA SON LAS 2:30 AM DEL 15 DE FEBRERO:
    - Usuario piensa que es "día 14"
    - BD query obtiene: desde 03:00:00 del 14 hasta 02:59:59.999 del 15
    - Por eso captura comidas de ayer noche + madrugada
    - ✅ Correcto! (usuario nocturno)
```

---

## 📐 ESQUEMA DE BASE DE DATOS

### users
```sql
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY,           -- ID de Telegram
    name TEXT NOT NULL,                     -- "Juan Pérez"
    daily_calorie_goal INTEGER DEFAULT 2500,
    daily_protein_goal INTEGER DEFAULT 150,
    daily_carbs_goal INTEGER DEFAULT 300,
    daily_fat_goal INTEGER DEFAULT 80,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ÍNDICES:
- PRIMARY KEY: user_id
- Uso: Recuperar perfil del usuario rápidamente
```

### food_logs
```sql
CREATE TABLE food_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,               -- FK → users
    food_name TEXT NOT NULL,                -- "Arroz blanco"
    quantity_grams INTEGER NOT NULL,        -- 150
    calories INTEGER NOT NULL,              -- 195 (180% × 100)
    protein INTEGER NOT NULL,               -- 3g
    carbs INTEGER NOT NULL,                 -- 29g
    fat INTEGER NOT NULL,                   -- 0g
    barcode TEXT,                           -- "8431890069843" (nullable)
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

ÍNDICES:
- PRIMARY KEY: log_id
- COMPOSITE: (user_id, timestamp)
  └─→ Optimiza: WHERE user_id = ? AND timestamp BETWEEN X AND Y
  └─→ Usado en: get_today_totals(), get_day_history()
```

### saved_meals
```sql
CREATE TABLE saved_meals (
    meal_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,               -- FK → users
    meal_name TEXT NOT NULL,                -- "Desayuno típico"
    total_calories INTEGER NOT NULL,        -- 450 (suma)
    total_protein INTEGER NOT NULL,         -- 15g
    total_carbs INTEGER NOT NULL,           -- 50g
    total_fat INTEGER NOT NULL,             -- 20g
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    UNIQUE(user_id, meal_name)  -- No puede haber dos "Desayuno típico" del mismo usuario
);

ÍNDICES:
- PRIMARY KEY: meal_id
- COMPOSITE: (user_id) con UNIQUE constraint
  └─→ Evita nombres duplicados por usuario
```

---

## 🔐 SEGURIDAD Y VALIDACIÓN

### 1. Validación de Entrada

```python
# Barcode validation
is_valid_barcode(text)
    ├─→ Solo dígitos
    ├─→ 8-14 caracteres (rango EAN estándar)
    └─→ No es un número arbitrario

# Cantidad parsing
int(text)  # Lanza ValueError si no es número
if grams <= 0: return error  # Rechaza negativos/cero

# Fecha parsing
datetime.strptime(date_str, "%Y-%m-%d")  # Formato estricto
```

### 2. Inyección SQL

**Protección:** Todas las queries usan placeholders `?`

```python
# ✅ SEGURO:
await db.execute(
    "SELECT * FROM users WHERE user_id = ?",
    (user_id,)  # Parámetro separado
)

# ❌ NUNCA (vulnerable):
query = f"SELECT * FROM users WHERE user_id = {user_id}"
```

### 3. Rate Limiting

No implementado en la versión básica, pero podría añadirse:

```python
# Pseudocódigo para futures:
@rate_limit(max_requests=10, window=60)  # 10 por minuto
async def handle_text_or_barcode(message):
    ...
```

### 4. Credenciales

Las credenciales nunca se hardcodean:

```python
# ✅ Correcto: Desde .env
from src.config import GEMINI_API_KEY

# ❌ Nunca:
GEMINI_API_KEY = "AIzaSyD..."  # En el código fuente
```

---

## 🚀 PATRONES DE DISEÑO UTILIZADOS

### 1. **Router Pattern** (Aiogram)
Cada router maneja un aspecto:
- `main_router`: Mensajes genéricos
- `commands_router`: Comandos `/start`, `/estado`, etc.
- `fsm_router`: Estados específicos

### 2. **Fallback Pattern**
Múltiples intentos en cascada:
```
Intenta A → Si falla, intenta B → Si falla, usa C (default)
```

Ejemplos:
- `get_nutrition_by_food_name()`: OFF → USDA → Estimado
- Búsqueda de alimentos: API1 → API2 → Valores por defecto

### 3. **Singleton Pattern**
```python
# src/database/db.py
db = Database()  # Instancia única global

# En main.py:
from src.database.db import db
await db.log_food(...)  # Siempre el mismo objeto
```

### 4. **Repository Pattern** (BD)
Clase `Database` abstrae toda la persistencia:
- Los handlers NO hacen queries directas
- Todo pasa por `db.*`
- Fácil de testear o cambiar BD

### 5. **Strategy Pattern** (APIs)
Diferentes estrategias para obtener datos nutricionales:
```python
strategy = "barcode"      # Strategy 1: Código → OFF
strategy = "text"         # Strategy 2: Texto → Gemini → APIs
strategy = "fallback"     # Strategy 3: Si todo falla → default
```

### 6. **FSM Pattern** (Workflows)
Estados definidos para flujos de múltiples pasos:
```
waiting_quantity → usuario escribe → procesar → volver a normal
```

---

## 📝 TIPOS DE DATOS CLAVE

### NutritionalData (OOP)
```python
nutrition = NutritionalData(
    food_name="Arroz",
    calories_per_100g=130,
    protein_per_100g=2.7,
    carbs_per_100g=28,
    fat_per_100g=0.3,
    source="off"
)

# Método:
totals = nutrition.calculate_totals(150)  # 150 gramos
# Retorna:
# {
#     "calories": 195,  # 130 * 150 / 100
#     "protein": 4,
#     "carbs": 42,
#     "fat": 0
# }
```

### Dataclasses (BD)
```python
@dataclass
class FoodLog:
    log_id: int
    user_id: int
    food_name: str
    quantity_grams: int
    calories: int
    ...
    timestamp: str

# SQLite devuelve tuplas:
row = (1, 123, "Arroz", 150, 195, ...)
food_log = FoodLog(*row)  # Desempaqueta automáticamente
```

---

## 🧪 TESTING (Recomendaciones Futuras)

```python
# tests/test_api_services.py
@pytest.mark.asyncio
async def test_gemini_parses_food():
    result = await process_with_gemini("Arroz con pollo")
    assert len(result["foods"]) > 0
    assert "name" in result["foods"][0]

# tests/test_database.py
@pytest.mark.asyncio
async def test_log_food_increases_count():
    await db.initialize()
    count_before = await db.get_today_totals(123)
    await db.log_food(123, "Arroz", 150, 195, 3, 42, 0)
    count_after = await db.get_today_totals(123)
    assert count_after["food_count"] == count_before["food_count"] + 1

# tests/test_logical_day.py
def test_logical_day_offsets():
    # 02:30 AM → Día anterior
    dt = datetime(2024, 2, 15, 2, 30)
    start = get_logical_day_start(dt)
    assert start.day == 14
    assert start.hour == 3
    
    # 03:30 AM → Día actual
    dt = datetime(2024, 2, 15, 3, 30)
    start = get_logical_day_start(dt)
    assert start.day == 15
    assert start.hour == 3
```

---

## 🔄 CICLO DE VIDA DEL BOT

```
1. Usuario ejecuta: python run.py
   └─→ run.py verifica Dependencias, .env, config

2. main.py importa todos los módulos
   └─→ config.py carga variables
   └─→ src/main.py importa routers y handlers

3. main() → await db.initialize()
   └─→ Crea tablas si no existen

4. dispatcher.start_polling(bot)
   └─→ Inicia loop de polling
   └─→ Cada ~1 seg pregunta: ¿hay nuevos mensajes?

5. Usuario envía mensaje
   └─→ Telegram recibe
   └─→ Telegram API lo envía a polling
   └─→ aiogram lo procesa
   └─→ Router lo direcciona al handler
   └─→ Handler ejecuta lógica
   └─→ Handler envía respuesta
   └─→ Usuario recibe

6. Cuando usuario presiona Ctrl+C
   └─→ KeyboardInterrupt capturado
   └─→ Bot se detiene gracefully
   └─→ Conexión se cierra
```

---

## 🎓 CONCLUSIÓN

Este bot está diseñado con **principios de arquitectura robusta**:
- ✅ Modular: Cada archivo tiene responsabilidad única
- ✅ Desacoplado: Bajo acoplamiento entre componentes
- ✅ Resiliente: Múltiples fallbacks
- ✅ Seguro: Validación y protección contra SQL injection
- ✅ Escalable: Fácil agregar nuevas APIs o comandos
- ✅ Documentado: Comentarios detallados en código

Espero que esta arquitectura te sea útil como referencia o punto de partida para proyectos más complejos. 🚀

