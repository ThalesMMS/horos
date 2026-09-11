#!/usr/bin/env bash
# Continuous DICOM routing under load, with one destination taken away and
# brought back, so queue depth, import latency, memory and the number of alerts
# raised can be measured rather than guessed.
#
# Expects a development build already running with -AUTOROUTINGACTIVATED YES,
# two routing rules pointing at two tools/serve-store-fixture.py SCPs on the
# ports below, and a python with pydicom. See docs/native-validation-harness.md.
set -u
if [ $# -lt 2 ]; then
  echo "usage: $0 <work-directory> <python-with-pydicom> [batches] [instances] [down-at] [up-at]" >&2
  exit 2
fi
WORK="$1"; PYTHON="$2"; BATCHES="${3:-10}"; INSTANCES="${4:-12}"; DOWN_AT="${5:-4}"; UP_AT="${6:-8}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_ROOT="${HOROS_DEV_TEST_ROOT:-$ROOT/local-validation/runtime-private}"
INCOMING="$TEST_ROOT/Horos Data/INCOMING.noindex"
[ -d "$INCOMING" ] || { echo "No incoming folder at $INCOMING" >&2; exit 1; }
PID=$(pgrep -f "Contents/MacOS/Horos -DATABASELOCATION" | head -1)
[ -n "$PID" ] || { echo "No development build running" >&2; exit 1; }
mkdir -p "$WORK"
echo "app pid $PID, $BATCHES batches of $INSTANCES instances"
echo "batch,seconds,rss_kb" > "$WORK/metrics.csv"

for i in $(seq 1 "$BATCHES"); do
  if [ "$i" = "$DOWN_AT" ]; then
    echo "--- taking the second destination down (batch $i) ---"
    pkill -f "serve-store-fixture.py.*11182"
  fi
  if [ "$i" = "$UP_AT" ]; then
    echo "--- bringing it back (batch $i) ---"
    nohup "$PYTHON" "$ROOT/tools/serve-store-fixture.py" "$WORK/second-again" --port 11182 \
      --aetitle PACSB > "$WORK/second-again.log" 2>&1 &
    for _ in $(seq 1 20); do nc -z 127.0.0.1 11182 2>/dev/null && break; sleep 1; done
  fi
  rm -rf "$WORK/batch$i"; mkdir -p "$WORK/batch$i"
  "$PYTHON" "$ROOT/tools/generate-store-fixture.py" "$WORK/batch$i" \
    --ct-instances "$INSTANCES" --us-instances 0 > /dev/null 2>&1
  start=$(python3 -c "import time;print(time.time())")
  cp "$WORK/batch$i"/ct-*.dcm "$INCOMING/"
  for _ in $(seq 1 120); do
    [ "$(ls -A "$INCOMING" 2>/dev/null | wc -l | tr -d ' ')" = "0" ] && break
    sleep 0.5
  done
  end=$(python3 -c "import time;print(time.time())")
  rss=$(ps -o rss= -p "$PID" 2>/dev/null | tr -d ' ')
  python3 -c "print('%d,%.2f,%s' % ($i, $end-$start, '${rss:-0}'))" >> "$WORK/metrics.csv"
  sleep 4
done

echo "--- letting the queue drain ---"
sleep 45
echo "metrics in $WORK/metrics.csv; sample the application with: sample $PID 3"
