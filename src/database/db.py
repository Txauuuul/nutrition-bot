"""
Capa de acceso a la base de datos PostgreSQL (Supabase).

MIGRACIÓN DE SQLite A PostgreSQL:
- Anterior: aiosqlite (embebido, archivo local)
- Nuevo: asyncpg + PostgreSQL (servidor remoto, escalable)

CONCEPTOS CLAVE:
- Pool de conexiones: Reutiliza conexiones de forma eficiente
- Async/await con asyncpg para no bloquear el bot
- Lógica de "día lógico": 03:00:00 a 02:59:59 (no UTC estándar)
- Todas las funciones son asyncrónicas

POR QUÉ CADA TABLA:
1. users: Perfil del usuario (objetivos, preferencias)
2. saved_meals: Platos predefinidos reutilizables
3. food_logs: Registro de cada alimento consumido
4. daily_summaries: Caché de resúmenes (optimización - reservada)
"""

import asyncpg
from datetime import datetime, timedelta, time
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
import os

from src.config import LOGICAL_DAY_START_HOUR


# ==========================================
# MODELOS DE DATOS (dataclasses)
# ==========================================

@dataclass
class User:
    """Representa un usuario del bot."""
    user_id: int
    name: str
    daily_calorie_goal: int
    daily_protein_goal: int
    daily_carbs_goal: int
    daily_fat_goal: int
    created_at: str

@dataclass
class FoodLog:
    """Representa una entrada de alimento consumido."""
    log_id: int
    user_id: int
    food_name: str
    quantity_grams: int
    calories: int
    protein: int
    carbs: int
    fat: int
    timestamp: str
    barcode: Optional[str] = None

@dataclass
class SavedMeal:
    """Representa un plato guardado (reutilizable)."""
    meal_id: int
    user_id: int
    meal_name: str
    total_calories: int
    total_protein: int
    total_carbs: int
    total_fat: int
    created_at: str


# ==========================================
# FUNCIONES DE UTILIDAD - MANEJO DE FECHAS
# ==========================================

def get_logical_day_start(date: datetime = None) -> datetime:
    """
    Calcula el inicio del 'día lógico' (3:00 AM).
    
    LÓGICA:
    - Si ahora es 3:00 AM o después, el día lógico empezó hoy a las 3:00 AM
    - Si ahora es antes de 3:00 AM, el día lógico empezó AYER a las 3:00 AM
    
    Args:
        date: datetime para calcular (default: ahora)
        
    Returns:
        datetime del inicio del día lógico actual
    """
    if date is None:
        date = datetime.now()
    
    # Inicio del día lógico hoy
    start_of_logical_day = date.replace(
        hour=LOGICAL_DAY_START_HOUR,
        minute=0,
        second=0,
        microsecond=0
    )
    
    # Si ahora es ANTES de las 3:00 AM, el día lógico empezó ayer
    if date < start_of_logical_day:
        start_of_logical_day -= timedelta(days=1)
    
    return start_of_logical_day


def get_logical_day_end(date: datetime = None) -> datetime:
    """Calcula el final del 'día lógico' (2:59:59 AM del día siguiente)."""
    if date is None:
        date = datetime.now()
    
    start = get_logical_day_start(date)
    # El día lógico termina 23:59:59 después del inicio
    return start + timedelta(hours=24) - timedelta(seconds=1)


# ==========================================
# CLASE PRINCIPAL - DATABASE MANAGER
# ==========================================

class Database:
    """Gestor centralizado de PostgreSQL con pool de conexiones."""
    
    def __init__(self, database_url: str = None):
        """
        Inicializa el gestor de base de datos.
        
        Args:
            database_url: URL de conexión a PostgreSQL (usa env var DATABASE_URL si no se proporciona)
        """
        self.database_url = database_url or os.environ.get("DATABASE_URL")
        if not self.database_url:
            raise ValueError(
                "DATABASE_URL no configurada. "
                "Agrega DATABASE_URL a tu archivo .env"
            )
        self.pool: Optional[asyncpg.Pool] = None
    
    # ========== CONEXIÓN Y POOL ==========
    
    async def connect(self) -> None:
        """
        Crea el pool de conexiones a PostgreSQL.
        Se llama una sola vez al iniciar el bot.
        """
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=5,           # Mínimo 5 conexiones en reposo
                max_size=20,          # Máximo 20 conexiones simultáneas
                command_timeout=10,   # Timeout de comandos (segundos)
                ssl='require' if 'localhost' not in self.database_url else False  # SSL para producción
            )
            print("✅ Pool de conexiones PostgreSQL creado")
    
    async def close(self) -> None:
        """
        Cierra el pool de conexiones.
        Se llama al apagar el bot.
        """
        if self.pool:
            await self.pool.close()
            print("✅ Pool de conexiones cerrado")
    
    async def initialize(self) -> None:
        """
        Crea la base de datos y todas las tablas necesarias.
        Se llama una sola vez al iniciar el bot.
        """
        await self.connect()
        
        async with self.pool.acquire() as conn:
            # SQL para crear tablas con sintaxis PostgreSQL
            await conn.execute("""
                -- TABLA 1: USUARIOS
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    name TEXT NOT NULL,
                    daily_calorie_goal INTEGER DEFAULT 2500,
                    daily_protein_goal INTEGER DEFAULT 150,
                    daily_carbs_goal INTEGER DEFAULT 300,
                    daily_fat_goal INTEGER DEFAULT 80,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                -- TABLA 2: ALIMENTOS CONSUMIDOS (Log detallado)
                CREATE TABLE IF NOT EXISTS food_logs (
                    log_id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    food_name TEXT NOT NULL,
                    quantity_grams INTEGER NOT NULL,
                    calories INTEGER NOT NULL,
                    protein INTEGER NOT NULL,
                    carbs INTEGER NOT NULL,
                    fat INTEGER NOT NULL,
                    barcode TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(user_id)
                );
                
                -- TABLA 3: PLATOS GUARDADOS (Reutilizables)
                CREATE TABLE IF NOT EXISTS saved_meals (
                    meal_id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    meal_name TEXT NOT NULL,
                    total_calories INTEGER NOT NULL,
                    total_protein INTEGER NOT NULL,
                    total_carbs INTEGER NOT NULL,
                    total_fat INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_user_meal FOREIGN KEY (user_id) REFERENCES users(user_id),
                    CONSTRAINT unique_meal_name UNIQUE (user_id, meal_name)
                );
                
                -- ÍNDICES para optimizar búsquedas
                CREATE INDEX IF NOT EXISTS idx_food_logs_user_time 
                    ON food_logs(user_id, timestamp);
                CREATE INDEX IF NOT EXISTS idx_saved_meals_user 
                    ON saved_meals(user_id);
            """)
        
        print("✅ Base de datos PostgreSQL inicializada")

    # ========== USUARIOS ==========
    
    async def get_or_create_user(
        self,
        user_id: int,
        name: str = "Usuario"
    ) -> User:
        """
        Obtiene un usuario existente o lo crea si no existe.
        
        PATRÓN: Get-or-Create es común en bots (usuario nuevo se registra automáticamente)
        """
        async with self.pool.acquire() as conn:
            # Intentar obtener
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE user_id = $1",
                user_id
            )
            
            if row:
                return User(
                    user_id=row['user_id'],
                    name=row['name'],
                    daily_calorie_goal=row['daily_calorie_goal'],
                    daily_protein_goal=row['daily_protein_goal'],
                    daily_carbs_goal=row['daily_carbs_goal'],
                    daily_fat_goal=row['daily_fat_goal'],
                    created_at=str(row['created_at'])
                )
            
            # Si no existe, crear
            await conn.execute(
                """
                INSERT INTO users
                (user_id, name, daily_calorie_goal, daily_protein_goal, daily_carbs_goal, daily_fat_goal)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                user_id, name, 2500, 150, 300, 80
            )
            
            # Retornar el usuario creado
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE user_id = $1",
                user_id
            )
            return User(
                user_id=row['user_id'],
                name=row['name'],
                daily_calorie_goal=row['daily_calorie_goal'],
                daily_protein_goal=row['daily_protein_goal'],
                daily_carbs_goal=row['daily_carbs_goal'],
                daily_fat_goal=row['daily_fat_goal'],
                created_at=str(row['created_at'])
            )
    
    async def update_user_goals(
        self,
        user_id: int,
        daily_calorie_goal: int,
        daily_protein_goal: int,
        daily_carbs_goal: int,
        daily_fat_goal: int
    ) -> None:
        """Actualiza los objetivos nutricionales del usuario."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE users
                SET daily_calorie_goal = $1,
                    daily_protein_goal = $2,
                    daily_carbs_goal = $3,
                    daily_fat_goal = $4
                WHERE user_id = $5
                """,
                daily_calorie_goal, daily_protein_goal, daily_carbs_goal,
                daily_fat_goal, user_id
            )

    # ========== REGISTRO DE ALIMENTOS ==========
    
    async def log_food(
        self,
        user_id: int,
        food_name: str,
        quantity_grams: int,
        calories: int,
        protein: int,
        carbs: int,
        fat: int,
        barcode: Optional[str] = None
    ) -> int:
        """
        Registra un alimento consumido en la BD.
        
        Args:
            user_id: ID del usuario
            food_name: Nombre del alimento (ej: "Arroz blanco")
            quantity_grams: Cantidad en gramos
            calories: Calorías totales
            protein: Proteína en gramos
            carbs: Carbohidratos en gramos
            fat: Grasas en gramos
            barcode: Código de barras si aplica
            
        Returns:
            ID del registro creado
        """
        async with self.pool.acquire() as conn:
            log_id = await conn.fetchval(
                """
                INSERT INTO food_logs
                (user_id, food_name, quantity_grams, calories, protein, carbs, fat, barcode)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING log_id
                """,
                user_id, food_name, quantity_grams, calories, protein, carbs, fat, barcode
            )
            return log_id
    
    async def get_today_totals(self, user_id: int) -> Dict[str, int]:
        """
        Obtiene el total de macros del 'día lógico' actual (desde 3:00 AM).
        
        EXPLICACIÓN DE LA LÓGICA:
        1. Calcula el inicio y fin del día lógico actual
        2. Suma TODOS los alimentos registrados entre esos tiempos
        3. Retorna totales: calorías, proteína, carbos, grasa
        """
        async with self.pool.acquire() as conn:
            # Obtener los límites del día lógico
            day_start = get_logical_day_start()
            day_end = get_logical_day_end()
            
            row = await conn.fetchrow(
                """
                SELECT
                    SUM(calories)::INTEGER as total_calories,
                    SUM(protein)::INTEGER as total_protein,
                    SUM(carbs)::INTEGER as total_carbs,
                    SUM(fat)::INTEGER as total_fat,
                    COUNT(*)::INTEGER as food_count
                FROM food_logs
                WHERE user_id = $1
                  AND timestamp >= $2
                  AND timestamp < $3
                """,
                user_id, day_start, day_end
            )
            
            if not row or row['total_calories'] is None:
                # Sin datos aún hoy
                return {
                    "total_calories": 0,
                    "total_protein": 0,
                    "total_carbs": 0,
                    "total_fat": 0,
                    "food_count": 0
                }
            
            return {
                "total_calories": row['total_calories'] or 0,
                "total_protein": row['total_protein'] or 0,
                "total_carbs": row['total_carbs'] or 0,
                "total_fat": row['total_fat'] or 0,
                "food_count": row['food_count'] or 0
            }
    
    async def get_day_history(
        self,
        user_id: int,
        date: datetime
    ) -> Tuple[Dict[str, int], List[FoodLog]]:
        """
        Obtiene el resumen y lista detallada de consumo de un día específico.
        
        Args:
            user_id: ID del usuario
            date: Fecha a consultar (se normaliza a día lógico)
            
        Returns:
            Tupla (resumen, lista_de_alimentos)
        """
        async with self.pool.acquire() as conn:
            # Calcular límites del día lógico para la fecha
            day_start = get_logical_day_start(date)
            day_end = get_logical_day_end(date)
            
            # Obtener resumen
            summary_row = await conn.fetchrow(
                """
                SELECT
                    SUM(calories)::INTEGER as total_calories,
                    SUM(protein)::INTEGER as total_protein,
                    SUM(carbs)::INTEGER as total_carbs,
                    SUM(fat)::INTEGER as total_fat,
                    COUNT(*)::INTEGER as food_count
                FROM food_logs
                WHERE user_id = $1
                  AND timestamp >= $2
                  AND timestamp < $3
                """,
                user_id, day_start, day_end
            )
            
            summary = {}
            if summary_row and summary_row['total_calories'] is not None:
                summary = {
                    "total_calories": summary_row['total_calories'] or 0,
                    "total_protein": summary_row['total_protein'] or 0,
                    "total_carbs": summary_row['total_carbs'] or 0,
                    "total_fat": summary_row['total_fat'] or 0,
                    "food_count": summary_row['food_count'] or 0
                }
            else:
                summary = {
                    "total_calories": 0,
                    "total_protein": 0,
                    "total_carbs": 0,
                    "total_fat": 0,
                    "food_count": 0
                }
            
            # Obtener lista detallada (ordenada por tiempo)
            rows = await conn.fetch(
                """
                SELECT * FROM food_logs
                WHERE user_id = $1
                  AND timestamp >= $2
                  AND timestamp < $3
                ORDER BY timestamp DESC
                """,
                user_id, day_start, day_end
            )
            
            food_logs = [
                FoodLog(
                    log_id=row['log_id'],
                    user_id=row['user_id'],
                    food_name=row['food_name'],
                    quantity_grams=row['quantity_grams'],
                    calories=row['calories'],
                    protein=row['protein'],
                    carbs=row['carbs'],
                    fat=row['fat'],
                    timestamp=str(row['timestamp']),
                    barcode=row['barcode']
                )
                for row in rows
            ]
            
            return summary, food_logs
    
    async def delete_last_entry(self, user_id: int) -> bool:
        """
        Elimina la última entrada registrada del usuario.
        
        Returns:
            True si se eliminó algo, False si no hay entrada para eliminar
        """
        async with self.pool.acquire() as conn:
            # Obtener la entrada más reciente
            row = await conn.fetchrow(
                """
                SELECT log_id FROM food_logs
                WHERE user_id = $1
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                user_id
            )
            
            if not row:
                return False
            
            log_id = row['log_id']
            deleted = await conn.execute(
                "DELETE FROM food_logs WHERE log_id = $1",
                log_id
            )
            return deleted != "DELETE 0"

    # ========== PLATOS GUARDADOS ==========
    
    async def save_meal(
        self,
        user_id: int,
        meal_name: str,
        total_calories: int,
        total_protein: int,
        total_carbs: int,
        total_fat: int
    ) -> int:
        """
        Guarda un plato nuevo basado en la última comida.
        
        NOTA: Usa UNIQUE constraint para evitar duplicados de nombre
        """
        try:
            async with self.pool.acquire() as conn:
                meal_id = await conn.fetchval(
                    """
                    INSERT INTO saved_meals
                    (user_id, meal_name, total_calories, total_protein, total_carbs, total_fat)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING meal_id
                    """,
                    user_id, meal_name, total_calories, total_protein, total_carbs, total_fat
                )
                return meal_id
        except asyncpg.UniqueViolationError:
            # Ya existe un plato con ese nombre
            return -1
    
    async def get_saved_meal(self, user_id: int, meal_name: str) -> Optional[SavedMeal]:
        """Obtiene un plato guardado por nombre."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM saved_meals WHERE user_id = $1 AND meal_name = $2",
                user_id, meal_name
            )
            if not row:
                return None
            
            return SavedMeal(
                meal_id=row['meal_id'],
                user_id=row['user_id'],
                meal_name=row['meal_name'],
                total_calories=row['total_calories'],
                total_protein=row['total_protein'],
                total_carbs=row['total_carbs'],
                total_fat=row['total_fat'],
                created_at=str(row['created_at'])
            )
    
    async def list_saved_meals(self, user_id: int) -> List[SavedMeal]:
        """Lista todos los platos guardados del usuario."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM saved_meals WHERE user_id = $1 ORDER BY meal_name",
                user_id
            )
            return [
                SavedMeal(
                    meal_id=row['meal_id'],
                    user_id=row['user_id'],
                    meal_name=row['meal_name'],
                    total_calories=row['total_calories'],
                    total_protein=row['total_protein'],
                    total_carbs=row['total_carbs'],
                    total_fat=row['total_fat'],
                    created_at=str(row['created_at'])
                )
                for row in rows
            ]
    
    async def delete_saved_meal(self, user_id: int, meal_name: str) -> bool:
        """Elimina un plato guardado."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM saved_meals WHERE user_id = $1 AND meal_name = $2",
                user_id, meal_name
            )
            return result != "DELETE 0"


# ==========================================
# INSTANCIA GLOBAL
# ==========================================

db = Database()



# ==========================================
# MODELOS DE DATOS (dataclasses)
# ==========================================

@dataclass
class User:
    """Representa un usuario del bot."""
    user_id: int
    name: str
    daily_calorie_goal: int
    daily_protein_goal: int
    daily_carbs_goal: int
    daily_fat_goal: int
    created_at: str

@dataclass
class FoodLog:
    """Representa una entrada de alimento consumido."""
    log_id: int
    user_id: int
    food_name: str
    quantity_grams: int
    calories: int
    protein: int
    carbs: int
    fat: int
    timestamp: str
    barcode: Optional[str] = None

@dataclass
class SavedMeal:
    """Representa un plato guardado (reutilizable)."""
    meal_id: int
    user_id: int
    meal_name: str
    total_calories: int
    total_protein: int
    total_carbs: int
    total_fat: int
    created_at: str


# ==========================================
# FUNCIONES DE UTILIDAD - MANEJO DE FECHAS
# ==========================================

def get_logical_day_start(date: datetime = None) -> datetime:
    """
    Calcula el inicio del 'día lógico' (3:00 AM).
    
    LÓGICA:
    - Si ahora es 3:00 AM o después, el día lógico empezó hoy a las 3:00 AM
    - Si ahora es antes de 3:00 AM, el día lógico empezó AYER a las 3:00 AM
    
    Args:
        date: datetime para calcular (default: ahora)
        
    Returns:
        datetime del inicio del día lógico actual
    """
    if date is None:
        date = datetime.now()
    
    # Inicio del día lógico hoy
    start_of_logical_day = date.replace(
        hour=LOGICAL_DAY_START_HOUR,
        minute=0,
        second=0,
        microsecond=0
    )
    
    # Si ahora es ANTES de las 3:00 AM, el día lógico empezó ayer
    if date < start_of_logical_day:
        start_of_logical_day -= timedelta(days=1)
    
    return start_of_logical_day


def get_logical_day_end(date: datetime = None) -> datetime:
    """Calcula el final del 'día lógico' (2:59:59 AM del día siguiente)."""
    if date is None:
        date = datetime.now()
    
    start = get_logical_day_start(date)
    # El día lógico termina 23:59:59 después del inicio
    return start + timedelta(hours=24) - timedelta(seconds=1)


# ==========================================
# CLASE PRINCIPAL - DATABASE MANAGER
# ==========================================

class Database:
    """Gestor centralizado de la base de datos SQLite."""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
    
    # ========== CONEXIÓN Y INICIALIZACIÓN ==========
    
    async def initialize(self) -> None:
        """
        Crea la base de datos y todas las tablas necesarias.
        Se llama una sola vez al iniciar el bot.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript("""
                -- TABLA 1: USUARIOS
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    daily_calorie_goal INTEGER DEFAULT 2500,
                    daily_protein_goal INTEGER DEFAULT 150,
                    daily_carbs_goal INTEGER DEFAULT 300,
                    daily_fat_goal INTEGER DEFAULT 80,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                -- TABLA 2: ALIMENTOS CONSUMIDOS (Log detallado)
                CREATE TABLE IF NOT EXISTS food_logs (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    food_name TEXT NOT NULL,
                    quantity_grams INTEGER NOT NULL,
                    calories INTEGER NOT NULL,
                    protein INTEGER NOT NULL,
                    carbs INTEGER NOT NULL,
                    fat INTEGER NOT NULL,
                    barcode TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );
                
                -- TABLA 3: PLATOS GUARDADOS (Reutilizables)
                CREATE TABLE IF NOT EXISTS saved_meals (
                    meal_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    meal_name TEXT NOT NULL,
                    total_calories INTEGER NOT NULL,
                    total_protein INTEGER NOT NULL,
                    total_carbs INTEGER NOT NULL,
                    total_fat INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, meal_name),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );
                
                -- ÍNDICES para optimizar búsquedas
                CREATE INDEX IF NOT EXISTS idx_food_logs_user_time 
                    ON food_logs(user_id, timestamp);
                CREATE INDEX IF NOT EXISTS idx_saved_meals_user 
                    ON saved_meals(user_id);
            """)
            await db.commit()

    # ========== USUARIOS ==========
    
    async def get_or_create_user(
        self,
        user_id: int,
        name: str = "Usuario"
    ) -> User:
        """
        Obtiene un usuario existente o lo crea si no existe.
        
        PATRÓN: Get-or-Create es común en bots (usuario nuevo se registra automáticamente)
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Intentar obtener
            cursor = await db.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            
            if row:
                return User(*row)
            
            # Si no existe, crear
            await db.execute(
                """
                INSERT INTO users
                (user_id, name, daily_calorie_goal, daily_protein_goal, daily_carbs_goal, daily_fat_goal)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, name, 2500, 150, 300, 80)
            )
            await db.commit()
            
            # Retornar el usuario creado
            cursor = await db.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            return User(*row)
    
    async def update_user_goals(
        self,
        user_id: int,
        daily_calorie_goal: int,
        daily_protein_goal: int,
        daily_carbs_goal: int,
        daily_fat_goal: int
    ) -> None:
        """Actualiza los objetivos nutricionales del usuario."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE users
                SET daily_calorie_goal = ?,
                    daily_protein_goal = ?,
                    daily_carbs_goal = ?,
                    daily_fat_goal = ?
                WHERE user_id = ?
                """,
                (daily_calorie_goal, daily_protein_goal, daily_carbs_goal,
                 daily_fat_goal, user_id)
            )
            await db.commit()

    # ========== REGISTRO DE ALIMENTOS ==========
    
    async def log_food(
        self,
        user_id: int,
        food_name: str,
        quantity_grams: int,
        calories: int,
        protein: int,
        carbs: int,
        fat: int,
        barcode: Optional[str] = None
    ) -> int:
        """
        Registra un alimento consumido en la BD.
        
        Args:
            user_id: ID del usuario
            food_name: Nombre del alimento (ej: "Arroz blanco")
            quantity_grams: Cantidad en gramos
            calories: Calorías totales
            protein: Proteína en gramos
            carbs: Carbohidratos en gramos
            fat: Grasas en gramos
            barcode: Código de barras si aplica
            
        Returns:
            ID del registro creado
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO food_logs
                (user_id, food_name, quantity_grams, calories, protein, carbs, fat, barcode)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, food_name, quantity_grams, calories, protein, carbs, fat, barcode)
            )
            await db.commit()
            return cursor.lastrowid
    
    async def get_today_totals(self, user_id: int) -> Dict[str, int]:
        """
        Obtiene el total de macros del 'día lógico' actual (desde 3:00 AM).
        
        EXPLICACIÓN DE LA LÓGICA:
        1. Calcula el inicio y fin del día lógico actual
        2. Suma TODOS los alimentos registrados entre esos tiempos
        3. Retorna totales: calorías, proteína, carbos, grasa
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Obtener los límites del día lógico
            day_start = get_logical_day_start()
            day_end = get_logical_day_end()
            
            # IMPORTANTE: Usar strftime para formatear con espacio (no isoformat con T)
            # SQLite CURRENT_TIMESTAMP usa "YYYY-MM-DD HH:MM:SS" (con espacio)
            # Si usamos isoformat() devuelve "YYYY-MM-DDTHH:MM:SS" (con T) que no coincide
            day_start_str = day_start.strftime("%Y-%m-%d %H:%M:%S")
            day_end_str = day_end.strftime("%Y-%m-%d %H:%M:%S")
            
            cursor = await db.execute(
                """
                SELECT
                    SUM(calories) as total_calories,
                    SUM(protein) as total_protein,
                    SUM(carbs) as total_carbs,
                    SUM(fat) as total_fat,
                    COUNT(*) as food_count
                FROM food_logs
                WHERE user_id = ?
                  AND timestamp >= ?
                  AND timestamp < ?
                """,
                (user_id, day_start_str, day_end_str)
            )
            row = await cursor.fetchone()
            
            if not row or row[0] is None:
                # Sin datos aún hoy
                return {
                    "total_calories": 0,
                    "total_protein": 0,
                    "total_carbs": 0,
                    "total_fat": 0,
                    "food_count": 0
                }
            
            return {
                "total_calories": int(row[0]),
                "total_protein": int(row[1]),
                "total_carbs": int(row[2]),
                "total_fat": int(row[3]),
                "food_count": int(row[4])
            }
    
    async def get_day_history(
        self,
        user_id: int,
        date: datetime
    ) -> Tuple[Dict[str, int], List[FoodLog]]:
        """
        Obtiene el resumen y lista detallada de consumo de un día específico.
        
        Args:
            user_id: ID del usuario
            date: Fecha a consultar (se normaliza a día lógico)
            
        Returns:
            Tupla (resumen, lista_de_alimentos)
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Calcular límites del día lógico para la fecha
            day_start = get_logical_day_start(date)
            day_end = get_logical_day_end(date)
            
            # Formatear con strftime para coincidencia con CURRENT_TIMESTAMP de SQLite
            day_start_str = day_start.strftime("%Y-%m-%d %H:%M:%S")
            day_end_str = day_end.strftime("%Y-%m-%d %H:%M:%S")
            
            # Obtener resumen
            cursor = await db.execute(
                """
                SELECT
                    SUM(calories) as total_calories,
                    SUM(protein) as total_protein,
                    SUM(carbs) as total_carbs,
                    SUM(fat) as total_fat,
                    COUNT(*) as food_count
                FROM food_logs
                WHERE user_id = ?
                  AND timestamp >= ?
                  AND timestamp < ?
                """,
                (user_id, day_start_str, day_end_str)
            )
            summary_row = await cursor.fetchone()
            
            summary = {}
            if summary_row and summary_row[0] is not None:
                summary = {
                    "total_calories": int(summary_row[0]),
                    "total_protein": int(summary_row[1]),
                    "total_carbs": int(summary_row[2]),
                    "total_fat": int(summary_row[3]),
                    "food_count": int(summary_row[4])
                }
            else:
                summary = {
                    "total_calories": 0,
                    "total_protein": 0,
                    "total_carbs": 0,
                    "total_fat": 0,
                    "food_count": 0
                }
            
            # Obtener lista detallada (ordenada por tiempo)
            cursor = await db.execute(
                """
                SELECT * FROM food_logs
                WHERE user_id = ?
                  AND timestamp >= ?
                  AND timestamp < ?
                ORDER BY timestamp DESC
                """,
                (user_id, day_start_str, day_end_str)
            )
            rows = await cursor.fetchall()
            
            food_logs = [FoodLog(*row) for row in rows]
            
            return summary, food_logs
    
    async def delete_last_entry(self, user_id: int) -> bool:
        """
        Elimina la última entrada registrada del usuario.
        
        Returns:
            True si se eliminó algo, False si no hay entrada para eliminar
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Obtener la entrada más reciente
            cursor = await db.execute(
                """
                SELECT log_id FROM food_logs
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (user_id,)
            )
            row = await cursor.fetchone()
            
            if not row:
                return False
            
            log_id = row[0]
            await db.execute(
                "DELETE FROM food_logs WHERE log_id = ?",
                (log_id,)
            )
            await db.commit()
            return True

    # ========== PLATOS GUARDADOS ==========
    
    async def save_meal(
        self,
        user_id: int,
        meal_name: str,
        total_calories: int,
        total_protein: int,
        total_carbs: int,
        total_fat: int
    ) -> int:
        """
        Guarda un plato nuevo basado en la última comida.
        
        NOTA: Usa UNIQUE constraint para evitar duplicados de nombre
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    """
                    INSERT INTO saved_meals
                    (user_id, meal_name, total_calories, total_protein, total_carbs, total_fat)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, meal_name, total_calories, total_protein, total_carbs, total_fat)
                )
                await db.commit()
                return cursor.lastrowid
        except sqlite3.IntegrityError:
            # Ya existe un plato con ese nombre
            return -1
    
    async def get_saved_meal(self, user_id: int, meal_name: str) -> Optional[SavedMeal]:
        """Obtiene un plato guardado por nombre."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM saved_meals WHERE user_id = ? AND meal_name = ?",
                (user_id, meal_name)
            )
            row = await cursor.fetchone()
            return SavedMeal(*row) if row else None
    
    async def list_saved_meals(self, user_id: int) -> List[SavedMeal]:
        """Lista todos los platos guardados del usuario."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM saved_meals WHERE user_id = ? ORDER BY meal_name",
                (user_id,)
            )
            rows = await cursor.fetchall()
            return [SavedMeal(*row) for row in rows]
    
    async def delete_saved_meal(self, user_id: int, meal_name: str) -> bool:
        """Elimina un plato guardado."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM saved_meals WHERE user_id = ? AND meal_name = ?",
                (user_id, meal_name)
            )
            await db.commit()
            return cursor.rowcount > 0


# ==========================================
# INSTANCIA GLOBAL
# ==========================================

db = Database()
