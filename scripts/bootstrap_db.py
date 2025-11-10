from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    config_path = settings.alembic_config or Path("app/infrastructure/db/migrations/alembic.ini")
    alembic_cfg = Config(str(config_path))
    if not alembic_cfg.get_main_option("sqlalchemy.url"):
        alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)

    logger.info("alembic.upgrade", config=str(config_path))
    command.upgrade(alembic_cfg, "head")


if __name__ == "__main__":
    main()

