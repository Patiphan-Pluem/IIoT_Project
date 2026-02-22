import os
import time
import psycopg2
import numpy as np
from datetime import datetime  # เพิ่มเพื่อแสดงเวลาปัจจุบัน

# การตั้งค่าเชื่อมต่อ Database
DB_HOST = os.getenv('DB_HOST', 'timescaledb-service.edge-apps')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASS = os.getenv('DB_PASS', 'password')
DB_NAME = os.getenv('DB_NAME', 'postgres')

SIMULATION_MODE = os.getenv('SIM_MODE', 'matrix') 

def get_db_connection():
    try:
        return psycopg2.connect(host=DB_HOST, user=DB_USER, password=DB_PASS, dbname=DB_NAME, connect_timeout=5)
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [DB Error] {e}")
        return None

def get_pmu_count():
    conn = get_db_connection()
    if not conn: return 0
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM pmu_measurements WHERE time > NOW() - INTERVAL '10 seconds';")
        result = cur.fetchone()
        cur.close()
        conn.close()
        return result[0] if result else 0
    except Exception as e:
        return 0

def ems_nested_loop(n):
    start_time = time.time()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] --- [Mode: Loop] Processing n={n} ---")
    
    res = 0
    for i in range(n):
        for j in range(n):
            for k in range(n):
                res += (i * j) + k
    
    elapsed = time.time() - start_time
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Loop calculation finished in {elapsed:.2f} seconds.")
    return res

def ems_matrix(n):
    start_time = time.time()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] --- [Mode: Matrix] Processing n={n} ---")
    
    A = np.random.rand(n, n)
    B = np.random.rand(n, n)
    res = np.dot(A, B)
    
    elapsed = time.time() - start_time
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Matrix calculation finished in {elapsed:.2f} seconds.")
    return res

print(f"--- EMS Black Box Engine Starting (Mode: {SIMULATION_MODE}) ---")

while True:
    try:
        data_count = get_pmu_count()
        
        if data_count > 0:
            if SIMULATION_MODE == 'matrix':
                ems_matrix(data_count)
            else:
                ems_nested_loop(data_count)
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] No new PMU data. Waiting...")
        
        time.sleep(10)

    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Error: {e}")
        time.sleep(5)