import os, hashlib, asyncio
import numpy as np
from fastapi import FastAPI, Query
from concurrent.futures import ThreadPoolExecutor

app = FastAPI()
executor = ThreadPoolExecutor(max_workers=os.cpu_count())

def matrix_work(size: int) -> str:
    A = np.random.rand(size, size).astype(np.float64)
    B = np.random.rand(size, size).astype(np.float64)
    C = A @ B
    return hashlib.sha256(C.tobytes()).hexdigest(), C

@app.get("/matmul")
async def stress(size: int = Query(default=2048, ge=1, le=8192)):
    loop = asyncio.get_event_loop()
    hash_val, result = await loop.run_in_executor(executor, matrix_work, size)
    return {"matrix_size": size, "sha256": hash_val}

@app.get("/")
def root():
    return {"info": "GET /matmul?size=512  — matrix multiply stress test"}