from __future__ import annotations

import os
from typing import Any, TypedDict

from dotenv import load_dotenv

load_dotenv()


class DbConfig(TypedDict):
    host: str
    port: int
    dbname: str
    user: str
    password: str


DB_CONFIG: DbConfig = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "db"),
    "user": os.getenv("DB_USER", "user"),
    "password": os.getenv("DB_PASSWORD", "password"),
}


def connection_kwargs(**overrides: Any) -> dict[str, Any]:
    return {**DB_CONFIG, **overrides}


def get_db_connection(**overrides: Any):
    import psycopg2
    return psycopg2.connect(**connection_kwargs(**overrides))
