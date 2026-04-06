"""Discord UI assembly for the Tamagotchi feature."""

from .action_views import ChatterButton, CleanButton, MedicateButton, PlayButton
from .common import ui
from .game_views import GameSelectView, RPSView
from .inventory_views import InventoryButton, InventoryItemButton, InventoryView
from .state import should_show_medicate


class TamagotchiView(ui.View):
    """
    Persistent view with action buttons.
    Attached to every bot response when tama_enabled is True.
    """

    def __init__(self, config: dict, manager):
        super().__init__(timeout=None)
        self.config = config
        self.manager = manager
        self._build()

    def _build(self):
        self.add_item(InventoryButton(self.config, self.manager))
        if self.config.get("tama_chatter_enabled", True):
            self.add_item(ChatterButton(self.config, self.manager))
        self.add_item(PlayButton(self.config, self.manager))
        if should_show_medicate(self.config):
            self.add_item(MedicateButton(self.config, self.manager))
        if int(self.config.get("tama_dirt", 0) or 0) > 0:
            self.add_item(CleanButton(self.config, self.manager))


__all__ = [
    "ChatterButton",
    "CleanButton",
    "GameSelectView",
    "InventoryButton",
    "InventoryItemButton",
    "InventoryView",
    "MedicateButton",
    "PlayButton",
    "RPSView",
    "TamagotchiView",
]
