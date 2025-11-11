from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.core.exceptions import AlreadyExistsError, NotFoundError
from app.infrastructure.db.models import (
    Bot,
    Button,
    Category,
    Copy,
    Group,
    Media,
    MediaRepositoryMap,
)


class CategoryRepository:
    def __init__(self, session):
        self.session = session

    async def list(self) -> Sequence[Category]:
        stmt = select(Category).options(
            selectinload(Category.media_items),
            selectinload(Category.copies),
            selectinload(Category.buttons),
        )
        result = await self.session.scalars(stmt)
        categories = result.unique().all()
        for category in categories:
            category.buttons.sort(key=lambda b: (b.weight or 0, b.id))
        return categories

    async def get_by_slug(self, slug: str) -> Category:
        stmt = (
            select(Category)
            .where(Category.slug == slug)
            .options(
                selectinload(Category.media_items),
                selectinload(Category.copies),
                selectinload(Category.buttons),
            )
        )
        category = await self.session.scalar(stmt)
        if not category:
            raise NotFoundError(f"Category {slug!r} not found.")
        category.buttons.sort(key=lambda b: (b.weight or 0, b.id))
        return category

    async def get_by_id(self, category_id: int) -> Category:
        stmt = (
            select(Category)
            .where(Category.id == category_id)
            .options(
                selectinload(Category.media_items),
                selectinload(Category.copies),
                selectinload(Category.buttons),
            )
        )
        category = await self.session.scalar(stmt)
        if not category:
            raise NotFoundError(f"Category id {category_id} not found.")
        category.buttons.sort(key=lambda b: (b.weight or 0, b.id))
        return category

    async def create(self, name: str) -> Category:
        category = Category(name=name, slug="")
        category.set_slug()
        self.session.add(category)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise AlreadyExistsError(f"Category {name} already exists.") from exc
        return category

    async def add_media(self, category_id: int, *, media_type: str, file_id: str, caption: str | None, weight: int) -> Media:
        media = Media(
            category_id=category_id,
            media_type=media_type,
            file_id=file_id,
            caption=caption,
            weight=weight,
        )
        self.session.add(media)
        await self.session.flush()
        return media

    async def media_exists(self, category_id: int, file_id: str) -> bool:
        stmt = select(Media.id).where(Media.category_id == category_id, Media.file_id == file_id)
        result = await self.session.scalar(stmt)
        return result is not None

    async def add_copy(self, category_id: int, *, text: str, weight: int) -> Copy:
        copy = Copy(category_id=category_id, text=text, weight=weight)
        self.session.add(copy)
        await self.session.flush()
        return copy

    async def get_copy(self, copy_id: int) -> Copy:
        copy = await self.session.get(Copy, copy_id)
        if not copy:
            raise NotFoundError(f"Copy id {copy_id} not found.")
        return copy

    async def update_copy(self, copy_id: int, *, text: str, weight: int) -> Copy:
        stmt = (
            update(Copy)
            .where(Copy.id == copy_id)
            .values(text=text, weight=weight)
            .returning(Copy)
        )
        result = await self.session.execute(stmt)
        copy = result.scalar_one_or_none()
        if not copy:
            raise NotFoundError(f"Copy id {copy_id} not found.")
        return copy

    async def add_button(self, category_id: int, *, label: str, url: str, weight: int) -> Button:
        button = Button(category_id=category_id, label=label, url=url, weight=weight)
        self.session.add(button)
        await self.session.flush()
        return button

    async def get_button(self, button_id: int) -> Button:
        button = await self.session.get(Button, button_id)
        if not button:
            raise NotFoundError(f"Button id {button_id} not found.")
        return button

    async def update_button(self, button_id: int, *, label: str, url: str, weight: int) -> Button:
        stmt = (
            update(Button)
            .where(Button.id == button_id)
            .values(label=label, url=url, weight=weight)
            .returning(Button)
        )
        result = await self.session.execute(stmt)
        button = result.scalar_one_or_none()
        if not button:
            raise NotFoundError(f"Button id {button_id} not found.")
        return button

    async def update_welcome(
        self,
        category_id: int,
        *,
        mode: str,
        text: str | None,
        media_id: str | None,
        buttons: list[dict] | None,
        use_random_copy: bool | None = None,
        use_random_media: bool | None = None,
    ) -> Category:
        stmt = (
            update(Category)
            .where(Category.id == category_id)
            .values(
                welcome_mode=mode,
                welcome_text=text,
                welcome_media_id=media_id,
                welcome_buttons=buttons if buttons else None,
                **(
                    {}
                    if use_random_copy is None and use_random_media is None
                    else {
                        k: v
                        for k, v in {
                            "use_random_copy": use_random_copy,
                            "use_random_media": use_random_media,
                        }.items()
                        if v is not None
                    }
                ),
            )
            .returning(Category)
        )
        result = await self.session.execute(stmt)
        category = result.scalar_one_or_none()
        if not category:
            raise NotFoundError(f"Category id {category_id} not found.")
        return category


class GroupRepository:
    def __init__(self, session):
        self.session = session

    async def upsert(self, *, chat_id: int, title: str | None, category_id: int) -> Group:
        stmt = select(Group).where(Group.telegram_chat_id == chat_id)
        group = await self.session.scalar(stmt)
        if group:
            group.title = title or group.title
            group.category_id = category_id
        else:
            group = Group(telegram_chat_id=chat_id, title=title, category_id=category_id)
            self.session.add(group)
        await self.session.flush()
        return group

    async def assign_bot(self, group_id: int, bot_id: int | None) -> None:
        stmt = (
            update(Group)
            .where(Group.id == group_id)
            .values(assigned_bot_id=bot_id)
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def active_groups_for_bot(self, bot_id: int) -> Sequence[Group]:
        stmt = select(Group).where(Group.assigned_bot_id == bot_id, Group.active.is_(True))
        result = await self.session.scalars(stmt)
        return result.all()

    async def list_by_category(self, category_id: int) -> Sequence[Group]:
        stmt = select(Group).where(Group.category_id == category_id, Group.active.is_(True))
        result = await self.session.scalars(stmt)
        return result.all()


class BotRepository:
    def __init__(self, session):
        self.session = session

    async def list(self) -> Sequence[Bot]:
        result = await self.session.scalars(select(Bot))
        return result.all()

    async def get_by_name(self, name: str) -> Bot:
        bot = await self.session.scalar(select(Bot).where(Bot.name == name))
        if not bot:
            raise NotFoundError(f"Bot {name!r} not found.")
        return bot

    async def create(self, *, name: str, token_cipher: bytes, status: str = "active") -> Bot:
        bot = Bot(name=name, token_cipher=token_cipher, status=status)
        self.session.add(bot)
        await self.session.flush()
        return bot

    async def set_token(self, bot_id: int, token_cipher: bytes) -> None:
        stmt = update(Bot).where(Bot.id == bot_id).values(token_cipher=token_cipher)
        await self.session.execute(stmt)

    async def update_status(self, bot_id: int, *, status: str, heartbeat: bool = False) -> None:
        values = {"status": status}
        if heartbeat:
            values["last_heartbeat"] = sa.func.now()  # type: ignore[name-defined]
        stmt = update(Bot).where(Bot.id == bot_id).values(**values)
        await self.session.execute(stmt)

    async def heartbeat(self, bot_id: int) -> None:
        stmt = (
            update(Bot)
            .where(Bot.id == bot_id)
            .values(last_heartbeat=sa.func.now())
        )
        await self.session.execute(stmt)


class MediaRepositoryMapRepository:
    def __init__(self, session):
        self.session = session

    async def upsert(self, *, chat_id: int, category_id: int) -> MediaRepositoryMap:
        stmt = select(MediaRepositoryMap).where(MediaRepositoryMap.chat_id == chat_id)
        mapping = await self.session.scalar(stmt)
        if mapping:
            mapping.category_id = category_id
            mapping.active = True
        else:
            mapping = MediaRepositoryMap(chat_id=chat_id, category_id=category_id, active=True)
            self.session.add(mapping)
        await self.session.flush()
        return mapping

    async def get_by_chat(self, chat_id: int) -> MediaRepositoryMap | None:
        stmt = select(MediaRepositoryMap).where(
            MediaRepositoryMap.chat_id == chat_id, MediaRepositoryMap.active.is_(True)
        )
        return await self.session.scalar(stmt)

    async def deactivate(self, chat_id: int) -> None:
        stmt = (
            update(MediaRepositoryMap)
            .where(MediaRepositoryMap.chat_id == chat_id)
            .values(active=False)
        )
        await self.session.execute(stmt)

    async def list_by_category(self, category_id: int) -> Sequence[MediaRepositoryMap]:
        stmt = select(MediaRepositoryMap).where(
            MediaRepositoryMap.category_id == category_id, MediaRepositoryMap.active.is_(True)
        )
        result = await self.session.scalars(stmt)
        return result.all()


