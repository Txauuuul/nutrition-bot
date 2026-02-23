#!/usr/bin/env python3
"""
Script de inicio rápido para el Asistente Nutricional.

Uso:
    python run.py

Este script:
1. Verifica que todas las dependencias estén instaladas
2. Verifica que el archivo .env existe
3. Valida las claves API
4. Inicializa la base de datos
5. Inicia el bot
"""

import sys
import os
import asyncio
from pathlib import Path

def check_python_version():
    """Verifica que se está usando Python 3.8+"""
    if sys.version_info < (3, 8):
        print("❌ ERROR: Python 3.8+ es requerido")
        print(f"   Tu versión: {sys.version}")
        sys.exit(1)
    print(f"✅ Python {sys.version.split()[0]}")


def check_env_file():
    """Verifica que existe el archivo .env"""
    env_path = Path(".env")
    env_example_path = Path(".env.example")
    
    if not env_path.exists():
        print("\n❌ ERROR: Archivo .env no encontrado")
        print("   Solución:")
        print("   1. Copia .env.example a .env:")
        print("      cp .env.example .env")
        print("   2. Edita .env y completa las claves")
        print("   3. Ejecuta nuevamente este script")
        sys.exit(1)
    
    print("✅ Archivo .env encontrado")
    
    # Verificar que tenga contenido
    with open(env_path) as f:
        content = f.read().strip()
        if not content:
            print("❌ ERROR: .env está vacío")
            sys.exit(1)


def check_dependencies():
    """Verifica que las dependencias estén instaladas"""
    required_packages = [
        "aiogram",
        "google.generativeai",
        "aiohttp",
        "aiosqlite",
        "dotenv",
        "PIL",
        "pydantic",
    ]
    
    missing = []
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)
    
    if missing:
        print(f"\n❌ ERROR: Faltan paquetes: {', '.join(missing)}")
        print("\n   Instala con:")
        print("   pip install -r requirements.txt")
        sys.exit(1)
    
    print("✅ Todas las dependencias instaladas")


def check_config():
    """Verifica que la configuración de config.py sea válida"""
    try:
        from src.config import (
            TELEGRAM_BOT_TOKEN,
            GROQ_API_KEY,
            DB_PATH,
        )
        
        if not TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN vacío")
        if not GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY vacío")
        
        print("✅ Configuración validada")
        print(f"   Bot token: {TELEGRAM_BOT_TOKEN[:20]}...")
        print(f"   DB path: {DB_PATH}")
        
    except Exception as e:
        print(f"❌ ERROR en configuración: {str(e)}")
        print("\n   Revisa tu archivo .env - verifica:")
        print("   - TELEGRAM_BOT_TOKEN está configurado")
        print("   - GROQ_API_KEY está configurado")
        print("   - No hay caracteres especiales en los valores")
        sys.exit(1)


def print_banner():
    """Muestra un banner bonito"""
    banner = """
╔════════════════════════════════════════════════════╗
║   🥗 ASISTENTE NUTRICIONAL DE TELEGRAM - v1.0    ║
║                                                    ║
║   Iniciando bot...                                ║
╚════════════════════════════════════════════════════╝
    """
    print(banner)


async def main():
    """Punto de entrada principal"""
    print_banner()
    
    print("\n📋 Verificando requisitos previos:\n")
    
    # 1. Verificar Python
    check_python_version()
    
    # 2. Verificar .env
    check_env_file()
    
    # 3. Verificar dependencias
    check_dependencies()
    
    # 4. Verificar configuración
    check_config()
    
    print("\n" + "="*50)
    print("✅ TODAS LAS VERIFICACIONES PASADAS")
    print("="*50)
    
    # 5. Importar y ejecutar el bot
    print("\n🤖 Iniciando bot...\n")
    
    try:
        from src.main import main as run_bot
        await run_bot()
    except KeyboardInterrupt:
        print("\n\n👋 Bot detenido por el usuario")
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        print("\nSolicita ayuda en el README.md")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
