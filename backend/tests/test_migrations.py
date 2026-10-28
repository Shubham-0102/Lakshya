from alembic import command


def test_downgrade_and_upgrade_again(migrated_engine, alembic_cfg):
    """Every migration can be undone and re-applied (catches a broken downgrade)."""
    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")


def test_models_match_migrations(migrated_engine, alembic_cfg):
    """Fails if a model was changed without generating a migration for it."""
    command.check(alembic_cfg)
