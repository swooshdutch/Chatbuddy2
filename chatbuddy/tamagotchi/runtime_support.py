"""Internal support helpers shared by Tamagotchi runtime/UI modules."""

from __future__ import annotations


def build_tamagotchi_view(config: dict, manager):
    from .views import TamagotchiView

    return TamagotchiView(config, manager)


async def send_soul_logs(bot_ref, config: dict, soul_logs: list[str]) -> None:
    from bot_helpers import send_soul_logs

    await send_soul_logs(bot_ref, config, soul_logs)


__all__ = ["build_tamagotchi_view", "send_soul_logs"]
