import os
import time
import psycopg2
import numpy as np
import ray
from datetime import datetime

DB_HOST = os.getenv('DB_HOST', 'timescaledb-service')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASS = os.getenv('DB_PASS', 'password')
DB_NAME = os.getenv('DB_NAME', 'postgres')

SIMULATION_MODE = os.getenv('SIM_MODE', 'matrix') 
MANUAL_DATA_COUNT = int(os.getenv('MANUAL_DATA_COUNT', '0'))
DIVIDER_VALUE = int(os.getenv('DIVIDER_VALUE', '1'))

ray.init(address='auto', ignore_reinit_error=True)

@ray.remote
def ems_nested_loop_distributed(worker_id, n_start, n_end, total_n):
    start_t = time.time()
    res = 0
    for i in range(n_start, n_end):
        for j in range(total_n):
            for k in range(total_n):
                res += 1
    elapsed = time.time() - start_t
    return f"Worker {worker_id} finished [{n_start}:{n_end}] in {elapsed:.2f}s"

@ray.remote
def ems_matrix_distributed(n):
    start_t = time.time()
    A = np.random.rand(n, n)
    B = np.random.rand(n, n)
    np.dot(A, B)
    elapsed = time.time() - start_t
    return elapsed

def get_db_connection():
    try:
        return psycopg2.connect(host=DB_HOST, user=DB_USER, password=DB_PASS, dbname=DB_NAME, connect_timeout=5)
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [DB Error] {e}")
        return None

def get_message_count():
    conn = get_db_connection()
    if not conn: return 0
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM pmu_measurements WHERE time > NOW() - INTERVAL '60 seconds';")
        result = cur.fetchone()
        cur.close()
        conn.close()
        return result[0] if result else 0
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Error: {e}")
        return 0

def get_active_worker_count():
    nodes = ray.nodes()
    active_workers = [
        node for node in nodes 
        if node['Alive'] and "node:__internal_head__" not in node['Resources']
    ]
    count = len(active_workers)
    return max(1, count)

print(f"--- EMS Distributed Engine Starting (Mode: {SIMULATION_MODE}) ---")

pending_futures = []

while True:
    cycle_start = time.time()
    try:
        raw_count = get_message_count() 
        if raw_count == 0:
            raw_count = MANUAL_DATA_COUNT

        data_count = raw_count // max(1, DIVIDER_VALUE)
        
        if data_count != 0:
            num_pods = get_active_worker_count()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] --- [Mode: {SIMULATION_MODE.capitalize()}] Detected {num_pods} Pod(s), Processing n={data_count} ---")

            if len(pending_futures) < num_pods * 2:
                if SIMULATION_MODE == 'matrix':
                    for _ in range(3):
                        pending_futures.append(ems_matrix_distributed.remote(data_count))
                else:
                    chunk = data_count // num_pods
                    for i in range(num_pods):
                        start = i * chunk
                        end = (i + 1) * chunk if i != num_pods - 1 else data_count
                        pending_futures.append(ems_nested_loop_distributed.remote(i, start, end, data_count))
            
            if pending_futures:
                ready, pending_futures = ray.wait(pending_futures, num_returns=1, timeout=0.1)
                for r in ready:
                    result = ray.get(r)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {result}")
            
            if not pending_futures and data_count == 0:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] No pending tasks. Waiting...")
        
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] No new PMU data. Waiting...")
        
        time.sleep(max(0, 60 - (time.time() - cycle_start)))

    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Error: {e}")
        time.sleep(3)