#!/usr/bin/env bash
# Actualizar el sistema e instalar la librería del sistema para pyzbar
apt-get update && apt-get install -y libzbar0
# Instalar las librerías de Python
pip install --upgrade pip
pip install -r requirements.txt