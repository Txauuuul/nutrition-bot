# PostgreSQL Connection Pooling Strategy

## Overview

The migration from SQLite to PostgreSQL uses **asyncpg** with **connection pooling** to efficiently manage database connections. This document explains the architecture, configuration, and behavior.

---

## 1. What is a Connection Pool?

### Without Pooling (Bad)
```
Request 1: Create connection → Query → Close connection [~100ms per request]
Request 2: Create connection → Query → Close connection [~100ms per request]
Request 3: Create connection → Query → Close connection [~100ms per request]
Total: 300ms for 3 requests
```

Creating a TCP connection to PostgreSQL takes ~50-100ms. If you create a new connection for each request, you waste significant time.

### With Pooling (Good)
```
Startup: Create 5 idle connections upfront [~500ms one-time cost]
Request 1: Borrow connection → Query → Return connection [~10ms]
Request 2: Borrow connection → Query → Return connection [~10ms]
Request 3: Borrow connection → Query → Return connection [~10ms]
Total: 30ms for 3 requests (10x faster!)
```

The pool pre-creates connections at startup and reuses them.

---

## 2. Pool Configuration in `database.py`

```python
async def connect(self) -> None:
    """Initialize PostgreSQL connection pool."""
    self.pool = await asyncpg.create_pool(
        dsn=DATABASE_URL,
        min_size=5,
        max_size=20,
        ssl='require',
        command_timeout=10,
    )
```

### Parameters Explained

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `dsn` | PostgreSQL URL | Connection string (from Supabase) |
| `min_size` | 5 | Idle connections pool maintains at all times |
| `max_size` | 20 | Maximum concurrent connections allowed |
| `ssl` | 'require' | Force SSL for remote Supabase server |
| `command_timeout` | 10 | Seconds before query timeout |

---

## 3. Min/Max Size Strategy

### Min Size = 5
- **At startup**: Pool creates 5 connections immediately
- **Always ready**: These 5 stay open, ready to serve requests
- **Cost**: 5 idle connections consume ~50MB memory total
- **Benefit**: Zero wait time for first 5 concurrent requests

### Max Size = 20
- **Under load**: If all 5 are busy, pool creates more (up to 20)
- **Scaling**: Automatically creates connection 6, 7, 8... as demand increases
- **Protection**: Won't exceed 20 (prevents resource exhaustion)
- **Cleanup**: When demand drops, extra connections are closed and pool shrinks back to 5 idle

### Example Timeline
```
00:00 - Bot starts:
  Pool.idle = 5, Pool.total = 5, Pool.waiting = 0
  
00:05 - 8 users send messages simultaneously:
  Request 1-5: Use idle connections instantly
  Request 6-8: Pool creates 3 more (now 8 total)
  Result: All 8 queries execute in parallel
  
00:06 - 2 requests finish, 3 more arrive:
  Result: Pool has 8 available (2 from finished + 6 new requests)
  
00:10 - All activity stops:
  Pool shrinks back to 5 idle after 30 seconds inactivity
```

---

## 4. Acquire/Release Pattern

### How Connections Flow

```python
async with self.pool.acquire() as conn:
    result = await conn.fetch(query, *args)
    return result
```

**Step-by-step execution:**

1. **Acquire** (`async with self.pool.acquire() as conn`):
   - Check if idle connection available
   - If yes: Get idle connection immediately (~1µs)
   - If no: Create new connection (up to max_size=20)
   - If at max: WAIT until connection returns (~1-100ms)

2. **Use** (`await conn.fetch(...)`):
   - Execute query on this connection
   - Connection busy during query (~1-500ms depending on query complexity)

3. **Release** (automatic on `__exit__`):
   - Return connection to pool
   - Connection becomes idle again
   - Next waiting request gets it

### Visual Flow
```
[Pool: 5 Idle]
    ↓ Request arrives
[Pool: 4 Idle, 1 Busy] → Query executes → [Pool: 5 Idle]
    ↓ 8 Requests arrive
[Pool: 0 Idle, 8 Busy] (all 5 + 3 new) → Queries execute → [Pool: 5 Idle]
```

---

## 5. SSL Configuration for Supabase

### Why SSL Required?
- **Supabase**: Runs on remote AWS servers
- **Network**: Data travels over public internet
- **Risk**: Without SSL, credentials visible in network traffic
- **Solution**: SSL encrypts all data in transit

### SSL Modes in asyncpg
```python
ssl='require'      # Must use SSL, fail if unavailable
ssl='prefer'       # Use SSL if available, fall back to plaintext
ssl=False          # No SSL (only for localhost development)
```

For Supabase: **Always use `ssl='require'`**

---

## 6. Connection Timeout Behavior

```python
command_timeout=10  # Seconds
```

### What Happens with Timeout?

```
00:00 - Query starts
00:05 - Query still running (5 seconds elapsed)
00:10 - TIMEOUT! Query killed, connection returned to pool
        Exception raised: asyncpg.exception.TimeoutError
        Bot user gets "Database query timeout" message
```

### Why 10 Seconds?
- **Telegram**: Users expect response in ~3 seconds
- **Network**: Supabase ~50-100ms latency
- **Query**: Our queries typically < 100ms
- **Buffer**: 10s allows for rare slow queries
- **Safety**: Prevents connections from hanging forever

---

## 7. Connection Lifecycle

### Phase 1: Initialization (App Startup)
```python
await db.initialize()  # Calls db.connect() internally
```
- Creates pool with 5 connections
- Establishes SSH tunnel to Supabase (if needed)
- Creates tables if not exist
- Ready for requests

### Phase 2: Steady State (App Running)
```
User sends /start command
  → Telegram webhook hits bot
  → Handler acquires connection from pool
  → Query executes
  → Connection released
  → Pool has 5-X idle connections waiting
```

### Phase 3: Graceful Shutdown
```python
finally:
    await db.close()  # Close gracefully
    await bot.session.close()
```
- Waits for all active queries to complete
- Closes all idle connections
- Releases socket/memory
- Exit signal returns to OS

---

## 8. Monitoring Connection Pool

### How to Check Pool Status

Add this to a debug handler:
```python
@router.message(Command("status"))
async def status_handler(message: Message):
    size = db.pool.get_size()
    idle = db.pool.get_idle_size()
    await message.answer(f"Pool size: {size}, Idle: {idle}")
```

**Interpretation:**
- `size=5, idle=5` → Normal idle state
- `size=8, idle=2` → 6 queries currently running
- `size=20, idle=0` → At max capacity, 20 concurrent queries

---

## 9. Comparison: SQLite vs PostgreSQL

| Feature | SQLite | PostgreSQL |
|---------|--------|----------|
| **Connection** | File on disk | TCP to server |
| **Setup Time** | ~0ms | ~50-100ms |
| **Pooling** | Not needed | Essential |
| **Concurrency** | Single writer | Multiple writers |
| **Persistence** | Ephemeral on Render | Persistent Supabase |
| **Backup** | Manual copy files | Automatic snapshots |

---

## 10. Troubleshooting

### Issue: "Cannot acquire connection: pool exhausted"
**Cause**: All 20 connections busy, no timeout yet
**Solution**: Increase `max_size` or optimize slow queries

### Issue: "SSL error" or "certificate problem"
**Cause**: Supabase SSL certificate not trusted
**Solution**: Ensure `ssl='require'` set

### Issue: Connection hangs for 10 seconds then times out
**Cause**: Query too slow or network latency
**Solution**: Check Supabase database performance or optimize query

### Issue: "too many connections"
**Cause**: Crashed bot left connections open
**Solution**: Ensure `await db.close()` always called in finally block

---

## 11. Production Checklist

- [ ] `.env` has `DATABASE_URL` from Supabase
- [ ] `DATABASE_URL` format: `postgresql://user:password@db.xxxxx.supabase.co:5432/postgres`
- [ ] `requirements.txt` has `asyncpg` and removed `aiosqlite`
- [ ] `src/main.py` calls `await db.close()` in finally
- [ ] Test with `python -m pytest tests/` (if tests exist)
- [ ] Monitor pool via handler after 1 hour of traffic
- [ ] Supabase has daily backups configured
- [ ] Alert set for connection pool exhaustion

---

## 12. Quick Reference

**Initialize pool:**
```python
await db.initialize()  # Creates 5 connections
```

**Acquire connection:**
```python
async with db.pool.acquire() as conn:
    result = await conn.fetch(query)
```

**Close pool:**
```python
await db.close()  # Closes all connections gracefully
```

**Check pool status:**
```python
print(f"Size: {db.pool.get_size()}, Idle: {db.pool.get_idle_size()}")
```

---

## Summary

The connection pooling strategy ensures:
1. **Performance**: Reuse connections (10x faster than creating new ones)
2. **Resource Efficiency**: Min 5, max 20 connections (no exhaustion)
3. **Reliability**: SSL for Supabase, timeouts prevent hangs
4. **Persistence**: PostgreSQL survives Render deployments (unlike SQLite)
5. **Scalability**: Automatically handles traffic spikes up to 20 concurrent queries
