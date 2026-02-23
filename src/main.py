"""
Bot de Asistente Nutricional con aiogram 3.x

ARQUITECTURA:
1. Dispatcher + Router: Manejo de comandos y mensajes
2. FSM (Finite State Machine): Para workflows que requieren múltiples pasos
3. Handlers: Funciones que procesan eventos de Telegram
4. Database: Persistencia en SQLite
5. APIs: Integración con Gemini, Open Food Facts, USDA FoodData Central

FLUJOS PRINCIPALES:
- Mensaje/Foto → Gemini → BD
- Código de barras → Open Food Facts → Pedir cantidad (FSM) → BD
- Comando /estado → Consulta BD con offset de 3 AM
- Comando /historial → Consulta día específico
- Comando /guardar_plato → Guardar última comida
- Comando /comer_plato → Sumar plato guardado

FSM STATES:
- waiting_quantity: Esperando que usuario introduzca cantidad tras escanear código
- waiting_meal_name: Esperando nombre de plato a guardar
"""

import asyncio
import os
from aiohttp import web
from datetime import datetime
from aiogram import Dispatcher, Router, F, Bot
from aiogram.types import Message, PhotoSize, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import logging

from src.config import TELEGRAM_BOT_TOKEN
from src.database.db import db
from src.services.api_services import (
    process_with_gemini,
    process_gemini_and_enrich,
    search_open_food_facts_by_barcode,
    is_valid_barcode,
    extract_barcode_from_image,
    analyze_food_plate_with_groq,
    _analyze_nutrition_label_with_groq,
    NutritionalData,
)


# ==========================================
# CONFIGURACIÓN DE LOGGING
# ==========================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ==========================================
# MÁQUINA DE ESTADOS (FSM)
# ==========================================

class NutritionFSM(StatesGroup):
    """Estados posibles en el flujo de la aplicación."""
    
    # Espera de cantidad después de código de barras
    waiting_quantity = State()
    waiting_quantity_food = State()  # Para guardar cantidad de alimento
    
    # Espera de nombre de plato
    waiting_meal_name = State()
    waiting_meal_quantity = State()  # Para /comer_plato


# ==========================================
# ROUTERS - ORGANISMOS DE MANEJO
# ==========================================

# Router principal
main_router = Router()
# Router para comandos específicos
commands_router = Router()
# Router para estados FSM
fsm_router = Router()


# ==========================================
# HELPERS / FUNCIONES AUXILIARES
# ==========================================

def format_nutrition_summary(totals: dict, user=None) -> str:
    """
    Formatea el resumen de nutrición para mostrar al usuario.
    
    Args:
        totals: Dict con total_calories, total_protein, total_carbs, total_fat
        user: Usuario (para mostrar objetivos)
        
    Returns:
        Texto formateado bonito
    """
    
    cals = totals.get("total_calories", 0)
    prot = totals.get("total_protein", 0)
    carbs = totals.get("total_carbs", 0)
    fat = totals.get("total_fat", 0)
    
    message = f"""
📊 **RESUMEN NUTRICIONAL DEL DÍA**

🔥 Calorías: **{cals}** kcal"""
    
    if user:
        goal = user.daily_calorie_goal
        percentage = int((cals / goal) * 100) if goal > 0 else 0
        message += f" / {goal} kcal ({percentage}%)"
    
    message += f"""
🥩 Proteína: **{prot}** g"""
    
    if user:
        message += f" / {user.daily_protein_goal}g"
    
    message += f"""
🍞 Carbohidratos: **{carbs}** g"""
    
    if user:
        message += f" / {user.daily_carbs_goal}g"
    
    message += f"""
🧈 Grasas: **{fat}** g"""
    
    if user:
        message += f" / {user.daily_fat_goal}g"
    
    message += f"""
📈 Comidas registradas: **{totals.get('food_count', 0)}**
"""
    
    return message


def format_food_list(food_logs) -> str:
    """Formatea la lista de alimentos consumidos."""
    if not food_logs:
        return "No hay registros para este día."
    
    message = "**Desglose de consumo:**\n\n"
    
    for log in food_logs:
        time = datetime.fromisoformat(log.timestamp).strftime("%H:%M")
        message += (
            f"⏰ {time} - {log.food_name}\n"
            f"   {log.quantity_grams}g → "
            f"{log.calories} kcal | "
            f"P: {log.protein}g | "
            f"C: {log.carbs}g | "
            f"G: {log.fat}g\n\n"
        )
    
    return message


# ==========================================
# HANDLERS PRINCIPAL - TEXTO Y FOTOS
# ==========================================

@main_router.message(F.text, ~F.text.startswith('/'))
async def handle_text_or_barcode(message: Message, state: FSMContext) -> None:
    """
    Maneja mensajes de texto.
    
    FLUJO:
    1. ¿Es un código de barras numérico? → Open Food Facts → Solicitar cantidad (FSM)
    2. ¿Es texto normal? → Gemini → Procesar alimentos
    """
    
    user_id = message.from_user.id
    text = message.text.strip()
    
    await message.chat.do("typing")  # Mostrar indicador de escritura
    
    try:
        # ========== INTENTO 1: ¿ES CÓDIGO DE BARRAS? ==========
        if is_valid_barcode(text):
            logger.info(f"Código de barras detectado: {text}")
            
            nutrition_data = await search_open_food_facts_by_barcode(text)
            
            if nutrition_data:
                # Código encontrado en Open Food Facts
                await message.reply(
                    f"✅ Producto encontrado: **{nutrition_data.food_name}**\n\n"
                    f"Valores por 100g:\n"
                    f"🔥 {nutrition_data.calories_per_100g} kcal\n"
                    f"🥩 {nutrition_data.protein_per_100g}g proteína\n"
                    f"🍞 {nutrition_data.carbs_per_100g}g carbohidratos\n"
                    f"🧈 {nutrition_data.fat_per_100g}g grasa\n\n"
                    f"¿Cuántos gramos consumiste?"
                )
                
                # Guardar en contexto FSM
                await state.set_state(NutritionFSM.waiting_quantity)
                await state.update_data(
                    nutrition_data=nutrition_data.to_dict(),
                    barcode=text
                )
                return
            else:
                await message.reply(
                    "❌ No se encontró el código en la base de datos. "
                    "Intenta describir el alimento."
                )
                return
        
        # ========== INTENTO 2: PROCESAR CON GEMINI ==========
        gemini_result = await process_with_gemini(text)
        
        if not gemini_result:
            await message.reply(
                "⚠️ No pude procesar tu mensaje. "
                "Intenta ser más específico (ej: 'Arroz con pollo')"
            )
            return
        
        # Enriquecer datos
        enriched_foods = await process_gemini_and_enrich(gemini_result)
        
        if not enriched_foods:
            await message.reply("❌ No se encontraron alimentos a procesar.")
            return
        
        # Registrar usuario si no existe
        user = await db.get_or_create_user(user_id, message.from_user.first_name)
        
        # Registrar cada alimento en la BD
        total_calories = 0
        total_protein = 0
        total_carbs = 0
        total_fat = 0
        
        response_message = "✅ **Alimentos registrados:**\n\n"
        
        for food_name, grams, nutrition in enriched_foods:
            totals = nutrition.calculate_totals(grams)
            
            log_id = await db.log_food(
                user_id=user_id,
                food_name=food_name,
                quantity_grams=grams,
                calories=totals["calories"],
                protein=totals["protein"],
                carbs=totals["carbs"],
                fat=totals["fat"],
            )
            
            # Acumular totales
            total_calories += totals["calories"]
            total_protein += totals["protein"]
            total_carbs += totals["carbs"]
            total_fat += totals["fat"]
            
            # Construir respuesta
            response_message += (
                f"🍽️ {food_name}\n"
                f"   {grams}g → {totals['calories']} kcal | "
                f"P:{totals['protein']}g C:{totals['carbs']}g G:{totals['fat']}g\n"
            )
        
        # Agregar resumen
        response_message += f"\n{'='*50}\n"
        response_message += f"📊 **Subtotal añadido**\n"
        response_message += f"🔥 {total_calories} kcal\n"
        response_message += f"🥩 {total_protein}g proteína\n"
        response_message += f"🍞 {total_carbs}g carbohidratos\n"
        response_message += f"🧈 {total_fat}g grasas\n"
        
        # Obtener resumen del día
        today_totals = await db.get_today_totals(user_id)
        response_message += f"\n{'='*50}\n"
        response_message += f"📈 **Hoy total:**\n"
        response_message += f"🔥 {today_totals['total_calories']} kcal\n"
        response_message += f"🥩 {today_totals['total_protein']}g proteína\n"
        response_message += f"🍞 {today_totals['total_carbs']}g carbohidratos\n"
        response_message += f"🧈 {today_totals['total_fat']}g grasas\n"
        
        await message.reply(response_message, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error en handle_text_or_barcode: {str(e)}")
        await message.reply(
            f"❌ Ocurrió un error: {str(e)}\n"
            "Por favor, intenta de nuevo."
        )


@main_router.message(F.photo)
async def handle_photo(message: Message, state: FSMContext) -> None:
    """
    Maneja fotos de comida con DETECCIÓN AUTOMÁTICA DE CÓDIGOS DE BARRAS.
    
    NUEVO FLUJO MEJORADO:
    1. Usuario envía foto (con o sin descripción)
    2. Bot INTENTA LEER código de barras automáticamente
    3. SI ENCUENTRA código:
       → Busca en Open Food Facts automáticamente
       → Obtiene datos exactos del producto
       → Pide cantidad al usuario
    4. SI NO ENCUENTRA código pero hay caption:
       → Usa Groq para analizar la foto + descripción
    5. SI NO ENCUENTRA código ni caption:
       → Pide que agregue descripción
    
    ✨ VENTAJA: El usuario puede simplemente fotografiar el código sin escribir nada.
    """
    
    user_id = message.from_user.id
    
    await message.chat.do("typing")
    
    try:
        # PASO 1: Descargar foto
        photo: PhotoSize = message.photo[-1]  # Última es la más grande
        
        import io
        file = await message.bot.get_file(photo.file_id)
        image_buffer = io.BytesIO()
        await message.bot.download_file(file.file_path, destination=image_buffer)
        image_bytes = image_buffer.getvalue()
        
        print("🔍 Intentando detectar código de barras en la imagen...")
        
        # PASO 2: INTENTAR DETECTAR CÓDIGO DE BARRAS AUTOMÁTICAMENTE
        detected_barcode = await extract_barcode_from_image(image_bytes)
        
        if detected_barcode:
            # ✅ CÓDIGO DE BARRAS DETECTADO - Procesar automáticamente
            print(f"✅ Código detectado: {detected_barcode}")
            
            await message.chat.do("typing")
            
            # Buscar en Open Food Facts (con imagen para fallback de Groq)
            nutrition = await search_open_food_facts_by_barcode(detected_barcode, image_bytes=image_bytes)
            
            if nutrition:
                # ¡Encontrado! Pedir cantidad
                print(f"✅ Producto encontrado: {nutrition.food_name}")
                await state.set_state(NutritionFSM.waiting_quantity)
                await state.update_data(nutrition_data=nutrition.to_dict(), barcode=detected_barcode)
                
                await message.reply(
                    f"✅ <b>Producto identificado:</b>\n\n"
                    f"📦 <b>{nutrition.food_name}</b>\n\n"
                    f"<b>Valores nutricionales por 100g:</b>\n"
                    f"🔥 {nutrition.calories_per_100g} kcal\n"
                    f"🥩 {nutrition.protein_per_100g}g proteína\n"
                    f"🍞 {nutrition.carbs_per_100g}g carbohidratos\n"
                    f"🧈 {nutrition.fat_per_100g}g grasas\n\n"
                    f"<b>¿Cuántos gramos consumiste?</b> (ej: 150)",
                    parse_mode="HTML"
                )
                return
            else:
                # Código válido pero no encontrado en ninguna BD ni por análisis de imagen
                await message.reply(
                    "❌ Código de barras detectado pero no pude identificar el producto.\n\n"
                    "Por favor, reenvía la foto incluyendo la etiqueta nutricional visible,\n"
                    "o describe el alimento manualmente:\n"
                    "ej: 'Lasaña fresca, 400g, etiqueta: 250 kcal, 12g prot, 30g carbs, 8g grasas'\n\n"
                    "Envía otra foto con descripción 📝"
                )
                return
        
        # PASO 3: Sin código de barras - Verificar si hay descripción
        caption = message.caption
        
        if not caption or caption.strip() == "":
            # Sin código ni descripción - Intentar análisis de plato de comida con Groq Vision
            print("📸 Sin código ni caption - Analizando plato de comida con Groq Vision...")
            await message.chat.do("typing")
            
            # Primero intentar identificar como plato de comida
            groq_result = await analyze_food_plate_with_groq(image_bytes)
            
            # Si no funciona como plato, intentar leer etiqueta nutricional
            if not groq_result:
                print("📸 No es un plato identificable, intentando leer etiqueta...")
                groq_result = await _analyze_nutrition_label_with_groq(image_bytes)
            
            if groq_result and groq_result.food_name not in ["Unknown (Groq Analysis)", "Plato no identificado"]:
                # Groq logró identificar el producto/plato
                print(f"✅ Groq identificó: {groq_result.food_name}")
                await state.set_state(NutritionFSM.waiting_quantity)
                await state.update_data(nutrition_data=groq_result.to_dict())
                
                source_label = "Análisis de plato" if groq_result.source == "groq_plate_analysis" else "Lectura de etiqueta"
                
                await message.reply(
                    f"📸 <b>Comida identificada por IA ({source_label}):</b>\n\n"
                    f"🍽️ <b>{groq_result.food_name}</b>\n\n"
                    f"<b>Valores nutricionales estimados por 100g:</b>\n"
                    f"🔥 {groq_result.calories_per_100g} kcal\n"
                    f"🥩 {groq_result.protein_per_100g}g proteína\n"
                    f"🍞 {groq_result.carbs_per_100g}g carbohidratos\n"
                    f"🧈 {groq_result.fat_per_100g}g grasas\n\n"
                    f"<b>¿Cuántos gramos consumiste?</b> (ej: 300)",
                    parse_mode="HTML"
                )
                return
            
            # Groq no pudo - pedir descripción manual
            await message.reply(
                "📸 <b>No pude identificar la comida en la foto</b>\n\n"
                "Por favor, reenvía la foto con una descripción:\n\n"
                "<b>EJEMPLOS:</b>\n"
                "• <code>Lasaña, aproximadamente 300g</code>\n"
                "• <code>Pollo frito con arroz y ensalada</code>\n"
                "• <code>Yogur natural, marca Danone, 150g</code>\n\n"
                "Cuanto más detalle, más precisos serán los macros 📊",
                parse_mode="HTML"
            )
            return
        
        # PASO 4: Hay descripción - Procesar con Groq
        print(f"📸 Analizando foto con descripción: {caption}")
        await message.chat.do("typing")
        
        gemini_result = await process_with_gemini(caption, image_bytes=image_bytes)
        
        if not gemini_result:
            await message.reply(
                "⚠️ No pude analizar la foto. "
                "Intenta descripción más detallada o intenta de nuevo."
            )
            return
        
        # PASO 5: Enriquecer datos nutricionales
        enriched_foods = await process_gemini_and_enrich(gemini_result)
        
        if not enriched_foods:
            await message.reply("❌ No se encontraron alimentos en la foto.")
            return
        
        # PASO 6: Registrar usuario
        user = await db.get_or_create_user(user_id, message.from_user.first_name)
        
        # PASO 7: Registrar alimentos
        total_calories = 0
        total_protein = 0
        total_carbs = 0
        total_fat = 0
        
        response_message = "✅ <b>Alimentos detectados en la foto:</b>\n\n"
        
        for food_name, grams, nutrition in enriched_foods:
            totals = nutrition.calculate_totals(grams)
            
            await db.log_food(
                user_id=user_id,
                food_name=food_name,
                quantity_grams=grams,
                calories=totals["calories"],
                protein=totals["protein"],
                carbs=totals["carbs"],
                fat=totals["fat"],
            )
            
            total_calories += totals["calories"]
            total_protein += totals["protein"]
            total_carbs += totals["carbs"]
            total_fat += totals["fat"]
            
            response_message += (
                f"🍽️ {food_name}\n"
                f"   {grams}g → {totals['calories']} kcal | "
                f"P:{totals['protein']}g C:{totals['carbs']}g G:{totals['fat']}g\n"
            )
        
        response_message += f"\n{'='*50}\n"
        response_message += f"📊 <b>Subtotal añadido</b>\n"
        response_message += f"🔥 {total_calories} kcal | "
        response_message += f"🥩 {total_protein}g | "
        response_message += f"🍞 {total_carbs}g | "
        response_message += f"🧈 {total_fat}g\n"
        
        today_totals = await db.get_today_totals(user_id)
        response_message += f"\n{'='*50}\n"
        response_message += format_nutrition_summary(today_totals, user)
        
        await message.reply(response_message, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Error en handle_photo: {str(e)}")
        await message.reply(f"❌ Error procesando foto: {str(e)}")


# ==========================================
# HANDLERS - ESTADO FSM (ESPERAR CANTIDAD)
# ==========================================

@fsm_router.message(
    NutritionFSM.waiting_quantity,
    F.text,
    ~F.text.startswith('/')
)
async def handle_barcode_quantity(message: Message, state: FSMContext) -> None:
    """
    Maneja entrada de cantidad después de scan de código de barras.
    
    Acepta: "150", "150gr", "150 gr", "150g" - TODO sin problemas
    
    Flujo:
    1. Usuario escribió cantidad 
    2. Parsear - aceptar números con/sin sufijo
    3. Calcular totales
    4. Registrar en BD
    5. Mostrar resumen
    """
    
    user_id = message.from_user.id
    text = message.text.strip()
    
    try:
        # Parseador más flexible - acepta "150", "150gr", "150 gr", "150g", "150 gramos"
        # Limpiar sufijos comunes de cantidad (orden: más largo primero)
        cleaned_text = text.lower().strip()
        for suffix in ["gramos", "grams", "gram", "gr", "g", " "]:
            cleaned_text = cleaned_text.replace(suffix, "").strip()
        
        # Intentar convertir a int
        try:
            grams = int(cleaned_text)
            if grams <= 0:
                await message.reply(
                    "❌ Por favor, introduce una cantidad positiva.\n\n"
                    "Válido: <code>150</code>, <code>150gr</code>, <code>150 g</code>"
                )
                return
            if grams > 10000:
                await message.reply("⚠️ Esa cantidad parece muy grande. ¿Estás seguro?")
                return
        except ValueError:
            await message.reply(
                "❌ No entiendo esa cantidad.\n\n"
                "Por favor, introduce un número:\n"
                "<code>150</code> o <code>150gr</code> o <code>150 g</code>"
            )
            return
        
        # Recuperar datos del contexto
        data = await state.get_data()
        nutrition_dict = data.get("nutrition_data")
        barcode = data.get("barcode")
        
        if not nutrition_dict:
            await message.reply("❌ Contexto perdido. Intenta scanear el código nuevamente.")
            await state.clear()
            return
        
        # Reconstruir NutritionalData
        from src.services.api_services import NutritionalData
        nutrition = NutritionalData(
            food_name=nutrition_dict["food_name"],
            calories_per_100g=nutrition_dict["calories_per_100g"],
            protein_per_100g=nutrition_dict["protein_per_100g"],
            carbs_per_100g=nutrition_dict["carbs_per_100g"],
            fat_per_100g=nutrition_dict["fat_per_100g"],
            source=nutrition_dict["source"]
        )
        
        # Calcular totales
        totals = nutrition.calculate_totals(grams)
        
        # Registrar Usuario
        user = await db.get_or_create_user(user_id, message.from_user.first_name)
        
        # Registrar en BD
        await db.log_food(
            user_id=user_id,
            food_name=nutrition.food_name,
            quantity_grams=grams,
            calories=totals["calories"],
            protein=totals["protein"],
            carbs=totals["carbs"],
            fat=totals["fat"],
            barcode=barcode
        )
        
        # Mostrar confirmación
        response = (
            f"✅ <b>Registrado:</b>\n\n"
            f"🍽️ {nutrition.food_name}\n"
            f"{grams}g → "
            f"{totals['calories']} kcal | "
            f"P:{totals['protein']}g | "
            f"C:{totals['carbs']}g | "
            f"G:{totals['fat']}g\n\n"
        )
        
        # Resumen del día
        day_totals = await db.get_today_totals(user_id)
        response += format_nutrition_summary(day_totals, user)
        
        await message.reply(response, parse_mode="HTML")
        
        # Limpiar estado
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error en handle_barcode_quantity: {str(e)}")
        await message.reply(f"❌ Error: {str(e)}")
        await state.clear()


# ==========================================
# HANDLERS - COMANDOS
# ==========================================

@commands_router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Comando /start - Bienvenida e instrucciones."""
    
    help_text = """
👋 **¡Bienvenido al Asistente Nutricional!**

Soy tu bot de tracking de nutrición. Puedo ayudarte a:
✅ Registrar alimentos por foto o descripción
✅ Escanear códigos de barras
✅ Consultar macros del día
✅ Guardar platos favoritos
✅ Ver historiales de días pasados

**Cómo usarme:**

📝 **Envía texto:** "Desayuno: tostadas con queso y café"
📸 **Envía foto:** Sube una foto de tu plato
📱 **Código de barras:** Escanea un código EAN

**Comandos disponibles:**
/estado - Ver resumen nutricional de hoy
/historial YYYY-MM-DD - Consultar un día específico
/guardar_plato [nombre] - Guardar última comida como plato
/comer_plato [nombre] - Consumir un plato guardado
/deshacer - Eliminar última entrada
/miaplatos - Ver platos guardados
/ayuda - Mostrar esta ayuda

¡Comencemos! Escribe algo o envía una foto 📸
    """
    
    await message.reply(help_text, parse_mode="Markdown")


@commands_router.message(Command("estado"))
async def cmd_estado(message: Message) -> None:
    """Comando /estado - Muestra resumen del día lógico actual."""
    
    user_id = message.from_user.id
    
    try:
        user = await db.get_or_create_user(user_id, message.from_user.first_name)
        totals = await db.get_today_totals(user_id)
        
        response = format_nutrition_summary(totals, user)
        
        await message.reply(response, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error en /estado: {str(e)}")
        await message.reply(f"❌ Error: {str(e)}")


@commands_router.message(Command("historial"))
async def cmd_historial(message: Message) -> None:
    """
    Comando /historial YYYY-MM-DD
    Muestra el registro detallado de un día específico.
    """
    
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Parsear fecha del comando
    parts = text.split()
    
    if len(parts) < 2:
        await message.reply(
            "Uso: /historial YYYY-MM-DD\n"
            "Ejemplo: /historial 2024-01-15"
        )
        return
    
    date_str = parts[1]
    
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        await message.reply(
            f"❌ Formato de fecha inválido: {date_str}\n"
            "Usa YYYY-MM-DD (ej: 2024-01-15)"
        )
        return
    
    try:
        user = await db.get_or_create_user(user_id, message.from_user.first_name)
        summary, food_logs = await db.get_day_history(user_id, target_date)
        
        response = f"📅 **Historial del {date_str}**\n\n"
        response += f"🔥 Calorías: {summary.get('total_calories', 0)} kcal\n"
        response += f"🥩 Proteína: {summary.get('total_protein', 0)}g\n"
        response += f"🍞 Carbohidratos: {summary.get('total_carbs', 0)}g\n"
        response += f"🧈 Grasas: {summary.get('total_fat', 0)}g\n\n"
        
        response += format_food_list(food_logs)
        
        await message.reply(response, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error en /historial: {str(e)}")
        await message.reply(f"❌ Error: {str(e)}")


@commands_router.message(Command("guardar_plato"))
async def cmd_save_meal(message: Message, state: FSMContext) -> None:
    """
    Comando /guardar_plato [nombre]
    Guarda la última comida registrada como un plato reutilizable.
    """
    
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Extraer nombre del plato
    parts = text.split(maxsplit=1)
    
    if len(parts) < 2:
        await message.reply(
            "Uso: /guardar_plato nombre\n"
            "Ejemplo: /guardar_plato Desayuno típico"
        )
        return
    
    meal_name = parts[1]
    
    try:
        # Obtener últimas comidas (registradas hoy)
        summary, food_logs = await db.get_day_history(user_id, datetime.now())
        
        if not food_logs:
            await message.reply(
                "❌ No hay comidas registradas hoy para guardar."
            )
            return
        
        # Tomar la última
        last_foods = food_logs  # Ya ordenados por timestamp DESC
        
        # Acumular totales
        total_calories = sum(f.calories for f in last_foods)
        total_protein = sum(f.protein for f in last_foods)
        total_carbs = sum(f.carbs for f in last_foods)
        total_fat = sum(f.fat for f in last_foods)
        
        # Guardar plato
        meal_id = await db.save_meal(
            user_id=user_id,
            meal_name=meal_name,
            total_calories=total_calories,
            total_protein=total_protein,
            total_carbs=total_carbs,
            total_fat=total_fat
        )
        
        if meal_id == -1:
            await message.reply(
                f"⚠️ Ya existe un plato llamado '{meal_name}'. "
                "Usa otro nombre."
            )
            return
        
        response = f"✅ **Plato guardado: {meal_name}**\n\n"
        response += f"🔥 {total_calories} kcal\n"
        response += f"🥩 {total_protein}g proteína\n"
        response += f"🍞 {total_carbs}g carbohidratos\n"
        response += f"🧈 {total_fat}g grasas\n\n"
        response += "Puedes comerlo con: /comer_plato " + meal_name
        
        await message.reply(response, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error en /guardar_plato: {str(e)}")
        await message.reply(f"❌ Error: {str(e)}")


@commands_router.message(Command("comer_plato"))
async def cmd_eat_meal(message: Message) -> None:
    """
    Comando /comer_plato [nombre]
    Consume un plato guardado (suma sus macros al registro actual).
    """
    
    user_id = message.from_user.id
    text = message.text.strip()
    
    parts = text.split(maxsplit=1)
    
    if len(parts) < 2:
        await message.reply(
            "Uso: /comer_plato nombre\n"
            "Ejemplo: /comer_plato Desayuno típico"
        )
        return
    
    meal_name = parts[1]
    
    try:
        user = await db.get_or_create_user(user_id, message.from_user.first_name)
        
        # Buscar plato
        saved_meal = await db.get_saved_meal(user_id, meal_name)
        
        if not saved_meal:
            await message.reply(f"❌ No existe plato llamado '{meal_name}'")
            return
        
        # Registrar el plato como consumo
        await db.log_food(
            user_id=user_id,
            food_name=f"Plato: {meal_name}",
            quantity_grams=100,  # Es simbólico
            calories=saved_meal.total_calories,
            protein=saved_meal.total_protein,
            carbs=saved_meal.total_carbs,
            fat=saved_meal.total_fat,
        )
        
        response = f"✅ **Plato consumido: {meal_name}**\n\n"
        response += f"🔥 {saved_meal.total_calories} kcal\n"
        response += f"🥩 {saved_meal.total_protein}g proteína\n"
        response += f"🍞 {saved_meal.total_carbs}g carbohidratos\n"
        response += f"🧈 {saved_meal.total_fat}g grasas\n\n"
        
        day_totals = await db.get_today_totals(user_id)
        response += f"{'='*50}\n"
        response += format_nutrition_summary(day_totals, user)
        
        await message.reply(response, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error en /comer_plato: {str(e)}")
        await message.reply(f"❌ Error: {str(e)}")


@commands_router.message(Command("miaplatos"))
async def cmd_my_meals(message: Message) -> None:
    """Comando /miaplatos - Lista los platos guardados del usuario."""
    
    user_id = message.from_user.id
    
    try:
        meals = await db.list_saved_meals(user_id)
        
        if not meals:
            await message.reply("📪 No tienes platos guardados aún.")
            return
        
        response = "🍽️ **Tus platos guardados:**\n\n"
        
        for meal in meals:
            response += (
                f"• **{meal.meal_name}**\n"
                f"  {meal.total_calories} kcal | "
                f"P:{meal.total_protein}g C:{meal.total_carbs}g G:{meal.total_fat}g\n\n"
            )
        
        response += "\nUsa `/comer_plato [nombre]` para consumir uno."
        
        await message.reply(response, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error en /miaplatos: {str(e)}")
        await message.reply(f"❌ Error: {str(e)}")


@commands_router.message(Command("deshacer"))
async def cmd_undo(message: Message) -> None:
    """Comando /deshacer - Elimina la última entrada registrada."""
    
    user_id = message.from_user.id
    
    try:
        success = await db.delete_last_entry(user_id)
        
        if success:
            await message.reply("✅ Última entrada eliminada.")
        else:
            await message.reply("⚠️ No hay entradas para eliminar.")
        
        # Mostrar nuevo resumen
        user = await db.get_or_create_user(user_id, message.from_user.first_name)
        totals = await db.get_today_totals(user_id)
        
        response = format_nutrition_summary(totals, user)
        await message.reply(response, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error en /deshacer: {str(e)}")
        await message.reply(f"❌ Error: {str(e)}")


@commands_router.message(Command("ayuda"))
async def cmd_help(message: Message) -> None:
    """Comando /ayuda - Muestra instrucciones detalladas."""
    
    help_text = """
📚 **GUÍA COMPLETA DE USO**

**Registrando alimentos:**
━━━━━━━━━━━━━━━━━━━━━
1️⃣ Envía un mensaje: "Desayuno: huevo, tostadas, café"
2️⃣ Envía una foto: Foto de tu plato
3️⃣ Escanea código: Tu app de cámara lo captura como texto

**Comandos principales:**
━━━━━━━━━━━━━━━━━━━━━
/estado          - Ver macros del día actual
/historial DD    - Ver día específico (YYYY-MM-DD)
/guardar_plato   - Guardar última comida
/comer_plato     - Consumir plato guardado
/miaplatos       - Ver platos guardados
/deshacer        - Eliminar última entrada

**Ejemplos:**
━━━━━━━━━━━━━━━━━━━━━
💬 "Almuerzo: arroz, pollo y ensalada"
📸 [Envía foto de comida]
📱 [Escanea código de barras]
/historial 2024-02-15
/guardar_plato Mi almuerzo típico
/comer_plato Mi almuerzo típico

**Cómo funciona:**
━━━━━━━━━━━━━━━━━━━━━
• Google Gemini analiza fotos y descripciones
• Busca datos en Open Food Facts y USDA FoodData Central
• Los códigos de barras se verifican directamente
• Todo se guarda en una base de datos local
• El "día" comienza a las 03:00 AM

¿Preguntas? Intenta: /ayuda
    """
    
    await message.reply(help_text, parse_mode="Markdown")


# ==========================================
# CONFIGURACIÓN DEL DISPATCHER
# ==========================================

async def setup_dispatcher():
    """Configura y retorna el dispatcher configurado."""
    
    # Crear storage para state management
    storage = MemoryStorage()
    
    # Crear dispatcher
    dp = Dispatcher(storage=storage)
    
    # Incluir routers en el orden correcto
    # (Los más específicos primero)
    dp.include_router(fsm_router)
    dp.include_router(commands_router)
    dp.include_router(main_router)
    
    return dp

# ==========================================
# SERVIDOR WEB DUMMY (PARA RENDER)
# ==========================================

async def health_check(request):
    """Respuesta básica para que Render sepa que estamos vivos"""
    return web.Response(text="¡Bot nutricional funcionando perfectamente!")

async def start_dummy_server():
    """Inicia un servidor web falso para mantener el puerto abierto en Render"""
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render inyecta el puerto que quiere en la variable de entorno PORT
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"✅ Servidor web de mentira escuchando en el puerto {port}")

# ==========================================
# FUNCIÓN PRINCIPAL
# ==========================================

async def main():
    """Inicia el bot."""
    
    # Inicializar base de datos PostgreSQL + crear pool
    await db.initialize()
    logger.info("✅ Base de datos PostgreSQL inicializada")
    
    await start_dummy_server()

    # Crear bot
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    # Configurar dispatcher
    dp = await setup_dispatcher()
    
    logger.info("🤖 Bot iniciado")
    logger.info("⏳ Esperando mensajes...")
    
    try:
        # Iniciar polling (escucha cambios)
        await dp.start_polling(bot)
    finally:
        # Cerrar conexiones y pool
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
