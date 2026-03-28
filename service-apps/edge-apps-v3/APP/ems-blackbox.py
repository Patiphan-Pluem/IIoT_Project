import os
import time
import psycopg2
import numpy as np
import ray
from datetime import datetime  

# --- 1. ดึง Environment Variables (ครบตามต้นฉบับ) ---
DB_HOST = os.getenv('DB_HOST', 'timescaledb-service')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASS = os.getenv('DB_PASS', 'password')
DB_NAME = os.getenv('DB_NAME', 'postgres')

SIMULATION_MODE = os.getenv('SIM_MODE', 'matrix') 
MANUAL_DATA_COUNT = int(os.getenv('MANUAL_DATA_COUNT', '0'))
DIVIDER_VALUE = int(os.getenv('DIVIDER_VALUE', '1'))

# เชื่อมต่อ Ray
ray.init(address='auto', ignore_reinit_error=True)

# --- 2. ฟังก์ชันคำนวณ (Remote Functions) ---

@ray.remote
def ems_nested_loop_distributed(n_start, n_end, total_n):
    res = 0
    for i in range(n_start, n_end):
        for j in range(total_n):
            for k in range(total_n):
                res += 1
    return res

@ray.remote
def ems_matrix_distributed(n):
    start_time = time.time()
    A = np.random.rand(n, n)
    B = np.random.rand(n, n)
    np.dot(A, B)
    return time.time() - start_time

# --- 3. ฟังก์ชัน DB (คงเดิม) ---
def get_db_connection():
    try:
        return psycopg2.connect(host=DB_HOST, user=DB_USER, password=DB_PASS, dbname=DB_NAME, connect_timeout=5)
    except Exception as e:
        return None

def get_message_count():
    conn = get_db_connection()
    if not conn: return 0
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM pmu_measurements WHERE time > NOW() - INTERVAL '60 seconds';")
        result = cur.fetchall()
        cur.close()
        conn.close()
        return len(result) if result else 0
    except Exception as e:
        return 0

# --- 4. ฟังก์ชันเช็คจำนวน Pod ที่ใช้งานได้จริง ---
def get_active_worker_count():
    # นับจำนวน nodes ใน ray cluster ที่มีสถานะ alive
    nodes = ray.nodes()
    active_workers = [node for node in nodes if node['Alive']]
    return len(active_workers)

print(f"--- EMS Auto-Scaling Engine Starting (Mode: {SIMULATION_MODE}) ---")



while True:
    cycle_start = time.time()
    try:
        raw_count = get_message_count() 
        if raw_count == 0:
            raw_count = MANUAL_DATA_COUNT

        data_count = raw_count // max(1, DIVIDER_VALUE)
        
        if data_count != 0:
            # เช็คจำนวน Pod จริง ณ เวลานั้น
            num_pods = get_active_worker_count()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Detected {num_pods} active Pod(s).")

            if SIMULATION_MODE == 'matrix':
                # ถ้าเป็น Matrix งานเดียว ให้กระจายไปทำ 1 Pod ที่ว่างที่สุด
                future = ems_matrix_distributed.remote(data_count)
                ray.get(future)
            else:
                # ถ้าเป็น Loop ให้หั่นงานตามจำนวน Pod จริงที่มีอยู่ (Dynamic Chunks)
                chunk = data_count // num_pods
                futures = []
                for i in range(num_pods):
                    start = i * chunk
                    end = (i + 1) * chunk if i != num_pods - 1 else data_count
                    futures.append(ems_nested_loop_distributed.remote(start, end, data_count))
                
                results = ray.get(futures)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Distributed Loop among {num_pods} pods finished.")

        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] No data. Waiting...")
        
        time.sleep(max(0, 60 - (time.time() - cycle_start)))

    except Exception as e:
        print(f"Error: {e}")
        time.sleep(3)