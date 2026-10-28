"""Test fixtures shared by backend/tests and scraper/tests.

Database tests run against TEST_DATABASE_URL (the lakshya_test database). The schema is
rebuilt from the migrations once per test run, and every test runs inside a transaction
that is rolled back afterwards, so tests never see each other's data.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from lakshya_backend.config import get_settings

ROOT = Path(__file__).parent


def alembic_config(database_url: str) -> Config:
    config = Config(toml_file=str(ROOT / "pyproject.toml"))
    # Config values use %-interpolation, so a % in a password must be escaped
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = get_settings().test_database_url
    if not url:
        pytest.fail("TEST_DATABASE_URL is not set. Copy .env.example to .env.")
    # The fixture below wipes this database, so never let it point at real data
    if not make_url(url).database.endswith("_test"):
        pytest.fail(f"TEST_DATABASE_URL must name a database ending in _test, got {url!r}")
    return url


@pytest.fixture(scope="session")
def alembic_cfg(test_database_url: str) -> Config:
    return alembic_config(test_database_url)


@pytest.fixture(scope="session")
def migrated_engine(test_database_url: str, alembic_cfg: Config) -> Engine:
    engine = create_engine(test_database_url)
    try:
        with engine.begin() as connection:
            # Start from an empty database, whatever an earlier run left behind
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
    except OperationalError as error:
        pytest.fail(f"Can't reach the test database. Run `docker compose up -d`.\n{error}")
    command.upgrade(alembic_cfg, "head")
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def redis_client() -> Redis:
    """Tests use unique keys (e.g. a uuid in the name), so they don't clash with real runs."""
    client = Redis.from_url(get_settings().redis_url)
    try:
        client.ping()
    except RedisConnectionError as error:
        pytest.fail(f"Can't reach Redis. Run `docker compose up -d`.\n{error}")
    yield client
    client.close()


@pytest.fixture
def db_session(migrated_engine: Engine) -> Session:
    """A session whose changes are rolled back after the test, even if the code commits."""
    with migrated_engine.connect() as connection:
        transaction = connection.begin()
        # session.commit() inside the test only releases a savepoint; the outer
        # transaction is still rolled back below
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        yield session
        session.close()
        transaction.rollback()
