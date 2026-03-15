import os
import json
import threading
import time
import psycopg2
from datetime import datetime
from synchrophasor.pdc import Pdc
from synchrophasor.frame import DataFrame

# --- [DYNAMIC CONFIG FROM ENV] ---
# อ่านรายชื่อ PMU ในรูปแบบ JSON String
env_pmu_list = os.environ.get("PMU_LIST", "[]")
try:
    DEVICES = json.loads(env_pmu_list)
except Exception as e:
    print(f"[PDC] Config Error: {e}")
    DEVICES = []

# --- [DATABASE CONFIG] ---
DB_HOST = os.getenv("DB_HOST", "timescaledb-edge-b-rw")
DB_NAME = os.getenv("DB_NAME", "app")
DB_USER = os.getenv("DB_USER", "app")
DB_PASS = os.getenv("DB_PASSWORD", "password")
DB_PORT = os.getenv("DB_PORT", "5432")

# --- [GLOBAL VARIABLES] ---
RETRY_DELAY = 3
MAX_RETRIES = 20
BATCH_SIZE = 50  # จำนวนแถวที่จะสะสมก่อนเขียนลง DB ครั้งเดียว
msg_count = 0
batch_data = []
count_lock = threading.Lock()

def get_db_connection():
    """ฟังก์ชันเชื่อมต่อ Database พร้อมระบบ Retry"""
    while True:
        try:
            conn = psycopg2.connect(
                host=DB_HOST, 
                database=DB_NAME, 
                user=DB_USER, 
                password=DB_PASS, 
                port=DB_PORT
            )
            print(f"✅ [DB] Connected to {DB_HOST} successfully!")
            return conn
        except Exception as e:
            print(f"❌ [DB] Connection failed: {e}. Retrying in 2s...", flush=True)
            time.sleep(2)

def connect_with_retry(label, ip, port, pdc_id):
    """ฟังก์ชันเชื่อมต่อ PMU พร้อมระบบ Retry"""
    pdc = Pdc(pdc_id=pdc_id, pmu_ip=ip, pmu_port=port)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"[PDC:{label}] Connecting to {ip}:{port} (attempt {attempt}/{MAX_RETRIES})")
            pdc.run()
            pdc.get_config()
            pdc.start()
            print(f"✅ [PDC:{label}] Connected.")
            return pdc
        except Exception as e:
            print(f"⚠️ [PDC:{label}] Failed: {e} — retry in {RETRY_DELAY}s...")
            try: pdc.stop()
            except: pass
            time.sleep(RETRY_DELAY)
            pdc = Pdc(pdc_id=pdc_id, pmu_ip=ip, pmu_port=port)
    raise RuntimeError(f"Cannot connect to {label} at {ip}:{port}")

def receive_loop(label, ip, port, pdc_id):
    """Loop ของแต่ละ Thread เพื่อดึงข้อมูลจาก PMU"""
    global msg_count
    while True:
        try:
            pdc = connect_with_retry(label, ip, port, pdc_id)
            while True:
                data = pdc.get()
                if isinstance(data, DataFrame):
                    raw = data.get_measurements()
                    ts = datetime.now() # หรือใช้เวลาจาก PMU ถ้าต้องการ

                    if 'measurements' in raw and len(raw['measurements']) > 0:
                        stream = raw['measurements'][0]
                        freq = stream.get('frequency', 0)
                        phasors = stream.get('phasors', [])
                        analogs = stream.get('analog', [])
                        
                        # แกะข้อมูล Phasors 3 ชุด (Magnitude, Angle)
                        v_a = phasors[0] if len(phasors) >= 1 else (0, 0)
                        v_b = phasors[1] if len(phasors) >= 2 else (0, 0)
                        v_c = phasors[2] if len(phasors) >= 3 else (0, 0)
                        
                        # แกะ Analog
                        ana1 = analogs[0] if len(analogs) >= 1 else 0
                        
                        # นำข้อมูลใส่ Batch ก้อนกลาง
                        with count_lock:
                            batch_data.append((
                                ts, freq, 
                                v_a[0], v_a[1], 
                                v_b[0], v_b[1], 
                                v_c[0], v_c[1], 
                                ana1
                            ))
                            msg_count += 1
        except Exception as e:
            print(f"❌ [PDC:{label}] Error: {e} — reconnecting...", flush=True)
            time.sleep(RETRY_DELAY)

if __name__ == "__main__":
    if not DEVICES:
        print("🛑 [PDC] No PMU configured. Please check PMU_LIST env.")
        while True: time.sleep(10)

    # เชื่อมต่อ Database ครั้งแรก
    db_conn = get_db_connection()

    # เริ่ม Thread สำหรับ PMU แต่ละตัว
    for dev in DEVICES:
        t = threading.Thread(
            target=receive_loop,
            # ใช้ service_name จาก JSON ที่ส่งมาจาก YAML
            args=(dev["label"], dev["service_name"], dev["port"], dev["pdc_id"]),
            daemon=True
        )
        t.start()
        print(f"🚀 [PDC] Started thread for {dev['label']}")

    last_check = time.time()
    try:
        while True:
            time.sleep(0.01) # ปล่อย CPU นิดนึง
            now = time.time()

            # --- [DATABASE BATCH INSERT] ---
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
                        (time, frequency, magnitude, angle, mag_b, ang_b, mag_c, ang_c, analog1)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    cur.executemany(query, current_batch)
                    db_conn.commit()
                    cur.close()
                except Exception as db_err:
                    print(f"🔥 [DB] Insert Error: {db_err}", flush=True)
                    db_conn.rollback()
            
            # --- [MPS PRINTING] ---
            if now - last_check >= 1.0:
                with count_lock:
                    mps = msg_count
                    msg_count = 0
                print(f"📊 REALTIME_MPS:{mps} | Pending Batch: {len(batch_data)}", flush=True)
                last_check = now

    except KeyboardInterrupt:
        print("[PDC] Shutting down...")
    finally:
        if db_conn: db_conn.close()
        print("[PDC] Connections closed.")