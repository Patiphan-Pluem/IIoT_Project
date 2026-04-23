#!/bin/bash
set -e
set -o pipefail
# --- Configuration ---
NS="edge-apps"
NODE="edge-d"
ORIGIN_DB_POD="timescaledb-2-edge-d-0"
TEMP_DB_NAME="timescaledb-temp-edge-d"
TEMP_PVC_NAME="db-storage-temp-edge-d"
SERVICE="timescaledb-service-edge-d"

echo "[$(date)] Starting Maintenance ..."

echo ">>> [Pre-Maintenance Step 1/4] Creating new DB on cloud node..."

# 1. สร้าง PVC และ Deployment สำหรับ DB ชั่วคราว
echo "Creating PVC and Temporary Database on Cloud Node..."
kubectl apply -f - <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: $TEMP_PVC_NAME
  namespace: $NS
spec:
  accessModes: [ "ReadWriteOnce" ]
  storageClassName: local-path
  resources:
    requests:
      storage: 0.5Gi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: $TEMP_DB_NAME
  namespace: $NS
spec:
  replicas: 1
  selector:
    matchLabels:
      app: $TEMP_DB_NAME
  template:
    metadata:
      labels:
        app: $TEMP_DB_NAME
    spec:
      nodeSelector:
        kubernetes.io/hostname: cloud-node
      containers:
      - name: timescaledb
        image: timescale/timescaledb:latest-pg14
        env:
        - name: POSTGRES_PASSWORD
          value: "password"
        ports:
        - containerPort: 5432
        volumeMounts:
        - name: storage
          mountPath: /var/lib/postgresql/data
      volumes:
      - name: storage
        persistentVolumeClaim:
          claimName: $TEMP_PVC_NAME
EOF

# 2. รอจนกว่า DB ชั่วคราวจะ Ready
MIGRATE_START=$(date +%s)
echo "Waiting for Temp DB to be ready..."
kubectl wait --for=condition=ready pod -l app=$TEMP_DB_NAME -n $NS --timeout=60s
echo -n "Waiting for Temp Postgres to accept connections "
until kubectl exec deployment/$TEMP_DB_NAME -n $NS -- pg_isready -U postgres > /dev/null 2>&1; do
    echo -n ". "
    sleep 1
done
echo " Ready!"

# 3. สร้าง Table ใน DB ใหม่
echo "    Initializing schema in Temp DB..."
kubectl exec -i deployment/$TEMP_DB_NAME -n $NS -- psql -U postgres << 'SQL'
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'
    ) THEN
        CREATE EXTENSION timescaledb CASCADE;
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS pmu_measurements (
    time TIMESTAMPTZ NOT NULL,
    frequency FLOAT,
    mag_a FLOAT, ang_a FLOAT,
    mag_b FLOAT, ang_b FLOAT,
    mag_c FLOAT, ang_c FLOAT
);

SELECT create_hypertable('pmu_measurements', 'time', if_not_exists => TRUE);
SQL

echo "    [Step 1 Done] Temp DB on cloud node is ready."

echo ""
echo ">>> [Pre-Maintenance Step 2/4] Changing DB service endpoint to Temp DB (cloud node)..."

# 4. สลับ Service
echo "Switching traffic to Temp DB..."
kubectl patch svc $SERVICE -n $NS -p "{\"spec\":{\"selector\":{\"app\":\"$TEMP_DB_NAME\"}}}"

echo "Forcing disconnect on Origin DB..."
kubectl exec $ORIGIN_DB_POD -n $NS -- psql -U postgres -d postgres -c \
"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'postgres' AND pid <> pg_backend_pid();" > /dev/null

echo "    [Step 2 Done] Traffic is now routed to Temp DB."

echo ""
echo ">>> [Pre-Maintenance Step 3/4] Copying last 10 minutes of data from edge DB to Temp DB..."

# 5. ก๊อปปี้ข้อมูลล่าสุด (10 นาที)
echo "Migrating last 10 mins of data..."

CUTOFF_TIME=$(kubectl exec $ORIGIN_DB_POD -n $NS -- psql -U postgres -d postgres -t -A -c "SELECT max(time) FROM pmu_measurements;")
START_TIME=$(kubectl exec $ORIGIN_DB_POD -n $NS -- psql -U postgres -d postgres -t -A -c "SELECT '$CUTOFF_TIME'::timestamptz - INTERVAL '10 minutes';")

echo "Data Window: $START_TIME to $CUTOFF_TIME"
EXPECTED_ROWS=$(kubectl exec $ORIGIN_DB_POD -n $NS -- psql -U postgres -d postgres -t -A -c \
"SELECT COUNT(*) FROM pmu_measurements WHERE time > '$START_TIME' AND time <= '$CUTOFF_TIME';")
echo "Expected rows: $EXPECTED_ROWS"

kubectl exec $ORIGIN_DB_POD -n $NS -- psql -U postgres -d postgres -c \
"COPY (SELECT * FROM pmu_measurements WHERE time > '$START_TIME') TO STDOUT" \
| kubectl exec -i deployment/$TEMP_DB_NAME -n $NS -- psql -U postgres -d postgres -c "COPY pmu_measurements FROM STDIN"

ACTUAL_ROWS=$(kubectl exec deployment/$TEMP_DB_NAME -n $NS -- psql -U postgres -d postgres -t -A -c \
"SELECT COUNT(*) FROM pmu_measurements WHERE time > '$START_TIME' AND time <= '$CUTOFF_TIME';")
echo "Actual rows: $ACTUAL_ROWS"

if [ "$EXPECTED_ROWS" -ne "$ACTUAL_ROWS" ]; then
    echo "ERROR: Verification failed! Expected $EXPECTED_ROWS, got $ACTUAL_ROWS."
    exit 1
else
    echo "Verification passed!"
fi
MIGRATE_END=$(date +%s)   
MIGRATE_DUR=$((MIGRATE_END - MIGRATE_START))
echo "    [Step 3 Done] Data migration complete. ($((MIGRATE_DUR / 60))m $((MIGRATE_DUR % 60))s)"

echo ""
echo ">>> [Pre-Maintenance Step 4/4] Cordoning and draining edge node: $NODE..."

# 6. Drain Node
echo "Draining node $NODE..."
DRAIN_START=$(date +%s)
kubectl drain $NODE --ignore-daemonsets --force --delete-emptydir-data
DRAIN_END=$(date +%s)      
DRAIN_DUR=$((DRAIN_END - DRAIN_START))
echo "    [Step 4 Done] Node drained. All pods rescheduled to cloud node. ($((DRAIN_DUR / 60))m $((DRAIN_DUR % 60))s)"


echo "[$(date)] Maintenance Mode Active."
SCRIPT_END_TIME=$(date +%s)
TOTAL_DUR=$((MIGRATE_DUR + DRAIN_DUR))

echo "========================================"
echo "Execution Time Summary:"
echo " [Step 1-3] Database Migration Time : $((MIGRATE_DUR / 60))m $((MIGRATE_DUR % 60))s"
echo " [Step 4]   Node Draining Time      : $((DRAIN_DUR / 60))m $((DRAIN_DUR % 60))s"
echo " Total execution time               : $((TOTAL_DUR / 60))m $((TOTAL_DUR % 60))s"
echo "========================================"