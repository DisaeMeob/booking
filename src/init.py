import hashlib
from typing import Any, Callable
from starlette.requests import Request
from starlette.responses import Response

from src.connectors.redis_connector import RedisManager
from src.config import settings


def custom_key_builder(
    func: Callable[..., Any],
    namespace: str = "",
    *,
    request: Request | None = None,
    response: Response | None = None,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> str:
    func_identifier = f"{func.__module__}:{func.__name__}"

    if request:
        method = request.method
        path = request.url.path
        query_items = sorted(request.query_params.multi_items())
        raw_key = f"{func_identifier}:{method}:{path}:{query_items}"
    else:
        filtered_kwargs = {
            k: v for k, v in kwargs.items()
            if not hasattr(v, "session") and not isinstance(v, (Request, Response))
        }
        raw_key = f"{func_identifier}:{args}:{sorted(filtered_kwargs.items())}"

    cache_hash = hashlib.md5(raw_key.encode()).hexdigest()
    return f"{namespace}:{cache_hash}"


redis_manager = RedisManager(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT
)
