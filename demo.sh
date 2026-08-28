#!/bin/bash
set -e

echo "=== Demo 1: Successful run ==="
rm -f demo.db
RUNS_DB_PATH=demo.db uvicorn src.main:app --port 8124 &
SERVER_PID=$!
sleep 1

RUN_ID=$(curl -s -X POST localhost:8124/runs -H "Content-Type: application/json" \
  -d '{"task": "what is 6 times 7?"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['run_id'])")
echo "Started run: $RUN_ID"
sleep 2
curl -s localhost:8124/runs/$RUN_ID | python3 -m json.tool

echo ""
echo "=== Demo 2: Tool failures + retries (uses CalculatorTool's simulated 20% failure rate) ==="
RUN_ID2=$(curl -s -X POST localhost:8124/runs -H "Content-Type: application/json" \
  -d '{"task": "calculate something with retries"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['run_id'])")
sleep 2
curl -s localhost:8124/runs/$RUN_ID2 | python3 -c "
import sys, json
data = json.load(sys.stdin)
for e in data['events']:
    if 'tool_call' in e['event_type']:
        print(e['event_type'], e['payload'])
"

kill $SERVER_PID
wait $SERVER_PID 2>/dev/null

echo ""
echo "=== Demo 3: Kill mid-run and resume ==="
rm -f demo.db
RUNS_DB_PATH=demo.db uvicorn src.main:app --port 8124 &
SERVER_PID=$!
sleep 1

RUN_ID3=$(curl -s -X POST localhost:8124/runs -H "Content-Type: application/json" \
  -d '{"task": "a task that will be interrupted"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['run_id'])")
echo "Started run: $RUN_ID3"
sleep 0.5

echo "Killing server (SIGKILL, simulating a crash)..."
kill -9 $SERVER_PID
sleep 0.5

echo "Events persisted before kill:"
sqlite3 demo.db "SELECT event_type FROM events WHERE run_id='$RUN_ID3';"

echo "Restarting server (same DB)..."
RUNS_DB_PATH=demo.db uvicorn src.main:app --port 8124 &
SERVER_PID=$!
sleep 1

echo "Resumed run status:"
sleep 2
curl -s localhost:8124/runs/$RUN_ID3 | python3 -m json.tool

kill $SERVER_PID