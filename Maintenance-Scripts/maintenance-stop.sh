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

echo "[$(date)] Finishing Maintenance..."

echo ">>> [Post-Maintenance Step 1/4] Uncordoning edge node: $NODE..."

RECOVERY_START=$(date +%s)

# 1. Uncordon Node
echo "Uncordoning node $NODE..."
kubectl uncordon $NODE

# 2. รอ DB หลักกลับมาออนไลน์
echo "Waiting for $ORIGIN_DB_POD to be ready..."
kubectl wait --for=condition=ready pod/$ORIGIN_DB_POD -n $NS --timeout=120s
echo -n "Waiting for Postgres service to be fully up..."
until kubectl exec $ORIGIN_DB_POD -n $NS -- pg_isready -U postgres > /dev/null 2>&1; do
    echo -n ". "
    sleep 1 
done
echo " Ready!"

echo "    [Step 1 Done] Edge node is back online. All pods recreated on edge node."

# 3. หาเวลาล่าสุดใน DB หลัก
echo "Migrating data back..."
LAST_TIME=$(kubectl exec $ORIGIN_DB_POD -n $NS -- psql -U postgres -d postgres -t -A -c "SELECT max(time) FROM pmu_measurements;")
CUTOFF_TIME=$(kubectl exec deployment/$TEMP_DB_NAME -n $NS -- psql -U postgres -d postgres -t -A -c "SELECT max(time) FROM pmu_measurements;")
echo "Data Window:: $LAST_TIME to $CUTOFF_TIME"

echo ">>> [Post-Maintenance Step 2/4] Changing DB service endpoint back to Origin DB (edge node)..."

# 4. สลับ Service กลับ
echo "Switching traffic back to Origin DB..."
kubectl patch svc $SERVICE -n $NS -p "{\"spec\":{\"selector\":{\"app\":\"timescaledb-test-edge-d\"}}}"

echo "Forcing disconnect on Temp DB..."
kubectl exec deployment/$TEMP_DB_NAME -n $NS -- psql -U postgres -d postgres -c \
"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'postgres' AND pid <> pg_backend_pid();" > /dev/null

echo "    [Step 2 Done] Traffic is now routed back to Origin DB."

echo ""
echo ">>> [Post-Maintenance Step 3/4] Syncing all data collected during maintenance back to Origin DB..."

# 5. Sync ข้อมูลช่วงที่ซ่อมบำรุงกลับมา
echo "Syncing data back from Temp DB..."
EXPECTED_ROWS=$(kubectl exec deployment/$TEMP_DB_NAME -n $NS -- psql -U postgres -d postgres -t -A -c \
"SELECT COUNT(*) FROM pmu_measurements WHERE time > '$LAST_TIME' AND time <= '$CUTOFF_TIME';")
echo "Expected rows to sync: $EXPECTED_ROWS"

kubectl exec deployment/$TEMP_DB_NAME -n $NS -- psql -U postgres -d postgres -c \
"COPY (SELECT * FROM pmu_measurements WHERE time > '$LAST_TIME') TO STDOUT" \
| kubectl exec -i $ORIGIN_DB_POD -n $NS -- psql -U postgres -d postgres -c "COPY pmu_measurements FROM STDIN"

ACTUAL_ROWS=$(kubectl exec $ORIGIN_DB_POD -n $NS -- psql -U postgres -d postgres -t -A -c \
"SELECT COUNT(*) FROM pmu_measurements WHERE time > '$LAST_TIME' AND time <= '$CUTOFF_TIME';")
echo "Actual synced rows: $ACTUAL_ROWS"

if [ "$EXPECTED_ROWS" -ne "$ACTUAL_ROWS" ]; then
    echo "ERROR: Sync verification failed! Expected $EXPECTED_ROWS, got $ACTUAL_ROWS."
    exit 1
else
    echo "Verification passed!"
fi

RECOVERY_END=$(date +%s)
RECOVERY_DUR=$((RECOVERY_END - RECOVERY_START))

echo "    [Step 3 Done] Data sync complete. ($((RECOVERY_DUR / 60))m $((RECOVERY_DUR % 60))s)"

echo ""
echo ">>> [Post-Maintenance Step 4/4] Deleting Temp DB on cloud node and restarting edge services..."

CLEANUP_START=$(date +%s)
# 6. ลบ Deployment และ PVC ทิ้ง (Clean up)
echo "Removing Temporary Database and PVC..."
kubectl delete deployment $TEMP_DB_NAME -n $NS
kubectl delete pvc $TEMP_PVC_NAME -n $NS

# 7. Restart แอป
echo "Restarting Applications..."
kubectl rollout restart deployment ems-producer-edge-d -n $NS
kubectl rollout restart deployment ems-worker-edge-d -n $NS
kubectl rollout restart deployment pdc-edge-d -n $NS

echo "[$(date)] All systems back to normal!"
CLEANUP_END=$(date +%s)
CLEANUP_DUR=$((CLEANUP_END - CLEANUP_START))
echo "    [Step 4 Done] Temp DB deleted. All edge services restarted. ($((CLEANUP_DUR / 60))m $((CLEANUP_DUR % 60))s)"

TOTAL_DUR=$((RECOVERY_DUR + CLEANUP_DUR))

echo "========================================"
echo "Execution Time Summary:"
echo " [Step 1-3] Database Sync-Back Time   : $((RECOVERY_DUR / 60))m $((RECOVERY_DUR % 60))s"
echo " [Step 4]   Service Restoration Time  : $((CLEANUP_DUR / 60))m $((CLEANUP_DUR % 60))s"
echo " Total execution time                 : $((TOTAL_DUR / 60))m $((TOTAL_DUR % 60))s"
echo "========================================"