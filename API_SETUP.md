# 🔑 GUÍA COMPLETA: OBTENER Y CONFIGURAR APIs

Este documento te guía paso a paso para obtener cada una de las claves necesarias para ejecutar el bot.

---

## 1. 🤖 TELEGRAM BOT TOKEN

### Dónde obtenerlo:
1. Abre Telegram Web o una app
2. Busca el bot `@BotFather` (es oficial de Telegram)
3. Inicia conversación: `/start`
4. Envía comando: `/newbot`

### Pasos en BotFather:
```
➤ /newbot
"Give your bot a name"
→ Escribe: Asistente Nutricional
(o el nombre que quieras)

"Give your bot a username"
→ Escribe: mi_nutrition_bot_123
(Debe terminar en "_bot" y ser único)

✅ Recibirás un token como:
7123456789:ABCDEFGHijklmNoPqrsTuvwxyzABCDEF
```

### Guardar en `.env`:
```bash
TELEGRAM_BOT_TOKEN=7123456789:ABCDEFGHijklmNoPqrsTuvwxyzABCDEF
```

---

## 2. 🔮 GOOGLE GEMINI API KEY

Google Gemini es el "cerebro" que analiza fotos y texto. Es **GRATIS** hasta cierto límite.

### Dónde obtenerlo:
1. Ve a: https://aistudio.google.com/app/apikey
2. Haz clic en "Create API Key" (Crear clave de API)
3. Selecciona tu proyecto (o crea uno nuevo)
4. ✅ Se genera automáticamente

### Límites gratuitos:
- 60 solicitudes por minuto
- Perfectamente suficiente para uso personal

### Guardar en `.env`:
```bash
GEMINI_API_KEY=AIzaSyDxxx_your_gemini_api_key_xxxxx
```

---

## 3. 🥕 OPEN FOOD FACTS API

Open Food Facts es una **base de datos de alimentos GRATIS y colaborativa**.

### ¿Por qué es importante?
- Busca alimentos por nombre o código de barras
- Proporciona datos nutricionales verificados
- **NO requiere API Key** (es completamente gratuito)
- Mantenido por comunidad

### Para códigos de barras:
El bot automáticamente hará:
```
GET https://world.openfoodfacts.org/api/v3/product/{EAN_CODE}.json
```

### Para búsqueda por nombre:
```
GET https://world.openfoodfacts.org/api/v3/product/search?q=arroz
```

### Guardar en `.env`:
```bash
OFF_API_ENDPOINT=https://world.openfoodfacts.org/api/v3/product
```
(Ya viene por defecto en el `.env.example`)

---

## 4. � USDA FoodData Central API (Fallback)

**CAMBIO IMPORTANTE**: Antes recomendábamos Edamam, pero ya no ofrece un plan gratuito accesible.

Ahora usamos **USDA FoodData Central**, que es **mucho mejor**:

### ¿Por qué USDA FoodData?
✅ **Completamente GRATIS** (sin límites de llamadas)  
✅ **360,000+ alimentos** en su base de datos  
✅ **NO requiere autenticación** (API pública)  
✅ **Precisión garantizada** (datos del USDA)  
✅ **Mantenida por el gobierno** (garantía de permanencia)  

### ¿Dónde obtenerlo?
**No necesitas nada.** La API es completamente pública.

```
URL: https://fdc.nal.usda.gov/api/v1/foods/search
Autenticación: No requerida
Costo: Gratuito
```

### Ejemplo de uso automático:
El bot hará esto automáticamente cuando OFF no encuentre un alimento:
```
GET https://fdc.nal.usda.gov/api/v1/foods/search?query=arroz&pageSize=1
```

### Guardar en `.env`:
```bash
USDA_API_ENDPOINT=https://fdc.nal.usda.gov/api/v1/foods/search
```
(Ya viene por defecto en el `.env.example`)

---

### ¿Y qué pasó con Edamam?

Edamam cambió su modelo de negocio:
- ❌ Ya no ofrece plan "Developer Free" accesible
- ❌ Requiere tarjeta de crédito incluso para probar
- ❌ Límites muy restrictivos ahora

**Conclusión**: USDA FoodData es superior en relación gratuito/funcionalidad.

---

## 5. 📝 RESUMEN: ARCHIVO `.env` FINAL

Crea un archivo `.env` en la **raíz del proyecto** con:

```bash
# Telegram
TELEGRAM_BOT_TOKEN=7123456789:ABCDEFGHijklmNoPqrsTuvwxyzABCDEF

# Google Gemini
GEMINI_API_KEY=AIzaSyDxxx_your_gemini_api_key_xxxxx

# Open Food Facts (Sin cambios necesarios)
OFF_API_ENDPOINT=https://world.openfoodfacts.org/api/v3/product

# USDA FoodData Central (Sin cambios necesarios)
USDA_API_ENDPOINT=https://fdc.nal.usda.gov/api/v1/foods/search

# Database
DB_PATH=data/nutrition_bot.db

# Logging
LOG_LEVEL=INFO
```

---

## ⚠️ NOTAS IMPORTANTES DE SEGURIDAD

1. **NUNCA** subas el `.env` a Git/GitHub
2. Usa `.gitignore` para excluir `.env`:
   ```bash
   echo ".env" >> .gitignore
   ```

3. **APIs Key Seguridad:**
   - Telegram: Puede resetearla en BotFather si se filtra
   - Gemini: Restricciones por IP en la consola de Google Cloud
   - Edamam: Limita por IP en el dashboard

4. **En Producción:**
   - Usa variables de entorno del sistema
   - Usa servicios como AWS Secrets Manager
   - NO incluyas claves en código

---

## 🚀 VERIFICAR QUE TODO FUNCIONA

Después de configurar, antes de ejecutar:

```bash
# 1. Verifica que el .env existe y tiene valores
cat .env

# 2. Verifica que Python puede leer las variables
python -c "from src.config import *; print('✅ Configuración cargada')"

# 3. Si tienes error, revisa:
#    - ¿El archivo .env está cerca de main.py?
#    - ¿Tiene todas las variables?
#    - ¿No hay espacios extraños?
```

---

## 📚 REFERENCIAS OFICIALES

- **Telegram Bot API**: https://core.telegram.org/bots
- **Google Gemini**: https://ai.google.dev/
- **Open Food Facts**: https://world.openfoodfacts.org/
- **Edamam Food Database**: https://developer.edamam.com/food-database-api
- **aiogram 3.x**: https://docs.aiogram.dev/

---

## 🆘 PROBLEMAS COMUNES

### "InvalidToken" o "Unauthorized"
→ Tu TELEGRAM_BOT_TOKEN es incorrecto
→ Cópialo nuevamente de BotFather

### "Gemini API error: 403 Forbidden"
→ Tu GEMINI_API_KEY no es válida
→ Reconfigúralo en: https://aistudio.google.com/app/apikey

### "No module named 'google.generativeai'"
→ No instalaste las dependencias
→ Ejecuta: `pip install -r requirements.txt`

### Bot arranca pero no responde
→ Verifica que polling esté activo
→ Busca logs de error en la consola
→ Prueba escribiendo /start

---

¡Ya estás listo! Continúa leyendo el README para ejecutar el bot. 🚀
