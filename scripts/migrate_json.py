from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.core.exceptions import NotFoundError
from app.core.logging import configure_logging, get_logger
from app.core.utils import slugify
from app.domain.repositories import BotRepository, CategoryRepository, GroupRepository
from app.domain.services import BotService, CategoryService, GroupService
from app.infrastructure.db.base import get_session

logger = get_logger(__name__)


async def import_from_json(path: Path) -> None:
    with path.open("r", encoding="utf-8") as fp:
        payload = json.load(fp)

    async with get_session() as session:
        category_service = CategoryService(CategoryRepository(session))
        group_service = GroupService(GroupRepository(session))
        bot_service = BotService(BotRepository(session))

        for bot_data in payload.get("bots", []):
            name = bot_data["name"]
            token = bot_data["token"]
            status = bot_data.get("status", "active")
            await bot_service.register_bot(name=name, token=token, status=status)
            logger.info("import.bot", name=name)

        for category_data in payload.get("categories", []):
            name = category_data["name"]
            slug = category_data.get("slug") or slugify(name)
            try:
                category = await category_service.get_category_by_slug(slug)
            except NotFoundError:
                category = await category_service.create_category(name)
            logger.info("import.category", name=name, id=category.id)

            for media in category_data.get("media", []):
                await category_service.add_media(
                    category.id,
                    media_type=media["media_type"],
                    file_id=media["file_id"],
                    caption=media.get("caption"),
                    weight=media.get("weight", 1),
                )

            for copy in category_data.get("copies", []):
                await category_service.add_copy(
                    category.id,
                    text=copy["text"],
                    weight=copy.get("weight", 1),
                )

            for button in category_data.get("buttons", []):
                await category_service.add_button(
                    category.id,
                    label=button["label"],
                    url=button["url"],
                    weight=button.get("weight", 1),
                )

            for group in category_data.get("groups", []):
                await group_service.upsert_group(
                    chat_id=int(group["chat_id"]),
                    title=group.get("title"),
                    category_id=category.id,
                )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Importa categorias e bots a partir de JSON.")
    parser.add_argument("path", type=Path, help="Caminho para o arquivo JSON.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging()
    asyncio.run(import_from_json(args.path))


if __name__ == "__main__":
    main()

