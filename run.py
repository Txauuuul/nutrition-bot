import asyncio
from src.main import main

if __name__ == "__main__":
    # Puente directo al código principal ignorando chequeos obsoletos
    asyncio.run(main())