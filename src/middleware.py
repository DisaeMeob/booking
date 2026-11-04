from fastapi import Request
import time

from core.logger import logger

async def middleware_logger(request: Request, call_next):
    start = time.perf_counter()

    response = await call_next(request)

    process_time = time.perf_counter() - start

    response.headers['X-Process-Time'] = f'{process_time:.4f}'

    logger.info(
        "%s | %s | %s | %d | %.4fs",
        request.client.host,
        request.method,
        request.url.path,
        response.status_code,
        process_time,
    )

    return response