# Migration Summary: SQLite → PostgreSQL

## Quick Reference Card

### Architecture Change

```
BEFORE (SQLite)
┌─────────────────┐
│   Render App    │
│  (Python Bot)   │
└────────┬────────┘
         │
         ↓ Direct file I/O
┌─────────────────┐
│ nutrition_bot.db│ (ephemeral - deleted on redeploy)
└─────────────────┘

AFTER (PostgreSQL with Supabase)
┌─────────────────┐
│   Render App    │
│  (Python Bot)   │
└────────┬────────┘
         │
         ↓ TCP + SSL
┌──────────────────────────────┐
│ Supabase PostgreSQL Server   │ (persistent - survives redeploys)
│ (AWS-backed, daily backups)  │
└──────────────────────────────┘
```

---

## Code Changes at a Glance

### 1. Import Changes

```python
# BEFORE
import aiosqlite

# AFTER
import asyncpg
```

### 2. Connection Setup

```python
# BEFORE: Direct file connection
self.db_path = "data/nutrition_bot.db"
conn = await aiosqlite.connect(self.db_path)

# AFTER: Connection pooling
self.pool = await asyncpg.create_pool(
    dsn=DATABASE_URL,
    min_size=5,
    max_size=20,
    ssl='require'
)
```

### 3. SQL Syntax

```python
# BEFORE: SQLite parameter style
query = "INSERT INTO users (username) VALUES (?)"
await cursor.execute(query, (username,))

# AFTER: PostgreSQL parameter style
query = "INSERT INTO users (username) VALUES ($1)"
result = await conn.fetch(query, username)
```

### 4. Row Access

```python
# BEFORE: Tuple indexing
result = await cursor.fetchone()  # Returns (123, 'John', 2000, ...)
user_id = result[0]               # tuple index

# AFTER: Named field access
result = await conn.fetchrow(query)  # Returns asyncpg.Record
user_id = result['user_id']         # or result.user_id
```

### 5. Exception Handling

```python
# BEFORE
try:
    ...
except sqlite3.IntegrityError:
    # Unique constraint violation
    
# AFTER
try:
    ...
except asyncpg.UniqueViolationError:
    # Unique constraint violation
```

### 6. Connection Management

```python
# BEFORE: Single connection
async with aiosqlite.connect(db_path) as conn:
    result = await conn.execute(query)

# AFTER: Connection pool
async with self.pool.acquire() as conn:
    result = await conn.fetch(query)
```

### 7. Cleanup

```python
# BEFORE: Nothing needed (file auto-closed)
# Bot stops, no explicit cleanup

# AFTER: Graceful pool closure
finally:
    await db.close()  # Closes all pool connections
```

---

## Function Signature Compatibility

✅ **ALL function signatures remain identical:**

```python
# These are exactly the same in src/main.py and src/services/api_services.py

# Add user
await db.add_user(user_id, username, first_name, calorie_goal)

# Get user
user = await db.get_user(user_id)

# Add food log
await db.save_food_log(user_id, food_name, kcal, protein, carbs, fat, date)

# Get today's summary
food_logs = await db.get_food_logs_by_date(user_id, date)

# Add saved meal
await db.add_saved_meal(user_id, meal_name, kcal, protein, carbs, fat)

# Get saved meals
meals = await db.get_saved_meals(user_id)
```

**Zero changes needed to bot logic!**

---

## File-by-File Changes

| File | Changes | Impact |
|------|---------|--------|
| `src/database/db.py` | 🔴 Complete rewrite | Database backend |
| `requirements.txt` | 🟡 Replace aiosqlite with asyncpg | Dependencies |
| `src/config.py` | 🟡 Remove DB_PATH, add DATABASE_URL | Configuration |
| `.env` | 🟡 Update connection string | Credentials |
| `.env.example` | 🟡 Update example template | Documentation |
| `src/main.py` | 🟢 Add db.close() in finally | Cleanup |
| Other files | ✅ No changes | Compatibility |

🔴 = Major internal change, but same external API
🟡 = Configuration change  
🟢 = Minor improvement
✅ = No changes needed

---

## Performance Impact

| Metric | SQLite | PostgreSQL | Impact |
|--------|--------|-----------|--------|
| **First Connection** | ~0ms (file read) | ~100ms (network) | Startup +100ms |
| **Query Speed** | ~5ms (file I/O) | ~10ms (network) | Slower for single query |
| **Concurrent Queries** | 1 writer | Up to 20 parallel | **Much faster overall** |
| **Max Users** | ~100 (single file) | Unlimited | **Highly scalable** |
| **Data Persistence** | ❌ Lost on redeploy | ✅ Always safe | **Production-ready** |

**Real-world**: Despite slower individual queries, pooling + parallelism = faster overall response times for multiple concurrent users.

---

## Connection Pool Visualization

### Startup
```
┌─────────────────────────────┐
│ Pool initialized            │
│ [●][●][●][●][●]            │ 5 idle connections
└─────────────────────────────┘
```

### User 1 Sends Message
```
┌─────────────────────────────┐
│ User1 query running         │
│ [◐][●][●][●][●]            │ 1 active, 4 idle
└─────────────────────────────┘
```

### Users 1-8 Send Messages (Peak Load)
```
┌─────────────────────────────┐
│ 8 concurrent queries        │
│ [◐][◐][◐][◐][◐][◐][◐][◐]  │ 8 active, 0 idle
│ (auto-created 3 more)       │ (pool at 5+3 out of max 20)
└─────────────────────────────┘
```

### Queries Finish
```
┌─────────────────────────────┐
│ Back to idle state          │
│ [●][●][●][●][●]+3 closing  │ 5 kept, 3 removed
└─────────────────────────────┘
```

---

## Environment Variable Migration

### Before (.env with SQLite)
```bash
TELEGRAM_BOT_TOKEN=5123456789:ABCdef...
GROQ_API_KEY=grsk_xxxxxxx...
# DB_PATH=data/nutrition_bot.db  # Implicit (in code)
```

### After (.env with PostgreSQL)
```bash
TELEGRAM_BOT_TOKEN=5123456789:ABCdef...
GROQ_API_KEY=grsk_xxxxxxx...
DATABASE_URL=postgresql://postgres:mypassword123@db.xxxxx.supabase.co:5432/postgres
```

**New variable**: `DATABASE_URL` (Supabase connection string)

---

## Deployment Checklist

### Local Development ✓
- [x] Supabase account created
- [x] Supabase project created
- [x] DATABASE_URL in .env
- [x] `asyncio.run(db.initialize())` tests passing
- [x] Bot works with `/start`, `/log`, `/day_summary`

### Render Production ✓
- [x] GitHub repo updated
- [x] DATABASE_URL set in Render dashboard
- [x] Build passes (no asyncpg import errors)
- [x] Bot starts successfully
- [x] Data persists after restart
- [x] Data persists after redeploy

### Monitoring ✓
- [x] Check Render logs daily for errors
- [x] Monitor Supabase backup status
- [x] Test bot commands weekly
- [x] Review slow queries monthly

---

## Rollback Plan (If Problems)

### If PostgreSQL becomes unreachable:

**Option A: Quick Revert to SQLite** (temporary)
```bash
git checkout HEAD~ src/database/db.py
git checkout HEAD~ requirements.txt
# Rollback command on Render
```

**Option B: Check Supabase Status**
1. Supabase Dashboard → Status page
2. Verify no outages
3. Restart bot
4. Check if pool reconnects automatically

**Option C: Database Connection Issue**
1. Verify DATABASE_URL in Render dashboard
2. Test connection locally: `python -c "from src.database.db import db; asyncio.run(db.initialize())"`
3. If local works but Render fails: Network/firewall issue
4. Check Supabase IP whitelist

---

## Benefits of Migration

✅ **Data Persistence**: Survives Render deployments
✅ **Scalability**: Support unlimited users (not bottlenecked by single file)
✅ **Backups**: Automatic daily backups on Supabase
✅ **Performance**: Connection pooling (5-20 concurrent connections)
✅ **Security**: SSL encrypted connection, remote server, no local data
✅ **Flexibility**: SQL queries more powerful than SQLite for future growth
✅ **Monitoring**: Supabase dashboard shows database health
✅ **Cost**: Free tier covers bot usage (~10k requests/day is well within limits)

---

## Key Takeaways

1. **No code changes needed** - All function signatures identical
2. **Configuration changes only** - Update .env with DATABASE_URL
3. **Connection pooling** - Automatic, scales 5-20 connections
4. **Persistent storage** - Data survives Render redeploys
5. **Production-ready** - Daily backups, SSL encryption, automatic scaling

---

## Questions?

Refer to:
- **Connection pooling details**: See `PostgreSQL_CONNECTION_POOLING.md`
- **Setup & deployment steps**: See `SUPABASE_DEPLOYMENT_GUIDE.md`
- **Database schema**: See schema section in deployment guide
- **Troubleshooting**: See troubleshooting section in deployment guide
