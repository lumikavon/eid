import os

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
if value := os.getenv("EID_MIGRATION_DATABASE_URL"):
    config.set_main_option("sqlalchemy.url", value)


def verify_migration_connection(connection):
    row = connection.exec_driver_sql(
        "SELECT current_database(), current_user, "
        "shobj_description(oid, 'pg_database') "
        "FROM pg_database WHERE datname=current_database()"
    ).one_or_none()
    expected = ("eid_local_dev", "eid_migrator", "eid-local-dev-v1")
    if row is None or tuple(row) != expected:
        raise RuntimeError("Migration database connection identity mismatch")


def run_migrations_offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    from scripts.verify_local_environment import verify_migration_target

    verify_migration_target(config.get_main_option("sqlalchemy.url"))
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=5000 -c lock_timeout=2000"},
    )
    with connectable.begin() as connection:
        verify_migration_connection(connection)
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_offline() if context.is_offline_mode() else run_migrations_online()
