"""
Async SQLAlchemy engine + session factory.
"""

import ssl
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Convert postgres:// to postgresql+asyncpg:// for async driver
database_url = settings.DATABASE_URL
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

# Strip query params that asyncpg doesn't support and handle SSL
parsed = urlparse(database_url)
query_params = parse_qs(parsed.query)
needs_ssl = query_params.pop("sslmode", [None])[0] in ("require", "verify-full", "verify-ca")
query_params.pop("channel_binding", None)
clean_query = urlencode({k: v[0] for k, v in query_params.items()})
database_url = urlunparse(parsed._replace(query=clean_query))

# Build connect_args for SSL
connect_args = {}
if needs_ssl:
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    connect_args["ssl"] = ssl_ctx

engine = create_async_engine(
    database_url,
    echo=settings.ENVIRONMENT == "development",
    pool_size=5,
    max_overflow=10,
    connect_args=connect_args,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass
