#!/bin/bash
# Restarts the referee until the game actually ends (DONE in log) or 10 attempts.
D="${ARCADE_LIVE:-/tmp/chess}"
for i in $(seq 1 10); do
  grep -q "DONE:" "$D/relay2.log" && exit 0
  echo "keeper: relay attempt $i" >> "$D/relay2.log"
  "$D/relay2.sh"
  sleep 5
done
echo "keeper: gave up after 10 attempts" >> "$D/relay2.log"
