# 🔧 Guía de Diagnóstico: Conexión a Supabase

## El Problema: `OSError: [Errno 101] Network is unreachable`

Este error significa que Render **no puede alcanzar los servidores de Supabase**. Puede ser por:

1. **IP Whitelist bloqueada** - Supabase por defecto solo acepta conexiones locales
2. **Placeholders en DATABASE_URL** - Aún tiene `your_password` o `xxxxx`
3. **URL malformada** - Caracteres especiales mal codificados
4. **Problema temporal** - Supabase o Render con issues

---

## 🧪 PASO 1: Testear Localmente

Ejecuta este script en tu computadora:

```bash
python TEST_SUPABASE_CONNECTION.py
```

Esto verifica:
- ✅ DATABASE_URL es válido
- ✅ Puede conectarse a Supabase
- ✅ Las tablas existen

**Si pasa todos los tests**: El problema es específico de Render (network/firewall)

---

## 🔐 PASO 2: Verificar IP Whitelist en Supabase

**Este es el problema más común.**

### En Supabase Dashboard:

1. **Ve a tu proyecto**
2. **Settings** (en la izquierda abajo)
3. **Database** → **Network**
4. Verifica el estado de "Restrict access to only IPv4 addresses matching a pattern":

#### Opción A: Permitir acceso desde cualquier lugar (Simple)
- Haz clic en el icono de editar
- Selecciona: **"Allow connections from anywhere"**
- Guarda cambios
- **Espera 30 segundos a que se aplique**

#### Opción B: Solo permitir Render (Más seguro)
- Necesitas la IP de Render (difícil de obtener, cambia)
- No recomendado para testing

**Recomendación**: Usa Opción A por ahora, luego restringe si lo necesitas

---

## 🔑 PASO 3: Verificar DATABASE_URL en Render

En tu dashboard de Render:

1. Ve a tu servicio
2. **Settings** → **Environment**
3. Verifica que DATABASE_URL tiene este formato EXACTO:
   ```
   postgresql://postgres:YOUR_PASSWORD@db.XXXXX.supabase.co:5432/postgres
   ```

**Importante**:
- ❌ NO debe tener `your_password`
- ❌ NO debe tener `xxxxx`
- ✅ Debe tener tu PASSWORD real
- ✅ Debe tener tu PROJECT_ID real
- ✅ Termina en `:5432/postgres`

### Cómo obtener la URL correcta:

1. Abre Supabase: https://app.supabase.com
2. Selecciona tu proyecto
3. **Settings** → **Database**
4. **Connection Strings** → Selecciona **URI**
5. Copia todo (desde `postgresql://` hasta `/postgres`)
6. Pégalo en Render como value de DATABASE_URL

---

## 🚨 PASO 4: Resolver Problemas Comunes

### Error: "No open ports detected"
- Significa que el bot se cerró sin escuchar puerto
- Normalmente es por error en DATABASE_URL
- Ejecuta TEST_SUPABASE_CONNECTION.py

### Error: "Network is unreachable" después de whitelist
- Espera 2-3 minutos más (Supabase tarda en aplicar)
- Intenta redeploy manual en Render

### Error: "Invalid password"
- El DATABASE_URL tiene caracteres especiales: `@`, `%`, `#`, `:` en password
- Si tu password tiene estos caracteres, URL-encódéalos:
  - `@` → `%40`
  - `:` → `%3A`
  - `%` → `%25`
  - `#` → `%23`

Ejemplo: Si password es `pass@123:abc`, en URL va: `pass%40123%3Aabc`

### Error: "Invalid Catalog Name"
- La base de datos no existe
- En Supabase, SIEMPRE usa `postgres` como base de datos
- DATABASE_URL debe terminar en `/postgres`

---

## ✅ Checklist Pre-Deploy

**En Supabase:**
- [ ] Proyecto creado en https://app.supabase.com
- [ ] Network settings: "Allow connections from anywhere" ACTIVADO
- [ ] DATABASE_URL copiado del Connection String → URI
- [ ] URL no contiene placeholders (`your_password`, `xxxxx`)

**En Render:**
- [ ] TELEGRAM_BOT_TOKEN configurado
- [ ] GROQ_API_KEY configurado
- [ ] DATABASE_URL configurado (valor REAL, no placeholder)
- [ ] Manual Deploy ejecutado después de cambios

**Localmente:**
- [ ] Ejecuté TEST_SUPABASE_CONNECTION.py
- [ ] Pasó todos los tests

---

## 🚀 Flujo de Deploy Definitivo

1. **Verifica test local**:
   ```bash
   python TEST_SUPABASE_CONNECTION.py
   ```
   
2. **Si pasa**:
   - Haz push a GitHub
   - Redeploy en Render

3. **Si falla**:
   - Lee el error específico
   - Aplica solución del checklist arriba
   - Intenta test de nuevo

---

## 📞 Información de Diagnóstico

Si aún falla, recopila esto:

**Ejecuta localmente**:
```bash
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
db_url = os.getenv('DATABASE_URL')
if db_url:
    print('DATABASE_URL encontrado')
    print('Primeros 50 caracteres:', db_url[:50])
    print('Host:', db_url.split('@')[1].split(':')[0] if '@' in db_url else 'ERROR')
else:
    print('DATABASE_URL NO ENCONTRADO')
"
```

**En Render logs** (durante error):
- Copia el mensaje de error completo
- Incluye línea donde comienza la traza

---

## 🎯 Resumen Visual

```
┌─────────────────────────────────────┐
│  Tu Bot en Render                   │
└────────────────┬────────────────────┘
                 │
                 ↓ DATABASE_URL = postgresql://...
         ¿Puede conectarse?
                 │
         ┌───────┴────────┐
         │                │
        NO               YES
         │                │
         ↓                ↓
  OSError 101      ✅ Conectado
   Network is        │
  unreachable    ┌───┴──────┐
                 │          │
         ¿IP    ↓          ↓
      Whitelist?  Crea   Conecta a
         SI     tablas  datos
         │       │        │
         ✅ ←───┴────────┘
         BOT FUNCIONA
```

---

## ¿Necesitas ayuda?

Después de ejecutar TEST_SUPABASE_CONNECTION.py, cuéntame:
1. ¿Qué test falló específicamente?
2. ¿Cuál fue el mensaje de error?
3. ¿Activaste "Allow connections from anywhere" en Supabase?

Así podré ayudarte a resolver el problema exacto.
