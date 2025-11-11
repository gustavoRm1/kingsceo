from __future__ import annotations

from collections.abc import Sequence
from typing import Iterable

from app.core.exceptions import NotFoundError
from app.core.utils import weighted_choice
from app.domain import models
from app.domain.repositories import BotRepository, CategoryRepository, GroupRepository
from app.infrastructure.crypto import decrypt_token, encrypt_token


class CategoryService:
    def __init__(self, repo: CategoryRepository):
        self.repo = repo

    async def create_category(self, name: str) -> models.CategoryDTO:
        category = await self.repo.create(name=name)
        category_full = await self.repo.get_by_id(category.id)
        return models.CategoryDTO.model_validate(category_full)

    async def list_categories(self) -> list[models.CategoryDTO]:
        categories = await self.repo.list()
        return [models.CategoryDTO.model_validate(cat) for cat in categories]

    async def get_category_by_slug(self, slug: str) -> models.CategoryDTO:
        category = await self.repo.get_by_slug(slug)
        return models.CategoryDTO.model_validate(category)

    async def get_category_by_id(self, category_id: int) -> models.CategoryDTO:
        category = await self.repo.get_by_id(category_id)
        return models.CategoryDTO.model_validate(category)

    async def add_media(
        self,
        category_id: int,
        *,
        media_type: str,
        file_id: str,
        caption: str | None,
        weight: int = 1,
    ) -> models.MediaDTO:
        media = await self.repo.add_media(
            category_id,
            media_type=media_type,
            file_id=file_id,
            caption=caption,
            weight=weight,
        )
        return models.MediaDTO.model_validate(media)

    async def media_exists(self, category_id: int, file_id: str) -> bool:
        return await self.repo.media_exists(category_id, file_id)

    async def add_copy(self, category_id: int, *, text: str, weight: int = 1) -> models.CopyDTO:
        copy = await self.repo.add_copy(category_id, text=text, weight=weight)
        return models.CopyDTO.model_validate(copy)

    async def get_copy(self, copy_id: int) -> models.CopyDTO:
        copy = await self.repo.get_copy(copy_id)
        return models.CopyDTO.model_validate(copy)

    async def update_copy(self, copy_id: int, *, text: str, weight: int) -> models.CopyDTO:
        copy = await self.repo.update_copy(copy_id, text=text, weight=weight)
        return models.CopyDTO.model_validate(copy)

    async def get_copy(self, copy_id: int) -> models.CopyDTO:
        copy = await self.repo.get_copy(copy_id)
        return models.CopyDTO.model_validate(copy)

    async def add_button(
        self,
        category_id: int,
        *,
        label: str,
        url: str,
        weight: int = 1,
    ) -> models.ButtonDTO:
        button = await self.repo.add_button(category_id, label=label, url=url, weight=weight)
        return models.ButtonDTO.model_validate(button)

    async def get_button(self, button_id: int) -> models.ButtonDTO:
        button = await self.repo.get_button(button_id)
        return models.ButtonDTO.model_validate(button)

    async def update_button(
        self,
        button_id: int,
        *,
        label: str,
        url: str,
        weight: int,
    ) -> models.ButtonDTO:
        button = await self.repo.update_button(button_id, label=label, url=url, weight=weight)
        return models.ButtonDTO.model_validate(button)

    async def set_spoiler(self, category_id: int, *, enabled: bool) -> models.CategoryDTO:
        category = await self.repo.set_spoiler(category_id, enabled=enabled)
        return models.CategoryDTO.model_validate(category)

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
    ) -> models.CategoryDTO:
        category = await self.repo.update_welcome(
            category_id,
            mode=mode,
            text=text,
            media_id=media_id,
            buttons=buttons,
            use_random_copy=use_random_copy,
            use_random_media=use_random_media,
        )
        return models.CategoryDTO.model_validate(category)

    async def random_payload(
        self,
        category_ref: int | str,
        *,
        allow_media: bool = True,
        allow_copy: bool = True,
        allow_buttons: bool = True,
    ) -> models.Payload:
        if isinstance(category_ref, int):
            category = await self.repo.get_by_id(category_ref)
        else:
            category = await self.repo.get_by_slug(category_ref)

        media_dto = None
        if allow_media and category.media_items:
            if category.use_random_media:
                media_choice = weighted_choice([(m, m.weight or 1) for m in category.media_items])
                if media_choice:
                    media_dto = models.MediaDTO.model_validate(media_choice)
            else:
                media_dto = models.MediaDTO.model_validate(category.media_items[0])

        copy_dto = None
        if allow_copy and category.copies:
            if category.use_random_copy:
                copy_choice = weighted_choice([(c, c.weight or 1) for c in category.copies])
                if copy_choice:
                    copy_dto = models.CopyDTO.model_validate(copy_choice)
            else:
                copy_dto = models.CopyDTO.model_validate(category.copies[0])

        buttons: list[models.ButtonDTO] = []
        if allow_buttons and category.buttons:
            ordered_buttons = sorted(
                category.buttons,
                key=lambda b: (b.weight or 0, b.id),
            )
            buttons = [models.ButtonDTO.model_validate(btn) for btn in ordered_buttons]

        return models.Payload(
            media=media_dto,
            message=copy_dto,
            buttons=buttons,
            media_spoiler=category.use_spoiler_media,
        )


class GroupService:
    def __init__(self, repo: GroupRepository):
        self.repo = repo

    async def upsert_group(self, *, chat_id: int, title: str | None, category_id: int) -> models.GroupDTO:
        group = await self.repo.upsert(chat_id=chat_id, title=title, category_id=category_id)
        return models.GroupDTO.model_validate(group)

    async def assign_bot(self, group_id: int, bot_id: int | None) -> None:
        await self.repo.assign_bot(group_id, bot_id)

    async def list_active_for_bot(self, bot_id: int) -> Sequence[models.GroupDTO]:
        groups = await self.repo.active_groups_for_bot(bot_id)
        return [models.GroupDTO.model_validate(group) for group in groups]

    async def list_by_category(self, category_id: int) -> Sequence[models.GroupDTO]:
        groups = await self.repo.list_by_category(category_id)
        return [models.GroupDTO.model_validate(group) for group in groups]


class BotService:
    def __init__(self, repo: BotRepository):
        self.repo = repo

    async def register_bot(self, *, name: str, token: str, status: str = "active") -> models.BotDTO:
        token_cipher = encrypt_token(token)
        bot = await self.repo.create(name=name, token_cipher=token_cipher, status=status)
        return models.BotDTO.model_validate(bot)

    async def list_bots(self) -> Sequence[models.BotDTO]:
        bots = await self.repo.list()
        return [models.BotDTO.model_validate(bot) for bot in bots]

    async def get_token(self, name: str) -> str:
        bot = await self.repo.get_by_name(name)
        return decrypt_token(bot.token_cipher)

    async def update_token(self, bot_id: int, token: str) -> None:
        token_cipher = encrypt_token(token)
        await self.repo.set_token(bot_id, token_cipher)

    async def update_status(self, bot_id: int, *, status: str, heartbeat: bool = False) -> None:
        await self.repo.update_status(bot_id, status=status, heartbeat=heartbeat)

    async def heartbeat(self, bot_id: int) -> None:
        await self.repo.heartbeat(bot_id)

    async def heartbeat_by_name(self, name: str) -> None:
        bot = await self.repo.get_by_name(name)
        await self.repo.heartbeat(bot.id)


class MediaRepositoryService:
    def __init__(
        self,
        mapping_repo,
        category_repo: CategoryRepository,
    ):
        self.mapping_repo = mapping_repo
        self.category_repo = category_repo

    async def assign_repository(self, *, chat_id: int, category_slug: str) -> models.MediaRepositoryDTO:
        category = await self.category_repo.get_by_slug(category_slug)
        mapping = await self.mapping_repo.upsert(chat_id=chat_id, category_id=category.id)
        return models.MediaRepositoryDTO.model_validate(mapping)

    async def get_mapping(self, chat_id: int) -> models.MediaRepositoryDTO | None:
        mapping = await self.mapping_repo.get_by_chat(chat_id)
        if not mapping:
            return None
        return models.MediaRepositoryDTO.model_validate(mapping)

    async def list_by_category(self, category_id: int) -> list[models.MediaRepositoryDTO]:
        mappings = await self.mapping_repo.list_by_category(category_id)
        return [models.MediaRepositoryDTO.model_validate(item) for item in mappings]

    async def get_mapping_by_id(self, mapping_id: int) -> models.MediaRepositoryDTO | None:
        mapping = await self.mapping_repo.get_by_id(mapping_id)
        if not mapping:
            return None
        return models.MediaRepositoryDTO.model_validate(mapping)

    async def set_cleanup(self, mapping_id: int, *, enabled: bool) -> models.MediaRepositoryDTO:
        await self.mapping_repo.set_service_cleanup(mapping_id, enabled)
        mapping = await self.mapping_repo.get_by_id(mapping_id)
        if not mapping:
            raise NotFoundError(f"Repository map id {mapping_id} not found.")
        return models.MediaRepositoryDTO.model_validate(mapping)