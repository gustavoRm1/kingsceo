from __future__ import annotations

import random
import unicodedata
from typing import Iterable, Sequence, Tuple, TypeVar

T = TypeVar("T")


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug_chars = []
    for char in ascii_only.lower():
        if char.isalnum():
            slug_chars.append(char)
        elif char in {" ", "-", "_"}:
            slug_chars.append("-")
    slug = "".join(slug_chars)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def weighted_choice(items: Sequence[Tuple[T, int]]) -> T | None:
    if not items:
        return None
    population, weights = zip(*items)
    total = sum(weights)
    if total <= 0:
        return random.choice(population)
    return random.choices(population, weights=weights, k=1)[0]


def chunked(iterable: Iterable[T], size: int) -> Iterable[list[T]]:
    chunk: list[T] = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) == size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk

