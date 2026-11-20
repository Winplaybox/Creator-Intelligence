Migrations are managed with Alembic from the API working directory.

- Run `alembic upgrade head` to apply migrations.
- Run `alembic downgrade -1` only after reviewing the rollback and backing up data.
- Never run destructive migrations automatically in production without a reviewed backup.