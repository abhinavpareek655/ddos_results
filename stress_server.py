import os
import hashlib
import asyncio
import time
import numpy as np
import csv
from datetime import datetime
from collections import deque
from fastapi import FastAPI, Query, Request
from concurrent.futures import ThreadPoolExecutor

app = FastAPI()
executor = ThreadPoolExecutor(max_workers=os.cpu_count())

T_TIMEOUT      = 15.0
SIO_COOLDOWN_S = 5.0
ROLLING_N      = 100

recent_times: deque[float] = deque(maxlen=ROLLING_N)
metrics_lock = asyncio.Lock()

sio_active          = False
sio_last_trigger_ts = 0.0

CSV_FILE  = "request_log.csv"
log_queue: asyncio.Queue = asyncio.Queue()


def _init_csv():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, "w", newline="") as f:
            csv.writer(f).writerow(["timestamp", "ip_address", "response_time_s", "sio_active", "matrix_size"])

_init_csv()


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(_log_worker())


async def _log_worker():
    with open(CSV_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        while True:
            row = await log_queue.get()
            writer.writerow(row)
            while not log_queue.empty():
                writer.writerow(log_queue.get_nowait())
            f.flush()
            log_queue.task_done()


def _enqueue_log(ip: str, response_time: float, sio_status: bool, matrix_size):
    log_queue.put_nowait([datetime.now().isoformat(), ip, round(response_time, 6), sio_status, matrix_size])


def _check_sio(now: float) -> bool:
    global sio_active, sio_last_trigger_ts

    if not recent_times:
        return False

    p95 = float(np.percentile(list(recent_times), 95))

    if p95 >= T_TIMEOUT:
        sio_active = True
        sio_last_trigger_ts = now
        return True

    if sio_active and (now - sio_last_trigger_ts) >= SIO_COOLDOWN_S:
        sio_active = False

    return sio_active


@app.middleware("http")
async def track_latency(request: Request, call_next):
    ip = request.client.host if request.client else "unknown"
    start = time.perf_counter()
    try:
        response = await call_next(request)
        return response
    finally:
        elapsed = time.perf_counter() - start
        async with metrics_lock:
            recent_times.append(elapsed)
            current_sio = _check_sio(time.time())
        _enqueue_log(ip, elapsed, current_sio, request.query_params.get("size"))


def matrix_work(size: int) -> str:
    A = np.random.rand(size, size).astype(np.float64)
    B = np.random.rand(size, size).astype(np.float64)
    C = A @ B
    return hashlib.sha256(C.tobytes()).hexdigest()


@app.get("/matmul")
async def matmul(size: int = Query(default=2048, ge=1, le=8192)):
    if sio_active:
        return {"matrix_size": size, "sha256": "SIO_ACTIVE_SKIPPED_DUE_TO_LOAD", "reason": "high_p95_latency"}
    loop = asyncio.get_running_loop()
    hash_val = await loop.run_in_executor(executor, matrix_work, size)
    return {"matrix_size": size, "sha256": hash_val}