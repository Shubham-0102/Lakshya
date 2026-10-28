"""Alembic migration environment.

The database URL comes from Settings (.env), not from a config file. Tests point
Alembic at the test database by setting `sqlalchemy.url` on the Alembic Config.
"""

import logging

from alembic import context
from sqlalchemy import create_engine, pool

from lakshya_backend.config import get_settings
from lakshya_backend.db import models  # noqa: F401  (importing registers the tables)
from lakshya_backend.db.base import Base

logging.basicConfig(format="%(levelname)-5.5s [%(name)s] %(message)s")
logging.getLogger("alembic").setLevel(logging.INFO)
logging.getLogger("alembic.runtime.plugins").setLevel(logging.WARNING)  # one line per plugin

config = context.config
target_metadata = Base.metadata


def database_url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql`: print the SQL instead of running it."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
