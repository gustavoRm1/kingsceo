from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from app.core.config import AppSettings, get_settings
from app.core.exceptions import ConfigurationError


@dataclass(slots=True)
class BotConfig:
    name: str
    token: str
    role: str = "primary"


class BotRegistry:
    def __init__(self) -> None:
        self._registry: Dict[str, BotConfig] = {}

    def register(self, config: BotConfig) -> None:
        self._registry[config.name] = config

    def get(self, name: str) -> BotConfig:
        try:
            return self._registry[name]
        except KeyError as exc:
            raise ConfigurationError(f"Bot {name!r} is not registered.") from exc

    def all(self) -> list[BotConfig]:
        return list(self._registry.values())


def load_registry(settings: AppSettings | None = None) -> BotRegistry:
    settings = settings or get_settings()
    registry = BotRegistry()
    if settings.bot_main_token:
        registry.register(BotConfig(name="main", token=settings.bot_main_token, role="primary"))
    if settings.bot_standby_token:
        registry.register(BotConfig(name="standby", token=settings.bot_standby_token, role="standby"))
    if not registry.all():
        raise ConfigurationError("Configure ao menos um token de bot no arquivo .env.")
    return registry

