from synchrophasor.pdc import Pdc
from synchrophasor.frame import DataFrame
import threading
import time
import os
import psycopg2
from datetime import datetime

# # config
PDC_ID      = 7
# PMU_IP      = "pmu-device"
# PMU_PORT    = 1410
RETRY_DELAY = 3
MAX_RETRIES = 20

########## Database Setting ###############
DB_HOST = os.getenv("DB_HOST", "timescaledb-edge-b-rw")
DB_NAME = os.getenv("DB_NAME", "app")
DB_USER = os.getenv("DB_USER", "app")
DB_PASS = os.getenv("DB_PASSWORD", "password")
DB_PORT = os.getenv("DB_PORT", "5432")

msg_count = 0
batch_data = []
count_lock = threading.Lock()
BATCH_SIZE = 30 

def get_db_connection():
    while True:
        try:
            conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS, port=DB_PORT)
            print("Connected to TimescaleDB successfully!")
            return conn
        except Exception as e:
            print(f"Failed to connect to DB: {e}. Retrying in 2s...", flush=True)
            time.sleep(2)


def connect_with_retry():
    target_ip = os.getenv("PMU_IP", "pmu-service.edge-apps")
    target_port = 1410
    pdc = Pdc(pdc_id=7, pmu_ip=target_ip, pmu_port=target_port)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"[PDC] Connecting to {target_ip}:{target_port} (attempt {attempt}/{MAX_RETRIES})")
            pdc.run()
            config = pdc.get_config()
            pdc.start()
            print("[PDC] Connected and configured.")
            return pdc, config
        except Exception as e:
            print(f"[PDC] Failed: {e} — retrying in {RETRY_DELAY}s...")
            try:
                pdc.stop()
            except:
                pass
            time.sleep(RETRY_DELAY)
            pdc = Pdc(pdc_id=PDC_ID, pmu_ip=target_ip, pmu_port=target_port)
    raise RuntimeError("Cannot connect to PMU after max retries")

def receive_loop(pdc_ref):

    global msg_count
    while True:
        try:
            data = pdc_ref[0].get() 
            if isinstance(data, DataFrame):
                with count_lock:
                    msg_count += 1
        except Exception:
            break  

if __name__ == "__main__":
    db_conn = get_db_connection()
    #init_db(db_conn)
    pdc, config = connect_with_retry()

    pdc_ref = [pdc]
    recv_thread = threading.Thread(target=receive_loop, args=(pdc_ref,), daemon=True)
    recv_thread.start()

    last_check = time.time()

    try:
        while True:
            time.sleep(0.1)
            now = time.time()

            current_batch = []
            with count_lock:
                if len(batch_data) >= BATCH_SIZE:
                    current_batch = batch_data[:]
                    batch_data = []

            if current_batch:
                try:
                    if db_conn.closed: db_conn = get_db_connection()
                    cur = db_conn.cursor()
                    query = """
                        INSERT INTO pmu_measurements 
                        (time, frequency, magnitude, angle, mag_b, ang_b, mag_c, ang_c)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    cur.executemany(query, current_batch)
                    db_conn.commit()
                    cur.close()
                except Exception as db_err:
                    print(f"[DB] Insert Error: {db_err}", flush=True)
                    db_conn.rollback()
            
            if now - last_check >= 1.0:
                with count_lock:
                    mps = msg_count
                    msg_count = 0
          
                print(f"REALTIME_MPS:{mps}", flush=True)
                last_check = now

    
            if not recv_thread.is_alive():
                print("[PDC] Receiver thread died — reconnecting...")
                try:
                    pdc.stop()
                except:
                    pass
                time.sleep(RETRY_DELAY)
                pdc, config = connect_with_retry()
                pdc_ref[0] = pdc
                with count_lock:
                    msg_count = 0
                recv_thread = threading.Thread(target=receive_loop, args=(pdc_ref,), daemon=True)
                recv_thread.start()

    except KeyboardInterrupt:
        print("[PDC] Shutting down...")
    finally:
        try:
            pdc.stop()
            pdc.join()
        except:
            pass
        print("[PDC] Stopped.")