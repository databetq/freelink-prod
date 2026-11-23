from alembic import context
from sqlalchemy import create_engine, pool

from app import models
from app.config import get_settings

database_url = get_settings().database_url


def run_migrations() -> None:
    if context.is_offline_mode():
        context.configure(
            url=database_url,
            target_metadata=models.Base.metadata,
            literal_binds=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    def migrate(connection) -> None:
        context.configure(connection=connection, target_metadata=models.Base.metadata)
        with context.begin_transaction():
            context.run_migrations()

    connection = context.config.attributes.get("connection")
    if connection is not None:
        migrate(connection)
        return

    engine = create_engine(database_url, poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            migrate(connection)
    finally:
        engine.dispose()


run_migrations()
