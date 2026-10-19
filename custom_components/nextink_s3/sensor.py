"""Displayed quota estimates and last successful update diagnostic."""

from datetime import datetime
from decimal import Decimal

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import NextInkConfigEntry
from .const import DOMAIN
from .coordinator import NextInkCoordinator

DESCRIPTIONS = tuple(
    SensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        state_class=SensorStateClass.MEASUREMENT,
    )
    for key in ("used_bytes", "available_bytes", "total_bytes")
) + (
    SensorEntityDescription(
        key="object_count",
        translation_key="object_count",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:counter",
    ),
    SensorEntityDescription(
        key="percentage",
        translation_key="percentage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:chart-donut",
    ),
    SensorEntityDescription(
        key="last_success",
        translation_key="last_success",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NextInkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        NextInkSensor(entry.runtime_data, entry.entry_id, description)
        for description in DESCRIPTIONS
    )


class NextInkSensor(CoordinatorEntity[NextInkCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: NextInkCoordinator, entry_id: str, description: SensorEntityDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Next.ink S3",
            manufacturer="Next.ink",
            model="Displayed storage quota",
            configuration_url="https://next.ink/profile/?tab=storage",
        )

    @property
    def available(self) -> bool:
        if self.entity_description.key == "last_success":
            return self.coordinator.last_success is not None
        return super().available

    @property
    def native_value(self) -> Decimal | int | datetime | None:
        if self.entity_description.key == "last_success":
            return self.coordinator.last_success
        if self.coordinator.data is None:
            return None
        return getattr(self.coordinator.data, self.entity_description.key)
