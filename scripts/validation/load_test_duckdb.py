import duckdb
import time
import random
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = "data/utxoracle_load_test.duckdb"

def setup_db():
    if Path(DB_PATH).exists():
        Path(DB_PATH).unlink()
    
    conn = duckdb.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE prices (
            timestamp TIMESTAMP PRIMARY KEY,
            utxoracle_price DECIMAL(12, 2),
            mempool_price DECIMAL(12, 2),
            confidence DECIMAL(5, 4),
            tx_count INTEGER,
            diff_amount DECIMAL(12, 2),
            diff_percent DECIMAL(6, 2),
            is_valid BOOLEAN DEFAULT TRUE
        )
    """)
    return conn

def load_data(conn, count=10000):
    print(f"Inserting {count} rows...")
    start_time = time.time()
    
    base_ts = datetime.now()
    rows = []
    for i in range(count):
        ts = base_ts - timedelta(minutes=10 * i)
        utx_p = 60000 + random.uniform(-1000, 1000)
        mem_p = utx_p + random.uniform(-100, 100)
        diff = mem_p - utx_p
        rows.append((
            ts, utx_p, mem_p, 0.9, 2000, diff, (diff/utx_p)*100, True
        ))
    
    conn.executemany("INSERT INTO prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
    
    end_time = time.time()
    print(f"Insertion complete in {end_time - start_time:.2f} seconds")

def test_queries(conn):
    print("Testing query performance...")
    
    # Test 1: Latest price
    start = time.time()
    conn.execute("SELECT * FROM prices ORDER BY timestamp DESC LIMIT 1").fetchone()
    latest_time = (time.time() - start) * 1000
    print(f"Latest price query: {latest_time:.2f} ms")
    
    # Test 2: Historical (7 days)
    start = time.time()
    conn.execute("SELECT * FROM prices WHERE timestamp > current_timestamp - interval '7 days'").fetchall()
    hist_time = (time.time() - start) * 1000
    print(f"Historical (7 days) query: {hist_time:.2f} ms")
    
    # Test 3: Stats
    start = time.time()
    conn.execute("SELECT avg(diff_percent), max(diff_percent) FROM prices").fetchone()
    stats_time = (time.time() - start) * 1000
    print(f"Stats query: {stats_time:.2f} ms")
    
    return latest_time, hist_time, stats_time

if __name__ == "__main__":
    conn = setup_db()
    load_data(conn)
    latest, hist, stats = test_queries(conn)
    
    if latest < 50 and hist < 50:
        print("\n✅ LOAD TEST PASSED: All critical queries < 50ms")
    else:
        print("\n❌ LOAD TEST FAILED: Some queries > 50ms")
    
    conn.close()
    # Path(DB_PATH).unlink()
