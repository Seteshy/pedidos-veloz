import os

import psycopg
from psycopg.rows import dict_row


def connect():
    # Parametros separados evitam interpolar senhas em uma URL.
    return psycopg.connect(
        host=os.getenv("DB_HOST", "db"),
        dbname=os.getenv("DB_NAME", "veloz"),
        user=os.getenv("DB_USER", "veloz"),
        password=os.environ["DB_PASSWORD"],
        connect_timeout=3,
        row_factory=dict_row,
    )
