"""Split Tamagotchi feature package with a compatibility surface."""

from tamagotchi_inventory import (
    BUTTON_STYLE_BY_NAME,
    BUTTON_STYLE_LABELS,
    DEFAULT_TAMA_INVENTORY_ITEMS,
    TAMA_INVENTORY_DEFAULTS_VERSION,
    _coerce_item_amount,
    ensure_inventory_defaults,
    get_inventory_item,
    get_inventory_items,
    inventory_button_style,
    inventory_item_id_from_name,
    inventory_message_text,
)

from .runtime import *  # noqa: F401,F403
from .state import *  # noqa: F401,F403
from .views import *  # noqa: F401,F403

__all__ = [name for name in globals() if not name.startswith("_")]

