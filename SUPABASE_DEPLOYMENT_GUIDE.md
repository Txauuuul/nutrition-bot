# PostgreSQL Migration & Supabase Setup Guide

## Complete Step-by-Step Guide

This guide covers the complete migration from SQLite to PostgreSQL with Supabase and deployment on Render.

---

## Part 1: Database Migration Overview

### What Changed?

| Component | Before (SQLite) | After (PostgreSQL) |
|-----------|-----------------|-------------------|
| **Storage** | File: `data/nutrition_bot.db` | Cloud: Supabase (persistent) |
| **Driver** | `aiosqlite` | `asyncpg` |
| **Persistence** | ❌ Lost on Render redeploy | ✅ Survives redeploys |
| **Scalability** | Single server | AWS-backed Supabase |
| **Backups** | Manual | Automatic daily |
| **Connection** | Direct file access | TCP to Supabase server |

### Why This Change?

**Problem with SQLite on Render:**
```
Render uses ephemeral filesystem
  ↓
Every deploy → New container → Old data deleted
  ↓
Every redeploy loses all food logs!
```

**Solution with PostgreSQL:**
```
Supabase = Remote PostgreSQL instance
  ↓
Data lives on Supabase servers (not local filesystem)
  ↓
Every redeploy → New container → Data still on Supabase ✅
```

---

## Part 2: Files Changed

### ✅ Complete List of Modifications

1. **src/database/db.py** (~1000 lines changed)
   - SQLite3 API → asyncpg API
   - Direct file connections → Connection pool
   - SQL dialect updated (`:?` → `$1/$2/$3` parameters)
   - Row access updated (tuple indexing → named fields)

2. **requirements.txt**
   - ❌ Removed: `aiosqlite`
   - ✅ Added: `asyncpg`

3. **src/config.py**
   - ❌ Removed: `DB_PATH`, `DATA_DIR`
   - ✅ Added: `DATABASE_URL` validation

4. **.env**
   - ❌ Removed: `DB_PATH=data/nutrition_bot.db`
   - ✅ Added: `DATABASE_URL=postgresql://...`

5. **.env.example**
   - Updated example with PostgreSQL URL format

6. **src/main.py** (minimal change)
   - Added: `await db.close()` in finally block for graceful shutdown
   - Reason: Properly close connection pool when bot stops

---

## Part 3: Setting Up Supabase

### Step 1: Create Supabase Account

1. Go to https://supabase.com
2. Click "Sign Up"
3. Use GitHub account or email
4. Verify email

### Step 2: Create New Project

1. Dashboard → "New Project"
2. **Name**: `nutrition-bot` or similar
3. **Password**: Create strong password (you'll need for later)
4. **Region**: Choose closest to your user base (e.g., EU, US-East)
5. Click "Create new project"
6. Wait ~2 minutes for creation

### Step 3: Get Database URL

1. Left sidebar → "Project Settings" → "Database"
2. Look for "Connection string" section
3. Select "URI" tab
4. Copy the connection string (looks like):
   ```
   postgresql://postgres:XXXXXXXXXXXXXX@db.XXXXX.supabase.co:5432/postgres
   ```

### Step 4: Update .env File

In your workspace, update `.env`:

```bash
# Before
DB_PATH=data/nutrition_bot.db

# After
DATABASE_URL=postgresql://postgres:your_password@db.xxxxx.supabase.co:5432/postgres
```

**Replace:**
- `your_password` with the password you set in Step 2
- `xxxxx` with your project ID (from the Supabase URL)

### Step 5: Verify Connection Locally

Run this test script:

```python
import asyncio
import os
from src.database.db import db

async def test():
    try:
        await db.initialize()
        print("✅ Connected to Supabase successfully!")
        print(f"Pool size: {db.pool.get_size()}")
        print(f"Idle connections: {db.pool.get_idle_size()}")
        await db.close()
    except Exception as e:
        print(f"❌ Connection failed: {e}")

asyncio.run(test())
```

**Expected output:**
```
✅ Connected to Supabase successfully!
Pool size: 5
Idle connections: 5
```

---

## Part 4: Deploying to Render

### Step 1: Push Code to GitHub

```bash
git add -A
git commit -m "Migrate SQLite to PostgreSQL with Supabase"
git push origin main
```

### Step 2: Connect to Render

1. Go to https://render.com
2. Login with GitHub
3. Click "New +"  → "Web Service"
4. Connect GitHub repository
5. Select `nutrition-bot` repo

### Step 3: Configure Service

**Build Command:**
```bash
pip install -r requirements.txt
```

**Start Command:**
```bash
python -m src.main
```

Or if using a different entry point:
```bash
python src/main.py
```

**Environment Variables:**
Add in Render dashboard:

```
TELEGRAM_BOT_TOKEN=your_telegram_token
GROQ_API_KEY=your_groq_key
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@db.XXXXX.supabase.co:5432/postgres
```

### Step 4: Deploy

1. Click "Create Web Service"
2. Wait for deployment (5-10 minutes)
3. Check logs for errors
4. Test bot in Telegram: `/start`

---

## Part 5: Verifying Migration

### Test 1: Bot Functionality

Send these commands to your bot:

```
/start                    # Should work
/log apple                # Add food
/day_summary              # View today's nutrition
/saved_meals              # List saved meals
```

**Expected**: All commands work without errors.

### Test 2: Data Persistence

1. Add food: `/log banana`
2. Check food was saved: `/day_summary`
3. Stop bot (Ctrl+C or Render deploy stop)
4. Start bot again
5. Check food still there: `/day_summary`

**Expected**: Banana entry persists after restart ✅

### Test 3: Multiple Deployments

1. Make a small change to code
2. Push to GitHub
3. Render auto-redeploys
4. Check food data still exists: `/day_summary`

**Expected**: Data survives redeployment ✅

### Test 4: Database Connection Pool

Add this debug handler:

```python
from aiogram import Router, types
from aiogram.filters import Command

debug_router = Router()

@debug_router.message(Command("pool_status"))
async def pool_status(message: types.Message):
    size = db.pool.get_size()
    idle = db.pool.get_idle_size()
    await message.answer(f"🔌 Pool: {size} total, {idle} idle")

# In setup_dispatcher():
dp.include_router(debug_router)
```

Send `/pool_status` multiple times:
- Idle state: `Pool: 5 total, 5 idle`
- Under load: `Pool: 8 total, 2 idle` (then back to 5)

**Expected**: Pool size increases under load, shrinks at rest ✅

---

## Part 6: Monitoring & Maintenance

### Monitor from Supabase Dashboard

1. Dashboard → "SQL Editor"
2. Run query to check data:
   ```sql
   SELECT COUNT(*) as user_count FROM users;
   SELECT COUNT(*) as logs_count FROM food_logs;
   SELECT MAX(date) as latest_log FROM food_logs;
   ```

### Setup Backups

**Supabase automatically:**
- ✅ Daily backups for 7 days
- ✅ Point-in-time restore for 30 days
- ✅ No additional config needed

To download backup manually:
1. Dashboard → "Database" → "Backups"
2. Click download icon

### Monitor Render Logs

1. Render dashboard → Select service
2. Logs tab shows real-time output
3. Look for:
   - `✅ Base de datos PostgreSQL inicializada` (good)
   - `asyncpg` errors (bad - check DATABASE_URL)
   - `Connection timeout` (bad - Supabase server issue)

---

## Part 7: Troubleshooting

### Error: "psycopg error: fe_sendauth: no password supplied"

**Cause**: DATABASE_URL missing or incorrect password

**Fix**:
1. Recheck Supabase URL from dashboard
2. Verify password is correct (exact match)
3. Update `.env` and redeploy

### Error: "Host not found: db.xxxxx.supabase.co"

**Cause**: Network blocked or Supabase URL wrong

**Fix**:
1. Test connection locally: `python -m asyncio -c "import socket; socket.getaddrinfo('db.xxxxx.supabase.co', 5432)"`
2. Verify `xxxxx` matches your project ID
3. Check firewall rules on network

### Error: "SSL error: certificate verify failed"

**Cause**: SSL certificate issue

**Fix**:
```python
# In config.py or temporarily:
ssl=False  # For local testing ONLY
# Then change back to:
ssl='require'  # For production
```

### Bot Responds Slowly (>3 seconds)

**Cause**: 
- Supabase query slow
- Network latency high
- Connection pool exhausted

**Check**:
```bash
# Check pool status
/pool_status  # Should see healthy pool

# Check Supabase performance
# Dashboard → Monitoring → Slow Queries
```

### Data Lost After Redeploy

**Cause**: Using old SQLite (not migrated)

**Fix**:
1. Verify `src/database/db.py` has `asyncpg` imports
2. Verify `requirements.txt` has `asyncpg` (not `aiosqlite`)
3. Verify `.env` has `DATABASE_URL` (not `DB_PATH`)
4. Force rebuild: `Render dashboard → Redeploy`

---

## Part 8: Database Schema Reference

### Users Table
```sql
CREATE TABLE users (
    user_id BIGSERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    first_name TEXT NOT NULL,
    daily_calorie_goal INTEGER DEFAULT 2000,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Food Logs Table
```sql
CREATE TABLE food_logs (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    food_name TEXT NOT NULL,
    kcal INTEGER NOT NULL,
    protein FLOAT NOT NULL,
    carbs FLOAT NOT NULL,
    fat FLOAT NOT NULL,
    image_file_id TEXT,
    date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
```

### Saved Meals Table
```sql
CREATE TABLE saved_meals (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    kcal INTEGER NOT NULL,
    protein FLOAT NOT NULL,
    carbs FLOAT NOT NULL,
    fat FLOAT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
```

---

## Part 9: Quick Reference Checklist

### Before First Deploy
- [ ] Updated `requirements.txt` (asyncpg present, aiosqlite gone)
- [ ] Updated `src/database/db.py` (asyncpg version)
- [ ] Updated `src/config.py` (DATABASE_URL validation)
- [ ] Updated `src/main.py` (db.close() in finally)
- [ ] Created Supabase account
- [ ] Created Supabase project
- [ ] Copied DATABASE_URL to `.env`
- [ ] Tested locally: `asyncio.run(db.initialize())`

### After Deploy to Render
- [ ] Set `DATABASE_URL` in Render environment variables
- [ ] Check Render build logs for errors
- [ ] Test `/start` command in Telegram
- [ ] Test `/log` to add data
- [ ] Restart bot and verify data persists
- [ ] Monitor for connection pool exhaustion

### Monthly Maintenance
- [ ] Review Supabase backups status
- [ ] Check Render logs for errors
- [ ] Monitor query performance in Supabase
- [ ] Update `asyncpg` library if new version available

---

## Summary

✅ **What was accomplished:**
- Migrated database from SQLite (ephemeral file) to PostgreSQL (persistent cloud)
- Implemented asyncpg with connection pooling (5-20 concurrent connections)
- Ensured 100% compatibility with existing bot code (same function signatures)
- Bot now survives Render deployments
- Data persists across restarts

🚀 **You're production-ready!**
