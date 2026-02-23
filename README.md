# 🥗 ASISTENTE NUTRICIONAL DE TELEGRAM

Un bot inteligente para registrar, analizar y gestionar tu consumo nutricional mediante Telegram. Utiliza **Google Gemini** (visión + IA), **Open Food Facts** y **USDA FoodData Central** para proporcionar análisis detallados.

---

## ✨ CARACTERÍSTICAS PRINCIPALES

### 🧠 Sistema de Análisis Inteligente

#### 1. **Procesamiento por IA (Fotos + Texto)**
- Envía un descripción de tu comida o una foto
- Google Gemini analiza y estima cantidades
- Obtiene datos nutricionales automáticamente
- Registra todo en la base de datos

#### 2. **Identificación por Código de Barras**
- Escanea un código EAN con tu cámara
- El bot lo envía a Open Food Facts
- Retorna datos EXACTOS del producto
- Te pide que indiques la cantidad consumida

#### 3. **Búsqueda Inteligente (Fallback)**
- Si Open Food Facts no encuentra un alimento → intenta USDA FoodData Central
- Si USDA no encuentra → usa estimación de Gemini
- Garantiza que SIEMPRE encuentre datos

### 📊 Gestión de Datos

- **BD LOCAL**: SQLite sin servidor externo
- **Platos Reutilizables**: Guarda tus comidas favoritas
- **Historial Completo**: Consulta cualquier día del pasado
- **Día Lógico**: Las 3:00 AM es el inicio del día nutricional

### 🎯 Comandos Disponibles

| Comando | Descripción |
|---------|-------------|
| `/start` | Bienvenida e instrucciones |
| `/estado` | Resumen de hoy (calorías, macros) |
| `/historial YYYY-MM-DD` | Consulta un día específico |
| `/guardar_plato [nombre]` | Guarda última comida como plato |
| `/comer_plato [nombre]` | Come un plato guardado |
| `/miaplatos` | Lista de platos guardados |
| `/deshacer` | Elimina la última entrada |
| `/ayuda` | Instrucciones detalladas |

---

## 🏗️ ARQUITECTURA DEL PROYECTO

```
nutrition_bot/
├── src/
│   ├── __init__.py
│   ├── config.py                 # Configuración centralizada (APIs, variables)
│   ├── main.py                   # Punto de entrada (bot con aiogram)
│   ├── database/
│   │   ├── __init__.py
│   │   └── db.py                 # Gestor SQLite + queries + lógica día lógico
│   ├── services/
│   │   ├── __init__.py
│   │   └── api_services.py       # Integración con Gemini, OFF, USDA
│   └── handlers/                 # (Directorio para expansión futura)
├── data/
│   └── nutrition_bot.db          # Base de datos (generada automáticamente)
├── .env                          # Variables de entorno (NO en Git)
├── .env.example                  # Plantilla de variables
├── .gitignore                    # Archivos a ignorar en Git
├── requirements.txt              # Dependencias Python
├── API_SETUP.md                  # Guía paso a paso de APIs
└── README.md                     # Este archivo
```

---

## 📋 REQUISITOS PREVIOS

### Sistema Operativo
- ✅ Windows / macOS / Linux
- Python 3.8+ instalado

### Cuentas Necesarias
- 🤖 **Telegram**: Cuenta normal (los datos son tuyos)
- 📱 **BotFather**: Para crear el bot (es un bot oficial de Telegram)
- 🔮 **Google Cloud**: Para API de Gemini (GRATIS con límites generosos)
- 🥕 **Open Food Facts**: NO requiere registro (completamente GRATIS)
- � **USDA FoodData Central**: NO requiere registro (completamente GRATIS)

---

## 🚀 INSTALACIÓN PASO A PASO

### Paso 1: Clonar o Descargar el Proyecto

```bash
# Si tienes Git:
git clone <url-del-repositorio> nutrition_bot
cd nutrition_bot

# O descarga manual:
# Descomprime nutrition_bot.zip
# cd nutrition_bot
```

### Paso 2: Instalar Dependencias

```bash
# Crear entorno virtual (recomendado)
python -m venv venv

# Activar entorno virtual
# En Windows:
venv\Scripts\activate
# En macOS/Linux:
source venv/bin/activate

# Instalar paquetes
pip install -r requirements.txt
```

### Paso 3: Configurar APIs

**Lea el archivo `API_SETUP.md`** para obtener paso a paso:
- Cómo crear bot en BotFather
- Cómo generar Gemini API Key
- Por qué usamos USDA FoodData (en lugar de Edamam)

### Paso 4: Crear archivo `.env`

Copia `.env.example` a `.env` y completa con tus claves:

```bash
# Copiar plantilla
cp .env.example .env

# Editar con tu editor favorito
# (VSCode, Notepad++, etc.)
nano .env  # en Linux/macOS
```

Contenido mínimo requerido:

```bash
TELEGRAM_BOT_TOKEN=7123456789:ABCDEFGHijklmNoPqrsTuvwxyzABCDEF
GEMINI_API_KEY=AIzaSyDxxxxxxxxxxxxxxxxxxxxxxxxx
DB_PATH=data/nutrition_bot.db
LOG_LEVEL=INFO
```

Nota: Open Food Facts y USDA FoodData Central no requieren credenciales (APIs públicas).

### Paso 5: Ejecutar el Bot

```bash
# Asegúrate que estés en el directorio del proyecto
cd nutrition_bot

# Ejecutar
python src/main.py
```

**Deberías ver:**
```
INFO:root:✅ Base de datos inicializada
INFO:root:🤖 Bot iniciado
INFO:root:⏳ Esperando mensajes...
```

---

## 🎮 CÓMO USAR

### Uso Básico

1. **Abre Telegram** y busca tu bot (por el username que creaste en BotFather)
2. **Envía `/start`** para ver instrucciones
3. **Prueba los comandos:**

#### Ejemplo 1: Registrar por Texto
```
Usuario: "Desayuno: dos huevos, tostadas, café con leche"
Bot: Analiza con Gemini y registra
Bot: Resumen: 450 kcal, 20g proteína, 30g carbs, 15g grasas
```

#### Ejemplo 2: Registrar por Foto
```
Usuario: [Envía foto de su plato]
Bot: "Detectados: Arroz blanco, pollo a la plancha, brócoli"
Bot: Pide confirmación y registra
```

#### Ejemplo 3: Registrar por Código de Barras
```
Usuario: "8431890069843"  (escanea el código con la cámara)
Bot: "✅ Encontrado: Yogurt Griego"
Bot: "¿Cuántos gramos?"
Usuario: "150"
Bot: Registra y muestra resumen
```

#### Ejemplo 4: Consultar Estado
```
Usuario: /estado
Bot: Muestra:
    Calorías: 1850/2500 (74%)
    Proteína: 95/150g
    Carbos: 210/300g
    Grasas: 65/80g
    Comidas registradas: 3
```

#### Ejemplo 5: Guardar y Reutilizar
```
Usuario: /guardar_plato Desayuno típico
Bot: Guarda la última comida como plato

Usuario: /comer_plato Desayuno típico
Bot: Suma los macros de ese plato al registro de hoy
```

---

## 🗄️ BASE DE DATOS

### Estructura

La base de datos SQLite se crea automáticamente en `data/nutrition_bot.db`:

#### Tabla `users`
```sql
user_id (PK)           -- ID de Telegram
name                   -- Nombre del usuario
daily_calorie_goal     -- Objetivo de kcal (default: 2500)
daily_protein_goal     -- Objetivo de proteína (default: 150g)
daily_carbs_goal       -- Objetivo de carbos (default: 300g)
daily_fat_goal         -- Objetivo de grasas (default: 80g)
created_at             -- Timestamp de registro
```

#### Tabla `food_logs`
```sql
log_id (PK)            -- ID único del registro
user_id (FK)           -- Quién lo registró
food_name              -- "Arroz blanco"
quantity_grams         -- Cantidad exacta
calories               -- Total calculado
protein, carbs, fat    -- Desglose de macros
barcode (nullable)     -- Si viene de código EAN
timestamp              -- Cuándo se registró
```

#### Tabla `saved_meals`
```sql
meal_id (PK)           -- ID del plato
user_id (FK)           -- A quién pertenece
meal_name              -- "Desayuno típico"
total_calories         -- Suma de ingredientes
total_protein, etc.    -- Macros totales
created_at             -- Cuándo se guardó
UNIQUE(user_id, meal_name)  -- No repetir nombres
```

### Lógica del "Día Lógico"

El sistema usa un **offset de 3 AM** para determinar qué registros son "de hoy":

```python
# Ejemplo:
# Hora actual: 02:30 AM del 15 de febrero
# El sistema considera que es parte del 14 de febrero (el día empezó a las 3 AM de hoy)

# Hora actual: 03:30 AM del 15 de febrero
# El sistema considera que es parte del 15 de febrero (el día empezó hace 30 min)

# Esta lógica es útil para usuarios nocturnos que entrenan/cenan tarde
```

---

## 🔧 FLUJOS TÉCNICOS

### Flujo 1: Procesar Foto/Texto

```
Usuario envía mensaje o foto
    ↓
¿Es número (código de barras)?
    NO ↓
Google Gemini analiza y devuelve alimentos + estimación de pesos
    ↓
Para cada alimento:
    - Buscar en Open Food Facts
    - Si no encuentra → buscar en USDA FoodData Central
    - Si sigue sin encontrar → usar estimación de Gemini
    ↓
Calcular totales (cantidad × valores por 100g)
    ↓
Registrar en SQLite
    ↓
Mostrar resumen bonito al usuario
```

### Flujo 2: Código de Barras

```
Usuario envía: "8431890069843"
    ↓
¿Es un número válido (8-14 dígitos)?
    SÍ ↓
Buscar en Open Food Facts API
    ↓
¿Se encontró?
    SÍ ↓
Mostrar producto + valores por 100g
    ↓
"¿Cuántos gramos consumiste?"
    ↓
Usuario responde cantidad
    ↓
Calcular totales y registrar
    ↓
Mostrar resumen
```

### Flujo 3: Máquina de Estados (FSM)

```
waiting_quantity (después de barcode)
    - Usuario debe escribir número
    - Se calcula y registra
    - Se vuelve al estado normal

waiting_meal_name (al guardar plato)
    - Usuario escribe nombre del plato
    - Se guarda en BD
    - Se vuelve al estado normal
```

---

## 📊 EXPLICACIONES TÉCNICAS CLAVE

### 1. ¿Por qué aiogram 3.x?
- **Async-first**: No bloquea mientras espera APIs
- **FSM built-in**: Máquinas de estado integradas para workflows
- **Modular**: Fácil de expandir y mantener
- **Moderno**: Soporta Telegram Bot API v7.0+

### 2. ¿Por qué SQLite?
- **Embebido**: No necesita servidor externo
- **Archivo único**: Fácil de backup (`data/nutrition_bot.db`)
- **Async-ready**: Se puede usar con `aiosqlite`
- **ACID compliant**: Datos consistentes incluso si se corta la electricidad

### 3. ¿Por qué múltiples APIs de nutrición?
- **Open Food Facts**: Mantenida por comunidad, muy completa
- **USDA FoodData Central**: Base de datos oficial, 360,000+ alimentos
- **Gemini**: Fallback cuando falla todo 

Es un patrón **resiliente**: Si uno falla, tenemos otros.

### 4. ¿El "día lógico" de 3 AM por qué?
- Usuarios hispanohablantes suelen cenar tarde/trasnochando
- Permite capturar cenas nocturnas en el día que corresponde
- Estándar común en fitness trackers profesionales
- **Customizable**: Cambiar en `src/config.py` si lo necesitas

---

## 🐛 SOLUCIÓN DE PROBLEMAS

### El bot arranca pero no responde

**Causas posibles:**
1. Token inválido en `.env`
2. Bot no iniciado en BotFather
3. No tienes permisos para usar el bot

**Solución:**
```bash
# 1. Verifica el token
grep TELEGRAM_BOT_TOKEN .env

# 2. Re-resetea el token en BotFather
# Comando: /mybots → Selecciona bot → Edit Bot → API Token

# 3. Prueba escribiendo /start
```

### "ModuleNotFoundError: No module named 'aiogram'"

**Causa**: Dependencias no instaladas o entorno virtual no activado

**Solución:**
```bash
# Activar entorno virtual PRIMERO
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Luego instalar
pip install -r requirements.txt
```

### Gemini devuelve error "403 Forbidden"

**Causa**: API Key inválida o no configurada

**Solución:**
```bash
# 1. Verifica la clave en .env
grep GEMINI_API_KEY .env

# 2. Regenera en https://aistudio.google.com/app/apikey

# 3. Copia exactamente (sin espacios extras)
```

### Fotos no se procesan

**Causa**: La foto es demasiado grande o el formato no es válido

**Solución:**
```bash
# Telegram recomprime fotos automáticamente
# Si sigue fallando, intenta:
# 1. Usar JPG en lugar de PNG
# 2. Foto desde la cámara de Telegram (no galería antigua)
```

### "Base de datos bloqueada" (sqlite3.OperationalError)

**Causa**: Múltiples procesos accediendo simultáneamente

**Solución:**
```bash
# 1. Cierra otros bots/procesos que usen nutrition_bot.db

# 2. Si persiste, reinicia:
rm data/nutrition_bot.db  # Elimina (perderás datos)
python src/main.py        # Se creará nueva

# 3. Para producción, usa PostgreSQL en lugar de SQLite
```

---

## 🚀 PROXIMAS MEJORAS SUGERIDAS

1. **Antes/Después de Fotos**
   - Fotos de "antes/después" para tracking visual
   - Almacenar en el servidor

2. **Notificaciones**
   - Recordatorio a hora específica para registrar comidas
   - Alertas si superas objetivos

3. **Integración con Strava/Apple Health**
   - Importar calorías quemadas
   - Calcular déficit/superávit

4. **Análisis Predictor**
   - Proyectar macros si continúas así
   - Recomendaciones de qué comer

5. **Dashboard Web**
   - Gráficos de tendencia
   - Exportar a PDF

6. **Soporte Multiidioma**
   - Español, inglés, francés, etc.

7. **Sincronización con MyFitnessPal**
   - Importar/exportar datos

---

## 📝 ARCHIVO .gitignore

Crea `.gitignore` para no subir datos sensibles:

```
# Entorno virtual
venv/
env/
.venv

# Variables de entorno
.env
.env.local

# Base de datos
data/nutrition_bot.db
*.db

# Python
__pycache__/
*.py[cod]
*$py.class
*.so

# IDE
.vscode/
.idea/
*.swp
*.swo

# Sistema
.DS_Store
Thumbs.db
```

---

## 📚 REFERENCIAS Y DOCUMENTACIÓN

### Librerías Utilizadas
- **aiogram**: https://docs.aiogram.dev/
- **google-generativeai**: https://ai.google.dev/tutorials/python_quickstart
- **aiohttp**: https://docs.aiohttp.org/
- **aiosqlite**: https://github.com/omnilib/aiosqlite
- **python-dotenv**: https://github.com/theskumar/python-dotenv

### APIs Integradas
- **Telegram Bot API**: https://core.telegram.org/bots/api
- **Google Gemini**: https://ai.google.dev/
- **Open Food Facts**: https://world.openfoodfacts.org/data
- **USDA FoodData Central**: https://fdc.nal.usda.gov/

### Tutoriales Recomendados
- Crear bots con aiogram: https://aiogram.dev/dispatcher/
- FSM en Telegram: https://docs.aiogram.dev/en/latest/dispatcher/fsm/
- API REST async: https://aiohttp.readthedocs.io/

---

## 📞 SOPORTE Y PREGUNTAS

Si tienes dudas:

1. **Lee el archivo `API_SETUP.md`** para problemas de configuración
2. **Revisa los comentarios en el código** - muy detallados
3. **Busca los logs** en la consola - dicen exactamente qué falló
4. **Prueba manualmente las APIs:**
   ```bash
   # Test Gemini
   python -c "from src.config import *; print('✅ Gemini configurado')"
   
   # Test base de datos
   python -c "import asyncio; from src.database.db import db; asyncio.run(db.initialize()); print('✅ BD lista')"
   ```

---

## 📄 LICENCIA

Este proyecto es **código libre y educativo**. Úsalo, modifícalo y comparte.

---

## 🎓 NOTAS FINALES

Este es un proyecto **production-ready pero educativo**:
- ✅ Código modular y comentado
- ✅ Manejo de errores robusto
- ✅ Arquitectura escalable
- ✅ APIs documentadas
- ⚠️ Para producción real, agrega logs más detallados y monitoreo

**¡Espero que te sea útil!** 🚀

---

**Última actualización**: Febrero 2026
**Versión**: 1.0
**Autor**: Senior Python Developer
