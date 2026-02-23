"""
Servicios de APIs externas para procesamiento nutricional.

ARQUITECTURA DE FLUJOS:

1. CÓDIGO DE BARRAS EN FOTO → DETECTAR → OPEN FOOD FACTS → Datos exactos
2. FOTO SIN CÓDIGO → GROQ Análisis → OPEN FOOD FACTS/USDA
3. TEXTO DESCRIPTIVO → GROQ → OPEN FOOD FACTS/USDA

LIBRERÍAS USADAS:
- pyzbar: Detectar códigos de barras en imágenes (UPC, EAN, etc)
- pytesseract: OCR fallback para leer números
- opencv: Procesamiento avanzado de imágenes
- groq: SDK oficial de Groq para LLaMA (gratuito, sin límites)
- aiohttp: HTTP asíncrono
"""

import json
import re
from typing import Dict, Optional, List, Tuple
import aiohttp
import requests
from groq import Groq
from PIL import Image
import cv2
import numpy as np
from io import BytesIO
import base64

# Barcode detection
try:
    from pyzbar.pyzbar import decode as pyzbar_decode
    PYZBAR_AVAILABLE = True
except ImportError:
    PYZBAR_AVAILABLE = False
    print("⚠️ pyzbar no disponible. Instalando: pip install pyzbar")

try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False
    print("⚠️ pytesseract no disponible. Instalando: pip install pytesseract")

from src.config import (
    GROQ_API_KEY,
    GROQ_MODEL,
    OFF_API_ENDPOINT,
    USDA_API_ENDPOINT,
)


# ==========================================
# CONFIGURAR GROQ
# ==========================================
groq_client = Groq(api_key=GROQ_API_KEY)


# ==========================================
# TIPOS Y ESTRUCTURAS
# ==========================================

class NutritionalData:
    """Estructura para datos nutricionales standardizados."""
    
    def __init__(
        self,
        food_name: str,
        calories_per_100g: float,
        protein_per_100g: float,
        carbs_per_100g: float,
        fat_per_100g: float,
        source: str = "unknown"
    ):
        self.food_name = food_name
        self.calories_per_100g = calories_per_100g
        self.protein_per_100g = protein_per_100g
        self.carbs_per_100g = carbs_per_100g
        self.fat_per_100g = fat_per_100g
        self.source = source  # "gemini", "off", "edamam"
    
    def calculate_totals(self, quantity_grams: int) -> Dict[str, int]:
        """Calcula totales basado en cantidad."""
        return {
            "calories": int((self.calories_per_100g / 100) * quantity_grams),
            "protein": int((self.protein_per_100g / 100) * quantity_grams),
            "carbs": int((self.carbs_per_100g / 100) * quantity_grams),
            "fat": int((self.fat_per_100g / 100) * quantity_grams),
        }
    
    def to_dict(self) -> Dict:
        """Convierte a diccionario."""
        return {
            "food_name": self.food_name,
            "calories_per_100g": self.calories_per_100g,
            "protein_per_100g": self.protein_per_100g,
            "carbs_per_100g": self.carbs_per_100g,
            "fat_per_100g": self.fat_per_100g,
            "source": self.source,
        }


# ==========================================
# SISTEMA ATWATER - CÁLCULO REAL DE CALORÍAS
# ==========================================

def _atwater_kcal(protein_g: float, carbs_g: float, fat_g: float) -> float:
    """
    Calcula calorías usando el sistema Atwater exacto.
    
    Factores Atwater generales:
      - Proteínas: 4 kcal/g
      - Carbohidratos: 4 kcal/g
      - Grasas: 9 kcal/g
    
    Esto SIEMPRE es correcto por definición bioquímica.
    Nunca confiar en que una IA calcule calorías: hacerlo en Python.
    """
    return round((protein_g * 4) + (carbs_g * 4) + (fat_g * 9), 1)


def _validate_and_fix_calories(calories_reported: float, protein_g: float, carbs_g: float, fat_g: float) -> float:
    """
    Valida calorías reportadas contra Atwater.
    Si la diferencia es >20%, usa el cálculo Atwater.
    """
    atwater = _atwater_kcal(protein_g, carbs_g, fat_g)
    if atwater == 0:
        return calories_reported
    deviation = abs(calories_reported - atwater) / atwater
    if deviation > 0.20:
        print(f"  ⚠️ Atwater override: reportadas {calories_reported} kcal vs calculadas {atwater} kcal (desviación {deviation:.0%})")
        return atwater
    return calories_reported


# ==========================================
# DETECCIÓN DE CÓDIGOS DE BARRAS EN IMÁGENES (MEJORADO)
# ==========================================

async def extract_barcode_from_image(image_bytes: bytes) -> Optional[str]:
    """
    Intenta extraer código de barras EAN/UPC de una imagen.
    
    ESTRATEGIA ALMEJORA:
    1. pyzbar - Detección directa (RGB + Gray + Enhanced + Inverted)
    2. Preprocesamiento agresivo (morphology, dilate, erode)
    3. Múltiples rotaciones (0°, 90°, 180°, 270°)
    
    Retorna código detectado (ej: "8431890069843") o None.
    """
    try:
        img = Image.open(BytesIO(image_bytes))
        
        # Convertir a RGB si es necesario
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        img_array = np.array(img)
        
        # Intentar múltiples rotaciones y transformaciones
        rotation_angles = [0, 90, 180, 270]
        
        for angle in rotation_angles:
            # Rotar imagen si es necesario
            if angle > 0:
                img_rotated = Image.fromarray(img_array)
                img_rotated = img_rotated.rotate(angle, expand=False)
                img_array_work = np.array(img_rotated)
            else:
                img_array_work = img_array.copy()
            
            # INTENTO 1: RGB directo
            result = _try_pyzbar_decode(img_array_work, f"RGB {angle}°")
            if result:
                return result
            
            # INTENTO 2: Escala de grises
            try:
                gray = cv2.cvtColor(img_array_work, cv2.COLOR_RGB2GRAY)
                result = _try_pyzbar_decode(gray, f"Gray {angle}°")
                if result:
                    return result
            except Exception as e:
                pass
            
            # INTENTO 3: CLAHE Enhanced (contraste mejorado)
            try:
                gray = cv2.cvtColor(img_array_work, cv2.COLOR_RGB2GRAY)
                clahe = cv2.createCLAHE(clipLimit=5.0, tileGridSize=(12, 12))
                enhanced = clahe.apply(gray)
                result = _try_pyzbar_decode(enhanced, f"Enhanced {angle}°")
                if result:
                    return result
            except Exception as e:
                pass
            
            # INTENTO 4: Inverted
            try:
                gray = cv2.cvtColor(img_array_work, cv2.COLOR_RGB2GRAY)
                inverted = cv2.bitwise_not(gray)
                result = _try_pyzbar_decode(inverted, f"Inverted {angle}°")
                if result:
                    return result
            except Exception as e:
                pass
            
            # INTENTO 5: Morphological operations (especial para códigos oscuros)
            try:
                gray = cv2.cvtColor(img_array_work, cv2.COLOR_RGB2GRAY)
                
                # Aplicar threshold adaptativo
                thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                               cv2.THRESH_BINARY, 11, 2)
                
                # Operaciones morfológicas
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
                morph = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=1)
                morph = cv2.morphologyEx(morph, cv2.MORPH_OPEN, kernel, iterations=1)
                
                result = _try_pyzbar_decode(morph, f"Morphology {angle}°")
                if result:
                    return result
            except Exception as e:
                pass
            
            # INTENTO 6: Normalización de histograma
            try:
                gray = cv2.cvtColor(img_array_work, cv2.COLOR_RGB2GRAY)
                equalized = cv2.equalizeHist(gray)
                result = _try_pyzbar_decode(equalized, f"Equalized {angle}°")
                if result:
                    return result
            except Exception as e:
                pass
            
            # INTENTO 7: Gaussian blur + threshold (para reducir ruido)
            try:
                gray = cv2.cvtColor(img_array_work, cv2.COLOR_RGB2GRAY)
                blurred = cv2.GaussianBlur(gray, (5, 5), 0)
                _, thresh = cv2.threshold(blurred, 127, 255, cv2.THRESH_BINARY)
                result = _try_pyzbar_decode(thresh, f"Blurred+Thresh {angle}°")
                if result:
                    return result
            except Exception as e:
                pass
        
        print("❌ No se detectó código de barras con ninguna estrategia")
        return None
        
    except Exception as e:
        print(f"❌ Error general en extract_barcode: {e}")
        return None


def _try_pyzbar_decode(img_array, strategy_name: str) -> Optional[str]:
    """
    Intenta decodificar código de barras con pyzbar.
    
    Args:
        img_array: Array de imagen (RGB, Gray, etc)
        strategy_name: Nombre de la estrategia (para logging)
    
    Returns:
        String del código o None
    """
    if not PYZBAR_AVAILABLE:
        return None
    
    try:
        decoded_objects = pyzbar_decode(img_array)
        
        for obj in decoded_objects:
            barcode = obj.data.decode('utf-8').strip()
            
            # Validar que sea código de barras válido (8-14 dígitos)
            if barcode.isdigit() and 8 <= len(barcode) <= 14:
                print(f"  ✅ DETECTADO {strategy_name}: {barcode}")
                return barcode
            elif barcode and len(barcode) > 0:
                # Extraer secuencia de dígitos si hay otros caracteres
                digits = re.search(r'(\d{8,14})', barcode)
                if digits:
                    code = digits.group(1)
                    print(f"  ✅ DETECTADO {strategy_name} (limpiado): {code}")
                    return code
    
    except Exception as e:
        pass
    
    return None


async def process_with_gemini(
    text_description: str,
    image_bytes: Optional[bytes] = None
) -> Optional[Dict]:
    """
    Procesa texto y/o imagen con Groq (LLaMA).
    
    ESTRATEGIA ANTI-ALUCINACIÓN:
    1. Groq SOLO estima macronutrientes (proteínas, carbohidratos, grasas)
    2. PROHIBIDO que Groq calcule calorías → las calcula Python vía Atwater
    3. Si no se especifican gramos, estima ración estándar realista
    4. Temperatura 0.1 para máxima precisión factual
    """
    try:
        # SYSTEM PROMPT como nutricionista clínico
        system_prompt = """Eres un nutricionista clínico experto. Tu única base de datos de referencia es el USDA FoodData Central.

REGLAS INQUEBRANTABLES:
1. NUNCA calcules calorías ni kcal. Ese campo NO existe en tu respuesta.
2. Solo reporta proteínas, carbohidratos y grasas en gramos TOTALES para la porción.
3. Si el usuario NO especifica gramos, estima una RACIÓN ESTÁNDAR REALISTA de adulto:
   - Plato de pasta cocida: 250g
   - Plato de arroz cocido: 200g
   - Pechuga de pollo: 200g
   - Filete de ternera/cerdo: 200g
   - Ensalada mixta: 200g
   - Tostada de pan: 30g
   - Huevo: 60g
   - Café con leche: 200ml
   - Vaso de zumo: 250ml
   - Yogur: 125g
   - Pizza (porción): 200g
   - Hamburguesa completa: 250g
   - Plato de legumbres: 300g
4. Los macros deben ser para la CANTIDAD TOTAL estimada, no por 100g.
5. Usa valores realistas del USDA. Ejemplo: 250g pasta cocida = ~8g prot, ~78g carbs, ~3g grasa.
6. Responde ÚNICAMENTE con JSON válido. Sin explicaciones, sin markdown."""

        # USER PROMPT
        user_prompt = f"""El usuario ha comido: "{text_description}"

Devuelve un JSON con esta estructura EXACTA (sin campo de calorías):
{{"foods": [{{{{
  "alimento": "nombre descriptivo del plato",
  "cantidad_g": 250,
  "proteinas_g": 8.0,
  "carbohidratos_g": 30.0,
  "grasas_g": 6.0
}}}}]}}

Si hay varios alimentos, pon un objeto por cada uno en el array.
PROHIBIDO incluir "calorias", "kcal", "energy" o cualquier campo de calorías.
Responde SOLO con el JSON."""
        
        # Llamar a Groq con imagen (multimodal) o solo texto
        if image_bytes:
            import base64 as b64
            image_data = b64.standard_b64encode(image_bytes).decode("utf-8")
            message = groq_client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_data}",
                                },
                            },
                            {
                                "type": "text",
                                "text": user_prompt
                            }
                        ],
                    }
                ],
                temperature=0.1,
                max_tokens=512
            )
        else:
            message = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=512
            )
        
        response_text = message.choices[0].message.content.strip()
        print(f"🤖 Groq raw response: {response_text[:300]}")
        
        # Limpiar markdown si existe
        for marker in ["```json", "```"]:
            response_text = response_text.replace(marker, "")
        response_text = response_text.strip()
        
        # Intentar parsear JSON directamente
        result = None
        try:
            result = json.loads(response_text)
        except json.JSONDecodeError:
            # Si falla, buscar JSON en la respuesta con regex
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
        
        if not result or "foods" not in result or not result["foods"]:
            print(f"⚠️ Groq no retornó JSON válido: {response_text[:150]}")
            return None
        
        # POST-PROCESO: Calcular calorías vía Atwater y normalizar formato
        normalized_foods = []
        for food in result["foods"]:
            name = food.get("alimento") or food.get("name", "Alimento desconocido")
            cantidad_g = food.get("cantidad_g") or food.get("estimated_grams", 100)
            prot_total = float(food.get("proteinas_g") or food.get("protein_per_100g", 0) or 0)
            carbs_total = float(food.get("carbohidratos_g") or food.get("carbs_per_100g", 0) or 0)
            fat_total = float(food.get("grasas_g") or food.get("fat_per_100g", 0) or 0)
            cantidad_g = max(int(cantidad_g), 1)  # Evitar división por 0
            
            # Calorías SIEMPRE calculadas por Python (Atwater)
            kcal_total = _atwater_kcal(prot_total, carbs_total, fat_total)
            
            # Convertir a valores POR 100g para NutritionalData
            factor = 100.0 / cantidad_g
            kcal_100 = round(kcal_total * factor, 1)
            prot_100 = round(prot_total * factor, 1)
            carbs_100 = round(carbs_total * factor, 1)
            fat_100 = round(fat_total * factor, 1)
            
            print(f"  ✅ {name}: {cantidad_g}g → {kcal_total} kcal (Atwater: P{prot_total}×4 + C{carbs_total}×4 + G{fat_total}×9)")
            print(f"     Per 100g: {kcal_100} kcal | {prot_100}g prot | {carbs_100}g carbs | {fat_100}g fat")
            
            normalized_foods.append({
                "name": name,
                "estimated_grams": cantidad_g,
                "calories_per_100g": kcal_100,
                "protein_per_100g": prot_100,
                "carbs_per_100g": carbs_100,
                "fat_per_100g": fat_100,
            })
        
        return {"foods": normalized_foods}
        
    except Exception as e:
        print(f"❌ Error Groq: {e}")
        return None


# ==========================================
# OPEN FOOD FACTS - BÚSQUEDA POR CÓDIGO DE BARRAS
# ==========================================

async def search_open_food_facts_by_barcode(barcode: str, image_bytes: Optional[bytes] = None) -> Optional[NutritionalData]:
    """
    Busca un alimento por código de barras en MÚLTIPLES APIs (fallback strategy).
    
    INTENTA (en orden de confiabilidad):
    1. Open Food Facts (gratuito, muchos datos nutricionales)
    2. EAN Search (gratuito, base de datos EAN europea)
    3. Barcode Lookup (gratuito, 500 req/día)
    4. UPC Database (gratuito, trial mode, cobertura USA)
    5. Código Base Online (alternativa)
    
    Returns:
        NutritionalData si se encuentra, None si no
    """
    from src.config import BARCODE_LOOKUP_API, UPC_DATABASE_API
    
    # INTENTO 1: Open Food Facts
    print(f"🔍 Intento 1: Buscando {barcode} en Open Food Facts...")
    result = await _search_off_barcode(barcode)
    if result:
        print(f"✅ Encontrado en Open Food Facts: {result.food_name}")
        return result
    
    # INTENTO 2: EAN Search (base de datos europea de EAN)
    print(f"🔍 Intento 2: Buscando en EAN Search...")
    result = await _search_ean_search(barcode)
    if result:
        print(f"✅ Encontrado en EAN Search: {result.food_name}")
        return result
    
    # INTENTO 3: Barcode Lookup
    print(f"🔍 Intento 3: Buscando en Barcode Lookup...")
    result = await _search_barcode_lookup(barcode)
    if result:
        print(f"✅ Encontrado en Barcode Lookup: {result.food_name}")
        return result
    
    # INTENTO 4: UPC Database
    print(f"🔍 Intento 4: Buscando en UPC Database...")
    result = await _search_upc_database(barcode)
    if result:
        print(f"✅ Encontrado en UPC Database: {result.food_name}")
        return result
    
    # INTENTO 5: Barcode Database (alternativa)
    print(f"🔍 Intento 5: Buscando en Barcode Database...")
    result = await _search_barcode_database(barcode)
    if result:
        print(f"✅ Encontrado en Barcode Database: {result.food_name}")
        return result
    
    print(f"⚠️ Código NO encontrado en BDs externas")
    print(f"❌ Código {barcode} no encontrado en ninguna base de datos")
    
    # FALLBACK: Si tenemos imagen, intentar extraer datos directo con Groq
    if image_bytes:
        print(f"🔍 FALLBACK: Analizando etiqueta nutricional con Groq...")
        result = await _analyze_nutrition_label_with_groq(image_bytes)
        if result:
            print(f"✅ Groq logró extraer datos de la etiqueta")
            return result
    
    return None


async def _search_off_barcode(barcode: str) -> Optional[NutritionalData]:
    """Open Food Facts - API principal."""
    try:
        url = f"{OFF_API_ENDPOINT}/{barcode}.json"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 404:
                    return None
                if resp.status != 200:
                    return None
                
                data = await resp.json()
        
        product = data.get("product", {})
        if not product:
            return None
        
        # ARREGLO: Extraer nutrientes con mejor parse
        nutrients = product.get("nutriments", {}) or product.get("nutrients", {})
        
        # Intentar múltiples keys para cada nutriente
        calories = (
            nutrients.get("energy-kcal_100g") or
            nutrients.get("energy_kcal_100g") or
            nutrients.get("energy-kcal") or
            nutrients.get("energy_100g", 0)
        )
        
        protein = (
            nutrients.get("proteins_100g") or
            nutrients.get("protein_100g") or
            nutrients.get("proteins") or 0
        )
        
        carbs = (
            nutrients.get("carbohydrates_100g") or
            nutrients.get("carbs_100g") or
            nutrients.get("carbohydrates") or 0
        )
        
        fat = (
            nutrients.get("fat_100g") or
            nutrients.get("fats_100g") or
            nutrients.get("fat") or 0
        )
        
        food_name = product.get("product_name", "Unknown (OFF)")
        
        # Validar que tenga al menos calorías
        if calories == 0 and not (protein or carbs or fat):
            return None
        
        return NutritionalData(
            food_name=food_name,
            calories_per_100g=float(calories),
            protein_per_100g=float(protein),
            carbs_per_100g=float(carbs),
            fat_per_100g=float(fat),
            source="open_food_facts"
        )
        
    except Exception as e:
        print(f"  ⚠️ OFF Error: {str(e)}")
        return None


async def _search_barcode_lookup(barcode: str) -> Optional[NutritionalData]:
    """Barcode Lookup - Alternativa con buena cobertura."""
    try:
        from src.config import BARCODE_LOOKUP_API
        
        url = BARCODE_LOOKUP_API
        params = {"barcode": barcode, "formatted": "json"}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return None
                
                data = await resp.json()
        
        # Barcode Lookup devuelve estructura diferente
        if not data.get("success"):
            return None
        
        products = data.get("products", [])
        if not products:
            return None
        
        product = products[0]
        food_name = product.get("name", product.get("title", "Unknown (Barcode Lookup)"))
        
        # Barcode Lookup no siempre tienen nutricionales, pero intentamos
        # Devolvemos con valores estimados si no hay datos
        calories = float(product.get("calories", 0)) or 100  # Default 100 kcal
        
        return NutritionalData(
            food_name=food_name,
            calories_per_100g=calories,
            protein_per_100g=float(product.get("protein", 0)) or 0,
            carbs_per_100g=float(product.get("carbohydrates", 0)) or 0,
            fat_per_100g=float(product.get("fat", 0)) or 0,
            source="barcode_lookup"
        )
        
    except Exception as e:
        print(f"  ⚠️ Barcode Lookup Error: {str(e)}")
        return None


async def _search_upc_database(barcode: str) -> Optional[NutritionalData]:
    """UPC Database - Trial API con buena cobertura USA."""
    try:
        from src.config import UPC_DATABASE_API
        
        url = UPC_DATABASE_API
        params = {"upc": barcode}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return None
                
                data = await resp.json()
        
        if data.get("code") != "OK":
            return None
        
        items = data.get("items", [])
        if not items:
            return None
        
        item = items[0]
        food_name = item.get("title", "Unknown (UPC DB)")
        
        return NutritionalData(
            food_name=food_name,
            calories_per_100g=100,  # UPC DB no tiene datos nutricionales
            protein_per_100g=0,
            carbs_per_100g=0,
            fat_per_100g=0,
            source="upc_database"
        )
        
    except Exception as e:
        print(f"  ⚠️ UPC Database Error: {str(e)}")
        return None


async def _search_ean_search(barcode: str) -> Optional[NutritionalData]:
    """EAN Search - Base de datos de códigos EAN europeos."""
    try:
        # EAN Search API: https://www.ean-search.org/
        url = f"https://api.ean-search.org/api?format=json&barcode={barcode}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return None
                
                data = await resp.json()
        
        if not data.get("barcode"):
            return None
        
        product_name = data.get("name", data.get("title", "Unknown (EAN Search)"))
        if not product_name:
            return None
        
        # EAN Search no siempre tiene datos nutricionales
        return NutritionalData(
            food_name=product_name,
            calories_per_100g=0,  # No disponible
            protein_per_100g=0,
            carbs_per_100g=0,
            fat_per_100g=0,
            source="ean_search"
        )
        
    except Exception as e:
        print(f"  ⚠️ EAN Search Error: {str(e)}")
        return None


async def _search_barcode_database(barcode: str) -> Optional[NutritionalData]:
    """Barcode Database - API alternativa con buena cobertura."""
    try:
        # Barcodes.online API: https://barcodes.online/
        url = f"https://api.barcodes.online/api/barcodes/{barcode}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status not in [200, 201]:
                    # Intentar alternativa
                    return await _search_barcode_monster(barcode)
                
                data = await resp.json()
        
        if not data:
            return await _search_barcode_monster(barcode)
        
        product_name = data.get("name", data.get("title", "Unknown (Barcode DB)"))
        if not product_name:
            return await _search_barcode_monster(barcode)
        
        return NutritionalData(
            food_name=product_name,
            calories_per_100g=0,
            protein_per_100g=0,
            carbs_per_100g=0,
            fat_per_100g=0,
            source="barcode_database"
        )
        
    except Exception as e:
        print(f"  ⚠️ Barcode Database Error: {str(e)}")
        return await _search_barcode_monster(barcode)


async def _search_barcode_monster(barcode: str) -> Optional[NutritionalData]:
    """Barcode Monster - Última alternativa."""
    try:
        # Barcode Monster API (sin autenticación requerida)
        url = f"https://api.barcode.monster/search"
        params = {"q": barcode}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return None
                
                data = await resp.json()
        
        if not data or not isinstance(data, list) or len(data) == 0:
            return None
        
        product = data[0]
        product_name = product.get("name", product.get("title", "Unknown (Barcode Monster)"))
        
        if not product_name:
            return None
        
        return NutritionalData(
            food_name=product_name,
            calories_per_100g=0,
            protein_per_100g=0,
            carbs_per_100g=0,
            fat_per_100g=0,
            source="barcode_monster"
        )
        
    except Exception as e:
        print(f"  ⚠️ Barcode Monster Error: {str(e)}")
        return None


# ==========================================
# GROQ IMAGE ANALYSIS - FALLBACK FOR UNKNOWN BARCODES
# ==========================================

async def _analyze_nutrition_label_with_groq(image_bytes: bytes) -> Optional[NutritionalData]:
    """
    Lee la etiqueta nutricional directamente de la imagen usando Groq con Llama 4 Scout.
    Usado cuando el código de barras no se encuentra en ninguna BD.
    
    ANTI-ALUCINACIÓN: Aunque leemos calorías de la etiqueta, VALIDAMOS
    contra Atwater. Si hay desviación >20%, usamos el cálculo de Python.
    """
    try:
        import base64
        from groq import AsyncGroq
        from src.config import GROQ_API_KEY
        
        groq_client = AsyncGroq(api_key=GROQ_API_KEY)
        image_data = base64.standard_b64encode(image_bytes).decode("utf-8")
        
        prompt = """Eres un nutricionista clínico. Analiza la etiqueta nutricional visible en esta imagen.

EXTRAE SOLO lo que puedas LEER en la etiqueta. Valores POR 100g:
- Nombre del producto
- Proteínas (g)
- Carbohidratos/Hidratos (g)
- Grasas (g)

Si ves calorías/energía en la etiqueta, inclúyelas también (en kcal).
Si está en kJ, convierte: 1 kcal = 4.184 kJ.
Si NO encuentras un valor, escribe "NO ENCONTRADO".
NO inventes números. Solo lo que se lee claramente.

Formato EXACTO:
Nombre: [nombre_producto]
Calorias: [valor o NO ENCONTRADO]
Proteinas: [valor]
Carbohidratos: [valor]
Grasas: [valor]"""
        
        print(f"📸 Analizando etiqueta con Groq Llama 4 Scout...")
        
        message = await groq_client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_data}",
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ],
                }
            ],
            temperature=0.1,
            max_tokens=500,
            top_p=1,
        )
        
        response_text = message.choices[0].message.content
        print(f"📸 Groq Label Response:\n{response_text}")
        
        # Parsear respuesta
        product_name = "Unknown (Groq Analysis)"
        calories_reported = 0
        protein = 0
        carbs = 0
        fat = 0
        
        def _extract_number(text: str) -> float:
            import re as _re
            match = _re.search(r'[\d]+[.,]?[\d]*', text)
            if match:
                return float(match.group().replace(',', '.'))
            return 0
        
        for line in response_text.split('\n'):
            line_lower = line.lower().strip()
            if not line_lower or line_lower.startswith('**') or line_lower.startswith('#'):
                continue
            
            if 'nombre:' in line_lower or 'nombre ' in line_lower:
                for separator in ['Nombre:', 'nombre:', 'NOMBRE:']:
                    if separator in line:
                        product_name = line.split(separator)[-1].strip().strip('*').strip()
                        break
            elif any(k in line_lower for k in ['caloria', 'caloría', 'energia', 'energía', 'energy', 'kcal']):
                val = _extract_number(line.split(':')[-1] if ':' in line else line)
                if val > 0:
                    calories_reported = val
            elif any(k in line_lower for k in ['proteina', 'proteína', 'protein']):
                val = _extract_number(line.split(':')[-1] if ':' in line else line)
                if val > 0:
                    protein = val
            elif any(k in line_lower for k in ['carbohidrato', 'hidrato', 'carbohydrate', 'carbs']):
                val = _extract_number(line.split(':')[-1] if ':' in line else line)
                if val > 0:
                    carbs = val
            elif any(k in line_lower for k in ['grasa', 'lipido', 'lípido', 'fat', 'grasas']):
                val = _extract_number(line.split(':')[-1] if ':' in line else line)
                if val > 0:
                    fat = val
        
        # Validar que al menos tengamos el nombre
        if product_name == "Unknown (Groq Analysis)":
            print(f"⚠️ No se pudo extraer nombre del producto")
            return None
        
        # ANTI-ALUCINACIÓN: Validar calorías contra Atwater
        # Si Groq reportó calorías, verificar coherencia con macros
        if calories_reported > 0 and (protein > 0 or carbs > 0 or fat > 0):
            calories_final = _validate_and_fix_calories(calories_reported, protein, carbs, fat)
        elif protein > 0 or carbs > 0 or fat > 0:
            # No reportó calorías → calcular con Atwater
            calories_final = _atwater_kcal(protein, carbs, fat)
            print(f"  📐 Calorías calculadas por Atwater: {calories_final} kcal/100g")
        else:
            calories_final = calories_reported
        
        print(f"✅ Etiqueta: {product_name} | {calories_final}kcal | {protein}g prot | {carbs}g carbs | {fat}g grasas")
        
        return NutritionalData(
            food_name=product_name,
            calories_per_100g=calories_final,
            protein_per_100g=protein,
            carbs_per_100g=carbs,
            fat_per_100g=fat,
            source="groq_image_analysis"
        )
        
    except Exception as e:
        print(f"  ⚠️ Groq Image Analysis Error: {str(e)}")
        return None


# ==========================================
# GROQ FOOD PLATE ANALYSIS - IDENTIFICAR PLATOS DE COMIDA
# ==========================================

async def analyze_food_plate_with_groq(image_bytes: bytes) -> Optional[NutritionalData]:
    """
    Analiza una foto de un plato de comida usando Groq con visión.
    Identifica ingredientes, estima tipo de comida. Calorías se calculan vía Atwater.
    
    ANTI-ALUCINACIÓN: Groq NO calcula calorías. Solo reporta macros por 100g.
    Python calcula kcal = (P×4) + (C×4) + (G×9).
    """
    try:
        import base64
        from groq import AsyncGroq
        from src.config import GROQ_API_KEY
        
        groq_client = AsyncGroq(api_key=GROQ_API_KEY)
        image_data = base64.standard_b64encode(image_bytes).decode("utf-8")
        
        prompt = """Eres un nutricionista clínico experto usando la base de datos USDA FoodData Central.

Analiza esta foto de comida. Identifica el plato y sus ingredientes principales.

REGLAS ESTRICTAS:
1. PROHIBIDO reportar calorías o kcal. NO incluyas ese campo.
2. Reporta SOLO proteínas, carbohidratos y grasas POR 100g del plato.
3. Usa valores realistas del USDA como referencia.
4. Si no puedes identificar la comida, responde "Nombre: No identificado".

Valores de referencia USDA por 100g (solo macros):
- Arroz blanco cocido: 2.7g prot, 28g carbs, 0.3g grasa
- Pasta cocida: 5g prot, 25g carbs, 1.1g grasa
- Pollo a la plancha: 31g prot, 0g carbs, 3.6g grasa
- Ensalada mixta: 1.5g prot, 3g carbs, 0.3g grasa
- Pizza: 11g prot, 33g carbs, 10g grasa
- Hamburguesa: 17g prot, 24g carbs, 14g grasa
- Tortilla española: 8g prot, 5g carbs, 8g grasa
- Lentejas guisadas: 9g prot, 16g carbs, 1.5g grasa
- Lasaña: 9g prot, 18g carbs, 7g grasa
- Macarrones con queso: 8g prot, 22g carbs, 8g grasa

Formato EXACTO (sin explicaciones, sin campo de calorías):
Nombre: [nombre descriptivo del plato]
Ingredientes: [lista separada por coma]
Proteinas: [valor numerico por 100g]
Carbohidratos: [valor numerico por 100g]
Grasas: [valor numerico por 100g]"""
        
        print(f"📸 Analizando plato de comida con Groq Llama 4 Scout...")
        
        message = await groq_client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_data}",
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ],
                }
            ],
            temperature=0.2,
            max_tokens=500,
            top_p=1,
        )
        
        response_text = message.choices[0].message.content
        print(f"📸 Groq Plate Analysis Response:\n{response_text}")
        
        # Parsear respuesta
        import re as _re
        
        product_name = "Plato no identificado"
        ingredients = ""
        protein = 0
        carbs = 0
        fat = 0
        
        def _extract_num(text: str) -> float:
            match = _re.search(r'[\d]+[.,]?[\d]*', text)
            if match:
                return float(match.group().replace(',', '.'))
            return 0
        
        for line in response_text.split('\n'):
            line_lower = line.lower().strip()
            if not line_lower or (line_lower.startswith('**') and line_lower.endswith('**')):
                continue
            
            if 'nombre:' in line_lower:
                for sep in ['Nombre:', 'nombre:', 'NOMBRE:']:
                    if sep in line:
                        product_name = line.split(sep)[-1].strip().strip('*').strip()
                        break
            elif 'ingrediente' in line_lower:
                for sep in ['Ingredientes:', 'ingredientes:', 'INGREDIENTES:']:
                    if sep in line:
                        ingredients = line.split(sep)[-1].strip().strip('*').strip()
                        break
            elif any(k in line_lower for k in ['proteina', 'proteína', 'protein']):
                val = _extract_num(line.split(':')[-1] if ':' in line else line)
                if val > 0:
                    protein = val
            elif any(k in line_lower for k in ['carbohidrato', 'hidrato', 'carbohydrate', 'carbs']):
                val = _extract_num(line.split(':')[-1] if ':' in line else line)
                if val > 0:
                    carbs = val
            elif any(k in line_lower for k in ['grasa', 'fat', 'lípido', 'lipido']):
                if 'saturad' not in line_lower:
                    val = _extract_num(line.split(':')[-1] if ':' in line else line)
                    if val > 0:
                        fat = val
        
        # Añadir ingredientes al nombre
        display_name = product_name
        if ingredients:
            display_name = f"{product_name} ({ingredients[:80]})"
        
        # CALORÍAS CALCULADAS POR PYTHON - NUNCA POR LA IA
        calories_per_100g = _atwater_kcal(protein, carbs, fat)
        
        print(f"✅ Plato: {display_name} | Atwater: {calories_per_100g}kcal/100g")
        print(f"   Macros/100g: P:{protein}g × 4 + C:{carbs}g × 4 + G:{fat}g × 9 = {calories_per_100g} kcal")
        
        if product_name == "Plato no identificado" and (protein == 0 and carbs == 0 and fat == 0):
            return None
        
        return NutritionalData(
            food_name=display_name,
            calories_per_100g=calories_per_100g,
            protein_per_100g=protein,
            carbs_per_100g=carbs,
            fat_per_100g=fat,
            source="groq_plate_analysis"
        )
        
    except Exception as e:
        print(f"  ⚠️ Groq Plate Analysis Error: {str(e)}")
        return None


# ==========================================
# OPEN FOOD FACTS - BÚSQUEDA POR NOMBRE
# ==========================================

async def search_open_food_facts_by_name(food_name: str) -> Optional[NutritionalData]:
    """
    Busca un alimento por nombre en Open Food Facts.
    
    FLUJO:
    1. Usuario/Gemini devuelve nombre de alimento (ej: "Arroz blanco")
    2. Buscamos en OFF usando su API de búsqueda
    3. Retornamos primer resultado
    
    Args:
        food_name: Nombre del alimento
        
    Returns:
        NutritionalData si se encuentra, None si no
    """
    try:
        url = f"{OFF_API_ENDPOINT}/search"
        params = {
            "q": food_name,
            "fields": "product_name,nutrients",
            "page": 1,
            "page_size": 1
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    return None
                
                data = await resp.json()
        
        products = data.get("products", [])
        if not products:
            return None
        
        product = products[0]
        nutrients = product.get("nutrients", {})
        
        calories = nutrients.get("energy_kcal_100g") or 0
        protein = nutrients.get("proteins_100g") or 0
        carbs = nutrients.get("carbohydrates_100g") or 0
        fat = nutrients.get("fat_100g") or 0
        
        food_name_result = product.get("product_name", food_name)
        
        return NutritionalData(
            food_name=food_name_result,
            calories_per_100g=float(calories),
            protein_per_100g=float(protein),
            carbs_per_100g=float(carbs),
            fat_per_100g=float(fat),
            source="off"
        )
        
    except Exception as e:
        print(f"Error buscando en OFF por nombre: {str(e)}")
        return None


# ==========================================
# USDA FoodData Central - FALLBACK FINAL
# ==========================================

async def search_usda_food_data(food_name: str) -> Optional[NutritionalData]:
    """
    Busca un alimento en USDA FoodData Central API (fallback final si OFF no encuentra).
    
    VENTAJAS:
    - Completamente GRATIS (sin límites)
    - Base de datos ENORME (400,000+ alimentos)
    - NO requiere autenticación
    - API stable y mantenida por el USDA
    
    API Flow:
    1. GET /api/v1/foods/search?query=...
    2. Retorna lista de alimentos con datos nutricionales
    3. Extrae valores por 100g
    
    Args:
        food_name: Nombre del alimento a buscar
        
    Returns:
        NutritionalData si se encuentra, None si no
    """
    
    try:
        url = USDA_API_ENDPOINT
        params = {
            "query": food_name,
            "pageSize": 1,
            # No requiere API Key (es público)
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    return None
                
                data = await resp.json()
        
        foods = data.get("foods", [])
        if not foods:
            return None
        
        # Usar el primer resultado
        food = foods[0]
        food_name_result = food.get("description", food_name).lower()
        
        # Extraer nutrientes
        # USDA devuelve "foodNutrients" como lista
        nutrients_list = food.get("foodNutrients", [])
        
        calories = 0
        protein = 0
        carbs = 0
        fat = 0
        
        # Buscar valores específicos en la lista
        for nutrient in nutrients_list:
            nutrient_name = nutrient.get("nutrient", {}).get("name", "").lower()
            value = nutrient.get("value", 0)
            
            # USDA proporciona valores por 100g por defecto
            if "energy" in nutrient_name and "kcal" in nutrient_name:
                calories = value
            elif "protein" in nutrient_name and "g" in nutrient_name:
                protein = value
            elif "carbohydrate" in nutrient_name:
                carbs = value
            elif "fat" in nutrient_name and "total" in nutrient_name:
                fat = value
        
        # Si no encontramos valores, retornar None
        if calories == 0 and protein == 0:
            return None
        
        return NutritionalData(
            food_name=food_name_result.title(),
            calories_per_100g=float(calories),
            protein_per_100g=float(protein),
            carbs_per_100g=float(carbs),
            fat_per_100g=float(fat),
            source="usda"
        )
        
    except Exception as e:
        print(f"Error en USDA FoodData: {str(e)}")
        return None


# ==========================================
# ORQUESTACIÓN - FALLBACK PATTERN
# ==========================================

async def get_nutrition_by_food_name(food_name: str) -> Optional[NutritionalData]:
    """
    Busca datos nutricionales con patrón FALLBACK.
    
    ORDEN DE INTENTO:
    1. Open Food Facts (más completa, base de datos comunitaria)
    2. USDA FoodData Central (fallback, base de datos oficial del USDA)
    3. None (no encontrado)
    
    Args:
        food_name: Nombre del alimento
        
    Returns:
        NutritionalData si se encuentra. Los datos pueden venir de OFF o USDA
    """
    
    # Intento 1: Open Food Facts
    result = await search_open_food_facts_by_name(food_name)
    if result:
        return result
    
    print(f"⏳ OFF no encontró '{food_name}', intentando USDA FoodData...")
    
    # Intento 2: USDA FoodData Central
    result = await search_usda_food_data(food_name)
    if result:
        return result
    
    print(f"❌ No se encontraron datos para '{food_name}'")
    return None


async def process_gemini_and_enrich(
    gemini_response: Dict
) -> List[Tuple[str, int, NutritionalData]]:
    """
    Enriquece respuesta de Groq con datos de APIs nutricionales.
    
    ANTI-ALUCINACIÓN:
    - Si Groq ya calculó kcal vía Atwater (nuevo formato), las usa directamente.
    - Si viene de APIs (OFF/USDA), valida kcal contra Atwater.
    - NUNCA confía en kcal crudas de una IA sin validar.
    """
    result = []
    foods = gemini_response.get("foods", [])
    
    if not foods:
        return result
    
    for food in foods:
        name = food.get("name") or food.get("alimento")
        if not name:
            continue
        
        estimated_grams = food.get("estimated_grams") or food.get("cantidad_g", 100)
        if estimated_grams <= 0:
            estimated_grams = 100
        
        nutrition = None
        
        # Opción 1: Usar datos ya normalizados de Groq (con Atwater aplicado)
        if all(k in food for k in ["calories_per_100g", "protein_per_100g", "carbs_per_100g", "fat_per_100g"]):
            try:
                cal_100 = float(food["calories_per_100g"])
                prot_100 = float(food["protein_per_100g"])
                carbs_100 = float(food["carbs_per_100g"])
                fat_100 = float(food["fat_per_100g"])
                
                # Validación Atwater final (seguridad extra)
                cal_100 = _validate_and_fix_calories(cal_100, prot_100, carbs_100, fat_100)
                
                nutrition = NutritionalData(
                    food_name=name,
                    calories_per_100g=cal_100,
                    protein_per_100g=prot_100,
                    carbs_per_100g=carbs_100,
                    fat_per_100g=fat_100,
                    source="groq_atwater"
                )
            except (ValueError, TypeError):
                pass
        
        # Opción 2: Buscar en APIs (Open Food Facts o USDA)
        if not nutrition:
            api_result = await get_nutrition_by_food_name(name)
            if api_result:
                # Validar kcal de APIs también contra Atwater
                api_result.calories_per_100g = _validate_and_fix_calories(
                    api_result.calories_per_100g,
                    api_result.protein_per_100g,
                    api_result.carbs_per_100g,
                    api_result.fat_per_100g
                )
                nutrition = api_result
        
        # Opción 3: Valores por defecto razonables (con Atwater)
        if not nutrition:
            default_prot = 10.0
            default_carbs = 20.0
            default_fat = 5.0
            nutrition = NutritionalData(
                food_name=name,
                calories_per_100g=_atwater_kcal(default_prot, default_carbs, default_fat),
                protein_per_100g=default_prot,
                carbs_per_100g=default_carbs,
                fat_per_100g=default_fat,
                source="default"
            )
        
        result.append((name, estimated_grams, nutrition))
    
    return result


# ==========================================
# VALIDACIÓN DE CÓDIGO DE BARRAS
# ==========================================

def is_valid_barcode(text: str) -> bool:
    """
    Determina si un texto es un código de barras EAN válido.
    
    CRITERIOS:
    - Solo dígitos
    - Entre 8 y 14 dígitos (rango EAN standard)
    - No es un número que se vea como descripción
    
    Args:
        text: Texto a validar
        
    Returns:
        True si parece un código de barras
    """
    
    # Solo debe contener dígitos
    if not text.isdigit():
        return False
    
    # Debe tener longitud típica de EAN
    if not (8 <= len(text) <= 14):
        return False
    
    # No debe comenzar por números que sean tipicamente descripciones
    # (Esta es una heurística, puede ajustarse)
    
    return True
