#!/bin/bash

OUTPUT_DIR="./ab_results"
MERGED_CSV="$OUTPUT_DIR/all_requests.csv"
mkdir -p "$OUTPUT_DIR"

PIDS=()
#total 100 ips each sending 50 requests with a c of 10 only making effective concurrency of 1000
for i in {10..109}; do
    ab -k -s 120 -n 20 -c 10 \
        -g "$OUTPUT_DIR/gnuplot_$i.dat" \
        -e "$OUTPUT_DIR/stats_$i.csv" \
        -H "Accept-Encoding: gzip, deflate" \
        -B 192.168.100.$i \
        http://192.168.100.1:5000/matmul \
        >> "$OUTPUT_DIR/ab_$i.txt" 2>&1 &
    PIDS+=($!)
done

echo "Launched ${#PIDS[@]} ab instances. Waiting..."

for pid in "${PIDS[@]}"; do
    wait "$pid"
done

echo "Merging CSVs..."

# Write header once, with an extra column for source IP
echo "source_ip,percentage,requests_served,time_ms" > "$MERGED_CSV"

for i in {10..111}; do
    CSV="$OUTPUT_DIR/stats_$i.csv"
    if [[ -f "$CSV" ]]; then
        # Skip header line, prepend source IP to each row
        tail -n +2 "$CSV" | while IFS= read -r line; do
            echo "192.168.100.$i,$line"
        done >> "$MERGED_CSV"
    fi
done

# Merge raw ab text output
cat "$OUTPUT_DIR"/ab_*.txt > "$OUTPUT_DIR/all_ab_output.txt"

# Extract key summary stats per IP into a clean summary CSV
echo "source_ip,requests_completed,failed_requests,rps,mean_latency_ms,p50_ms,p95_ms,p99_ms,transfer_rate_kbps" \
    > "$OUTPUT_DIR/summary.csv"

for i in {10..111}; do
    TXT="$OUTPUT_DIR/ab_$i.txt"
    [[ -f "$TXT" ]] || continue

    completed=$(grep "Complete requests:"   "$TXT" | awk '{print $NF}')
    failed=$(grep "Failed requests:"        "$TXT" | awk '{print $NF}')
    rps=$(grep "Requests per second:"       "$TXT" | awk '{print $4}')
    mean=$(grep "Time per request:"         "$TXT" | head -1 | awk '{print $4}')
    p50=$(grep "^ *50%"                     "$TXT" | awk '{print $2}')
    p95=$(grep "^ *95%"                     "$TXT" | awk '{print $2}')
    p99=$(grep "^ *99%"                     "$TXT" | awk '{print $2}')
    transfer=$(grep "Transfer rate:"        "$TXT" | awk '{print $3}')

    echo "192.168.100.$i,$completed,$failed,$rps,$mean,$p50,$p95,$p99,$transfer" \
        >> "$OUTPUT_DIR/summary.csv"
done

echo "Done. Files ready for graphing:"
echo "  $OUTPUT_DIR/summary.csv      — per-IP summary stats"
echo "  $OUTPUT_DIR/all_requests.csv — per-percentile latency for all IPs"
echo "  $OUTPUT_DIR/all_ab_output.txt — raw ab output"
