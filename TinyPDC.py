from synchrophasor.pdc import Pdc
from synchrophasor.frame import DataFrame
import os
import time
import psycopg2
from datetime import datetime

# Database Settings
DB_HOST = os.getenv("DB_HOST", "timescaledb-service.edge-apps")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "password")
DB_PORT = "5432"

def get_db_connection():
    while True:
        try:
            conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS, port=DB_PORT)
            print("Connected to TimescaleDB successfully!")
            return conn
        except Exception as e:
            print(f"Failed to connect to DB: {e}. Retrying in 2s...", flush=True)
            time.sleep(2)

def init_db(conn):
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pmu_measurements (
                time TIMESTAMPTZ NOT NULL,
                frequency DOUBLE PRECISION,
                magnitude DOUBLE PRECISION, angle DOUBLE PRECISION,
                mag_b DOUBLE PRECISION, ang_b DOUBLE PRECISION,
                mag_c DOUBLE PRECISION, ang_c DOUBLE PRECISION
            );
        """)
        alter_queries = [
            "ALTER TABLE pmu_measurements ADD COLUMN IF NOT EXISTS mag_b DOUBLE PRECISION;",
            "ALTER TABLE pmu_measurements ADD COLUMN IF NOT EXISTS ang_b DOUBLE PRECISION;",
            "ALTER TABLE pmu_measurements ADD COLUMN IF NOT EXISTS mag_c DOUBLE PRECISION;",
            "ALTER TABLE pmu_measurements ADD COLUMN IF NOT EXISTS ang_c DOUBLE PRECISION;"
        ]
        for q in alter_queries:
            try: cur.execute(q)
            except: pass
            
        try: cur.execute("SELECT create_hypertable('pmu_measurements', 'time', if_not_exists => TRUE);")
        except: pass
            
        conn.commit()
        cur.close()
    except Exception as e:
        print(f"Init DB Error: {e}")

if __name__ == "__main__":
    conn = get_db_connection()
    init_db(conn)
    
    target_ip = os.getenv("PMU_IP", "pmu-service.edge-apps")
    target_port = 1410
    pdc = Pdc(pdc_id=1410, pmu_ip=target_ip, pmu_port=target_port)

    # Loop เชื่อมต่อ
    while True:
        try:
            pdc.run()
            print("Connected to PMU successfully!")
            break
        except Exception:
            print("Connection failed, retrying...")
            time.sleep(2)

    pdc.get_header()
    pdc.get_config()
    pdc.start()
    print("Start Streaming...", flush=True)

    # --- ระบบ Batch Insert ---
    batch_data = []
    BATCH_SIZE = 30 # เก็บครบ 30 ตัว (1 วินาที) ค่อยบันทึกทีเดียว

    while True:
        try:
            data = pdc.get()
            if not data:
                time.sleep(0.01)
                continue
            
            if isinstance(data, DataFrame):
                raw = data.get_measurements()
                timestamp = datetime.fromtimestamp(raw['time'])
                
                if 'measurements' in raw and len(raw['measurements']) > 0:
                    stream = raw['measurements'][0]
                    freq = stream['frequency']
                    phasors = stream.get('phasors', [])
                    
                    ma, aa, mb, ab, mc, ac = 0,0,0,0,0,0
                    if len(phasors) >= 1: ma, aa = phasors[0]
                    if len(phasors) >= 2: mb, ab = phasors[1]
                    if len(phasors) >= 3: mc, ac = phasors[2]

                    # เก็บลงถุง (Buffer)
                    batch_data.append((timestamp, freq, ma, aa, mb, ab, mc, ac))

                    # ถ้าเต็มถุงแล้วค่อยเทลง DB
                    if len(batch_data) >= BATCH_SIZE:
                        try:
                            cur = conn.cursor()
                            query = """
                                INSERT INTO pmu_measurements 
                                (time, frequency, magnitude, angle, mag_b, ang_b, mag_c, ang_c)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """
                            cur.executemany(query, batch_data) # ใช้ executemany เร็วกว่ามาก
                            conn.commit()
                            cur.close()
                            
                            print(f"Saved Batch: {len(batch_data)} records. Last Time: {timestamp}", flush=True)
                            batch_data = [] # ล้างถุง
                            
                        except Exception as db_err:
                            print(f"DB Error: {db_err}")
                            conn.rollback()

        except Exception as e:
            print(f"PDC Error: {e}", flush=True)
            time.sleep(1)