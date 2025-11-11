from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, JSON, LargeBinary, Text, event
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.utils import slugify
from app.infrastructure.db.base import Base


class Category(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    welcome_mode: Mapped[str] = mapped_column(Text, default="all", nullable=False)
    welcome_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    welcome_media_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    welcome_buttons: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    use_random_copy: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    use_random_media: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    use_spoiler_media: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dispatch_interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_dispatch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    groups: Mapped[list["Group"]] = relationship("Group", back_populates="category")
    media_items: Mapped[list["Media"]] = relationship("Media", back_populates="category")
    copies: Mapped[list["Copy"]] = relationship("Copy", back_populates="category")
    buttons: Mapped[list["Button"]] = relationship("Button", back_populates="category")
    repositories: Mapped[list["MediaRepositoryMap"]] = relationship(
        "MediaRepositoryMap", back_populates="category"
    )

    def set_slug(self) -> None:
        if not self.slug:
            self.slug = slugify(self.name)


class Group(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("category.id", ondelete="CASCADE"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    clean_service_messages: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    assigned_bot_id: Mapped[int | None] = mapped_column(
        ForeignKey("bot.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_activity: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    category: Mapped["Category | None"] = relationship("Category", back_populates="groups")
    assigned_bot: Mapped["Bot | None"] = relationship("Bot", back_populates="groups")


class Media(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("category.id", ondelete="CASCADE"))
    media_type: Mapped[str] = mapped_column(Text, nullable=False)
    file_id: Mapped[str] = mapped_column(Text, nullable=False)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    weight: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    has_spoiler: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    category: Mapped["Category"] = relationship("Category", back_populates="media_items")


class Copy(Base):
    __tablename__ = "copies"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("category.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    category: Mapped["Category"] = relationship("Category", back_populates="copies")


class Button(Base):
    __tablename__ = "buttons"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("category.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    category: Mapped["Category"] = relationship("Category", back_populates="buttons")


class Bot(Base):
    __tablename__ = "bot"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    token_cipher: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="active", nullable=False)
    last_heartbeat: Mapped[datetime | None] = mapped_column(nullable=True)
    heartbeat_interval_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    capabilities: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    groups: Mapped[list["Group"]] = relationship("Group", back_populates="assigned_bot")


class BotFailoverLog(Base):
    __tablename__ = "bot_failover_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("group.id", ondelete="SET NULL"))
    old_bot_id: Mapped[int | None] = mapped_column(ForeignKey("bot.id", ondelete="SET NULL"))
    new_bot_id: Mapped[int | None] = mapped_column(ForeignKey("bot.id", ondelete="SET NULL"))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

class MediaRepositoryMap(Base):
    __tablename__ = "media_repository"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("category.id", ondelete="CASCADE"), nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    clean_service_messages: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    category: Mapped["Category"] = relationship("Category", back_populates="repositories")


@event.listens_for(Category, "before_insert")
def category_before_insert(mapper, connection, target: Category) -> None:  # type: ignore[override]
    target.set_slug()


@event.listens_for(Category, "before_update")
def category_before_update(mapper, connection, target: Category) -> None:  # type: ignore[override]
    target.set_slug()

