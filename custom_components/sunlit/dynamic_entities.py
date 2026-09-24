"""Create platform entities as data becomes available, not only at setup.

Coordinator payloads are snapshots of what the cloud reported at that moment.
A device that is offline while Home Assistant starts contributes no keys, so
platforms that derive their entities from those keys would create nothing for
it — and, because setup runs exactly once, would never create anything later
either. The entity then lingers in the registry as ``restored``/unavailable
until the config entry is reloaded by hand.

The helper here keeps that data-driven behaviour (only entities whose hardware
actually reports are created, so systems without an EV3600 or charging box stay
clean) while re-running the builder whenever a coordinator publishes new data.
"""

from collections.abc import Callable, Iterable
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


@callback
def async_setup_dynamic_entities[EntityT: Entity](
    config_entry: ConfigEntry,
    coordinators: Iterable[DataUpdateCoordinator | None],
    async_add_entities: AddEntitiesCallback,
    build_entities: Callable[[set[str]], list[EntityT]],
    update_before_add: bool = True,
) -> None:
    """Add entities now and again whenever a coordinator reports new data.

    ``build_entities`` receives the set of keys that have already been created
    and must return only the entities missing from it, registering their keys as
    it goes. Keys must be stable across calls (device id, sensor key, module
    number) so an entity is never created twice.
    """
    created_keys: set[str] = set()

    @callback
    def _async_add_missing_entities() -> None:
        # Coordinators call their listeners directly, so an exception escaping
        # here would abort the remaining listeners for that update. A malformed
        # payload must not take the rest of the integration down with it.
        try:
            new_entities = build_entities(created_keys)
        except Exception:
            _LOGGER.exception("Error building entities for %s", config_entry.title)
            return
        if new_entities:
            async_add_entities(new_entities, update_before_add)

    for coordinator in coordinators:
        if coordinator is None:
            continue
        config_entry.async_on_unload(
            coordinator.async_add_listener(_async_add_missing_entities)
        )

    _async_add_missing_entities()
