from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from lakshya_backend.config import get_settings


@lru_cache
def get_engine() -> Engine:
    # pool_pre_ping: check a pooled connection is alive before using it
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def get_session() -> Session:
    """Usage: `with get_session() as session, session.begin(): ...` (commits on success)."""
    return Session(get_engine())
