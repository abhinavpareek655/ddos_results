import os
import hashlib
import asyncio
import time
import numpy as np
import csv
from datetime import datetime
from collections import defaultdict, deque
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

# FIX #1: ThreadPoolExecutor instead of ProcessPoolExecutor.
# Numpy releases the GIL during matmul, so threads work perfectly and avoid
# the 100–500 ms process-spawn + IPC overhead that ProcessPoolExecutor adds.
from concurrent.futures import ThreadPoolExecutor

app = FastAPI()
executor = ThreadPoolExecutor(max_workers=os.cpu_count())

# Thresholds
T_TIMEOUT  = 15.0   # Ttimeout: P95 latency threshold to trigger SIO
IP_LIMIT   = 20     # per-IP concurrent request limit
ROLLING_N  = 50     # window size for the rolling latency buffer

# FIX #3 (cooldown): once SIO fires we stay in shed mode for at least this
# many seconds before re-evaluating, preventing rapid oscillation.
SIO_COOLDOWN_S = 5.0

ip_counts: dict[str, int] = defaultdict(int)
ip_lock    = asyncio.Lock()

recent_times: deque[float] = deque(maxlen=ROLLING_N)
metrics_lock = asyncio.Lock()

# SIO state
sio_active          = False
sio_last_trigger_ts = 0.0   # wall-clock time when SIO was last activated

# ---------------------------------------------------------------------------
# FIX #2: async log queue + background writer
# Instead of opening/flushing the CSV file on every request (which serialises
# all requests through a lock + disk I/O), we push rows into an in-memory
# asyncio.Queue and drain it in a single background coroutine.
# ---------------------------------------------------------------------------
CSV_FILE  = "request_log.csv"
log_queue: asyncio.Queue = asyncio.Queue()

async def _log_worker():
    """Background task: drains log_queue and writes rows to CSV in batches."""
    # Open once and keep the file handle alive for the lifetime of the app.
    with open(CSV_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        while True:
            row = await log_queue.get()          # wait for the next row
            writer.writerow(row)
            # Drain any additional rows already waiting (batch write)
            while not log_queue.empty():
                writer.writerow(log_queue.get_nowait())
            f.flush()                            # one flush per batch
            log_queue.task_done()


def _init_csv():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "ip_address", "response_time_s",
                 "sio_active", "matrix_size", "status"])

_init_csv()


@app.on_event("startup")
async def startup_event():
    """Start the background CSV writer once the event loop is running."""
    asyncio.create_task(_log_worker())


def _enqueue_log(ip: str, response_time: float,
                 sio_status: bool, matrix_size):
    """Non-blocking: push a log row onto the queue (fire-and-forget)."""
    log_queue.put_nowait([
        datetime.now().isoformat(),
        ip,
        round(response_time, 6),
        sio_status,
        matrix_size,
    ])


# ---------------------------------------------------------------------------
# FIX #3: P95-based SIO check with cooldown
# The original mean-based check could be held permanently in SIO state after
# a single slow burst, blocking all future legitimate traffic.
# Using the 95th-percentile makes the trigger robust against outliers, and the
# cooldown window prevents rapid re-triggering once the system recovers.
# ---------------------------------------------------------------------------
def _check_sio(now: float) -> bool:
    """
    Activate SIO when P95 latency exceeds T_TIMEOUT.
    Once active, hold for SIO_COOLDOWN_S seconds before re-evaluating so the
    system gets a chance to drain backlogged work before checking again.
    """
    global sio_active, sio_last_trigger_ts

    if len(recent_times) == 0:
        return False

    p95 = float(np.percentile(list(recent_times), 95))

    if p95 >= T_TIMEOUT:
        sio_active          = True
        sio_last_trigger_ts = now
        return True

    # Only clear SIO after the cooldown has elapsed
    if sio_active and (now - sio_last_trigger_ts) >= SIO_COOLDOWN_S:
        sio_active = False

    return sio_active


@app.middleware("http")
async def track_and_gate(request: Request, call_next):
    ip = request.client.host if request.client else "unknown"

    async with ip_lock:
        if ip_counts[ip] >= IP_LIMIT:
            # Log the rejection before returning
            _enqueue_log(ip, 0.0, sio_active, 
                        request.query_params.get("size"), "ip_limit_rejected")
            return JSONResponse(
                status_code=200,
                content={"detail": "SIO_ACTIVE_SKIPPED_DUE_TO_LOAD",
                         "reason": "per_ip_limit"},
            )
        ip_counts[ip] += 1

    start = time.perf_counter()
    try:
        response = await call_next(request)
        return response
    finally:
        elapsed = time.perf_counter() - start
        async with metrics_lock:
            recent_times.append(elapsed)
            current_sio = _check_sio(time.time())

        _enqueue_log(ip, elapsed, current_sio,
                    request.query_params.get("size"), "served")

        async with ip_lock:
            ip_counts[ip] -= 1
            if ip_counts[ip] == 0:
                del ip_counts[ip]

def matrix_work(size: int) -> str:
    A = np.random.rand(size, size).astype(np.float64)
    B = np.random.rand(size, size).astype(np.float64)
    C = A @ B
    return hashlib.sha256(C.tobytes()).hexdigest()


@app.get("/matmul")
async def stress(size: int = Query(default=512, ge=1, le=8192)):
    if sio_active:
        return JSONResponse(
                status_code=200,
                content={
                            "matrix_size": size,
                            "sha256": "SIO_ACTIVE_SKIPPED_DUE_TO_LOAD",
                            "reason": "high_p95_latency",
                        })
    loop = asyncio.get_running_loop()
    hash_val = await loop.run_in_executor(executor, matrix_work, size)
    return {"matrix_size": size, "sha256": hash_val}


@app.get("/metrics")
async def metrics():
    async with ip_lock:
        active_ips = dict(ip_counts)
    async with metrics_lock:
        p95 = float(np.percentile(list(recent_times), 95)) if recent_times else 0.0
    return {
        "sio_active": sio_active,
        "p95_response_s": round(p95, 4),
        "active_ips": active_ips,
        "log_queue_depth": log_queue.qsize(),
    }


@app.get("/")
def root():
    return {
        "info": "GET /matmul?size=512",
        "limits": {
            "per_ip_concurrency": IP_LIMIT,
            "latency_shed_threshold_s": T_TIMEOUT,
            "sio_cooldown_s": SIO_COOLDOWN_S,
        },
    }