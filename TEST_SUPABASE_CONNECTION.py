#!/usr/bin/env python3
"""
Script de diagnóstico para conexión a Supabase.
Ejecuta: python TEST_SUPABASE_CONNECTION.py
"""

import asyncio
import asyncpg
import os
import sys
import urllib.parse
import socket
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

print("=" * 70)
print("🔍 DIAGNÓSTICO DE CONEXIÓN A SUPABASE")
print("=" * 70)

# ========== PASO 1: VALIDAR DATABASE_URL ==========
print("\n1️⃣ VALIDACIÓN DE DATABASE_URL")
print("-" * 70)

if not DATABASE_URL:
    print("❌ DATABASE_URL no está configurado en .env")
    sys.exit(1)

print(f"✅ DATABASE_URL encontrado")

# Validar placeholders
if "your_password" in DATABASE_URL or "xxxxx" in DATABASE_URL:
    print("❌ DATABASE_URL contiene placeholders (your_password, xxxxx)")
    print("   Reemplaza con tus credenciales reales de Supabase")
    sys.exit(1)

if not DATABASE_URL.startswith("postgresql://"):
    print("❌ DATABASE_URL debe comenzar con 'postgresql://'")
    sys.exit(1)

print("✅ Formato de DATABASE_URL correcto")

# Parsear URL
try:
    parsed = urllib.parse.urlparse(DATABASE_URL)
    user = parsed.username
    password = parsed.password
    host = parsed.hostname
    port = parsed.port or 5432
    database = parsed.path[1:] if parsed.path else "postgres"
    
    print(f"\n📋 Detalles de conexión:")
    print(f"   Usuario: {user}")
    print(f"   Host: {host}")
    print(f"   Puerto: {port}")
    print(f"   Base de datos: {database}")
    print(f"   Password: {'*' * len(password) if password else 'SIN PASSWORD'}")
except Exception as e:
    print(f"❌ Error parseando DATABASE_URL: {e}")
    sys.exit(1)

# ========== PASO 2: CONECTIVIDAD DE RED ==========
print("\n2️⃣ CONECTIVIDAD DE RED")
print("-" * 70)

try:
    print(f"🔗 Intentando alcanzar {host}:{port}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    result = sock.connect_ex((host, port))
    sock.close()
    
    if result == 0:
        print(f"✅ Puerto {port} en {host} está accesible")
    else:
        print(f"❌ No se puede alcanzar {host}:{port}")
        print("   Posibles causas:")
        print("   • Firewall de red bloqueando")
        print("   • Supabase IP whitelist no configurado")
        print("   • Host o puerto incorrecto")
        sys.exit(1)
except Exception as e:
    print(f"⚠️ Error en diagnóstico de red: {e}")

# ========== PASO 3: CONECTAR A POSTGRESQL ==========
print("\n3️⃣ CONEXIÓN A POSTGRESQL")
print("-" * 70)

async def test_connection():
    try:
        print(f"🔐 Intentando conectar como {user}...")
        conn = await asyncpg.connect(DATABASE_URL, ssl='require')
        print("✅ Conexión establecida exitosamente")
        
        # ========== PASO 4: VERIFICAR TABLAS ==========
        print("\n4️⃣ VERIFICACIÓN DE TABLAS")
        print("-" * 70)
        
        # Listar tablas
        tables = await conn.fetch("""
            SELECT tablename FROM pg_tables 
            WHERE schemaname = 'public'
            ORDER BY tablename;
        """)
        
        if not tables:
            print("❌ No hay tablas en la base de datos PUBLIC")
            print("   Las tablas deberían ser: users, food_logs, saved_meals")
            print("\n✅ No hay problema - Se crearán automáticamente cuando inicie el bot")
        else:
            print(f"✅ Encontradas {len(tables)} tablas:")
            for table in tables:
                print(f"   • {table['tablename']}")
            
            # Verificar tablas específicas requeridas
            required_tables = {'users', 'food_logs', 'saved_meals'}
            existing_tables = {t['tablename'] for t in tables}
            missing = required_tables - existing_tables
            
            if missing:
                print(f"\n⚠️ Tablas faltantes: {', '.join(missing)}")
                print("   Se crearán automáticamente cuando inicie el bot")
            else:
                print("\n✅ Todas las tablas requeridas existen")
        
        # ========== PASO 5: PROBAR ESQUEMA ==========
        print("\n5️⃣ VERIFICACIÓN DEL ESQUEMA")
        print("-" * 70)
        
        if 'users' in [t['tablename'] for t in tables]:
            columns = await conn.fetch("""
                SELECT column_name, data_type FROM information_schema.columns
                WHERE table_name = 'users'
                ORDER BY ordinal_position;
            """)
            print("Estructura de tabla 'users':")
            for col in columns:
                print(f"  • {col['column_name']}: {col['data_type']}")
        
        await conn.close()
        print("\n" + "=" * 70)
        print("✅ DIAGNÓSTICO COMPLETADO - Todo parece estar bien")
        print("=" * 70)
        print("\nSiguientes pasos:")
        print("1. Haz push a GitHub: git push origin main")
        print("2. Redeploy en Render")
        print("3. El bot debería confeccionarse correctamente")
        
    except asyncpg.AuthenticationFailedError as e:
        print(f"❌ Autenticación fallida: {e}")
        print("   Verifica usuario y contraseña en DATABASE_URL")
        sys.exit(1)
    except asyncpg.InvalidCatalogNameError as e:
        print(f"❌ Base de datos no existe: {e}")
        print(f"   La base de datos '{database}' no existe en Supabase")
        print("   En Supabase, usa 'postgres' como base de datos")
        sys.exit(1)
    except asyncpg.Error as e:
        print(f"❌ Error de asyncpg: {type(e).__name__}: {e}")
        print("   Verifica que DATABASE_URL es correcto")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        sys.exit(1)

# Ejecutar test
try:
    asyncio.run(test_connection())
except KeyboardInterrupt:
    print("\n⏸️ Interrumpido por usuario")
    sys.exit(1)
