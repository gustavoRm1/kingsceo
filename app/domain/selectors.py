from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select

from app.infrastructure.db.models import Bot, Group


async def groups_per_bot(session) -> Sequence[tuple[str, int]]:
    stmt = (
        select(Bot.name, func.count(Group.id))
        .join(Group, Group.assigned_bot_id == Bot.id, isouter=True)
        .group_by(Bot.name)
    )
    result = await session.execute(stmt)
    return result.all()

