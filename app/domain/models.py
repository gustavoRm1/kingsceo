from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Sequence

from pydantic import BaseModel, Field


class BaseDTO(BaseModel):
    model_config = {"from_attributes": True}


class ButtonDTO(BaseDTO):
    id: int
    category_id: int
    label: str
    url: str
    weight: int
    created_at: datetime


class MediaDTO(BaseDTO):
    id: int
    category_id: int
    media_type: Literal["photo", "video", "document", "animation"]
    file_id: str
    caption: str | None
    weight: int
    created_at: datetime


class CopyDTO(BaseDTO):
    id: int
    category_id: int
    text: str
    weight: int
    created_at: datetime


class CategoryDTO(BaseDTO):
    id: int
    name: str
    slug: str
    welcome_mode: Literal["all", "text", "media", "buttons", "none"]
    welcome_text: str | None = None
    welcome_media_id: str | None = None
    welcome_buttons: dict[str, Any] | None = None
    created_at: datetime
    media_items: Sequence[MediaDTO] | None = None
    copies: Sequence[CopyDTO] | None = None
    buttons: Sequence[ButtonDTO] | None = None


class GroupDTO(BaseDTO):
    id: int
    telegram_chat_id: int
    title: str | None
    category_id: int
    active: bool
    assigned_bot_id: int | None
    last_activity: datetime | None
    created_at: datetime


class BotDTO(BaseDTO):
    id: int
    name: str
    status: Literal["active", "standby", "offline"]
    last_heartbeat: datetime | None
    heartbeat_interval_seconds: int
    capabilities: dict[str, Any] | None
    created_at: datetime


class Payload(BaseModel):
    media: MediaDTO | None = None
    message: CopyDTO | None = None
    buttons: list[ButtonDTO] = Field(default_factory=list)


class MediaRepositoryDTO(BaseDTO):
    id: int
    category_id: int
    chat_id: int
    active: bool
    created_at: datetime


