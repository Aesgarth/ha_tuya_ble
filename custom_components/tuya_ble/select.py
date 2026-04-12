"""The Tuya BLE integration."""
from __future__ import annotations

from dataclasses import dataclass, field

import logging

from homeassistant.components.select import (
    SelectEntityDescription,
    SelectEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    FINGERBOT_MODE_PROGRAM,
    FINGERBOT_MODE_PUSH,
    FINGERBOT_MODE_SWITCH,
)
from .devices import TuyaBLEData, TuyaBLEEntity, TuyaBLEProductInfo
from .tuya_ble import TuyaBLEDataPointType, TuyaBLEDevice

_LOGGER = logging.getLogger(__name__)


@dataclass
class TuyaBLESelectMapping:
    dp_id: int
    description: SelectEntityDescription
    force_add: bool = True
    dp_type: TuyaBLEDataPointType | None = None
    # Maps display option strings to the values sent to/from the device.
    # If None, options are sent as integer indices (default behaviour).
    # If set, maps display option -> device value (string or int).
    options_map: dict[str, str | int] | None = None


@dataclass
class TemperatureUnitDescription(SelectEntityDescription):
    key: str = "temperature_unit"
    icon: str = "mdi:thermometer"
    entity_category: EntityCategory = EntityCategory.CONFIG


@dataclass
class TuyaBLEFingerbotModeMapping(TuyaBLESelectMapping):
    description: SelectEntityDescription = field(
        default_factory=lambda: SelectEntityDescription(
            key="fingerbot_mode",
            entity_category=EntityCategory.CONFIG,
            options=[
                FINGERBOT_MODE_PUSH,
                FINGERBOT_MODE_SWITCH,
                FINGERBOT_MODE_PROGRAM,
            ],
        )
    )


@dataclass
class TuyaBLECategorySelectMapping:
    products: dict[str, list[TuyaBLESelectMapping]] | None = None
    mapping: list[TuyaBLESelectMapping] | None = None


mapping: dict[str, TuyaBLECategorySelectMapping] = {
    "co2bj": TuyaBLECategorySelectMapping(
        products={
            "59s19z5m": [  # CO2 Detector
                TuyaBLESelectMapping(
                    dp_id=101,
                    description=TemperatureUnitDescription(
                        options=[
                            UnitOfTemperature.CELSIUS,
                            UnitOfTemperature.FAHRENHEIT,
                        ],
                    ),
                ),
            ],
        },
    ),
    "ms": TuyaBLECategorySelectMapping(
        products={
            **dict.fromkeys(
                ["ludzroix", "isk2p555"],  # Smart Lock
                [
                    TuyaBLESelectMapping(
                        dp_id=31,
                        description=SelectEntityDescription(
                            key="beep_volume",
                            options=[
                                "mute",
                                "low",
                                "normal",
                                "high",
                            ],
                            entity_category=EntityCategory.CONFIG,
                        ),
                    ),
                ],
            ),
        },
    ),
    "swtz": TuyaBLECategorySelectMapping(
        products={
            "iv13iqhf": [  # BBQ Thermometer SK-T100
                # Device sends/receives "c"/"f" as string enum values.
                # We display as Celsius/Fahrenheit but map to "c"/"f" for the device.
                TuyaBLESelectMapping(
                    dp_id=17,
                    description=SelectEntityDescription(
                        key="temperature_unit",
                        name="Temperature Unit",
                        icon="mdi:thermometer",
                        entity_category=EntityCategory.CONFIG,
                        options=[
                            UnitOfTemperature.CELSIUS,
                            UnitOfTemperature.FAHRENHEIT,
                        ],
                    ),
                    options_map={
                        UnitOfTemperature.CELSIUS: "c",
                        UnitOfTemperature.FAHRENHEIT: "f",
                    },
                ),
            ],
        },
    ),
    "szjqr": TuyaBLECategorySelectMapping(
        products={
            **dict.fromkeys(
                ["3yqdo5yt", "xhf790if"],  # CubeTouch 1s and II
                [
                    TuyaBLEFingerbotModeMapping(dp_id=2),
                ],
            ),
            **dict.fromkeys(
                [
                    "blliqpsj",
                    "ndvkgsrm",
                    "yiihr7zh",
                    "neq16kgd",
                ],  # Fingerbot Plus
                [
                    TuyaBLEFingerbotModeMapping(dp_id=8),
                ],
            ),
            **dict.fromkeys(
                [
                    "ltak7e1p",
                    "y6kttvd6",
                    "yrnk7mnn",
                    "nvr2rocq",
                    "bnt7wajf",
                    "rvdceqjh",
                    "5xhbk964",
                ],  # Fingerbot
                [
                    TuyaBLEFingerbotModeMapping(dp_id=8),
                ],
            ),
        },
    ),
    "wsdcg": TuyaBLECategorySelectMapping(
        products={
            "ojzlzzsw": [  # Soil moisture sensor
                TuyaBLESelectMapping(
                    dp_id=9,
                    description=TemperatureUnitDescription(
                        options=[
                            UnitOfTemperature.CELSIUS,
                            UnitOfTemperature.FAHRENHEIT,
                        ],
                        entity_registry_enabled_default=False,
                    ),
                ),
            ],
        },
    ),
    "znhsb": TuyaBLECategorySelectMapping(
        products={
            "cdlandip": [  # Smart water bottle
                TuyaBLESelectMapping(
                    dp_id=106,
                    description=TemperatureUnitDescription(
                        options=[
                            UnitOfTemperature.CELSIUS,
                            UnitOfTemperature.FAHRENHEIT,
                        ],
                    ),
                ),
                TuyaBLESelectMapping(
                    dp_id=107,
                    description=SelectEntityDescription(
                        key="reminder_mode",
                        options=[
                            "interval_reminder",
                            "alarm_reminder",
                        ],
                        entity_category=EntityCategory.CONFIG,
                    ),
                ),
            ],
        },
    ),
}


def get_mapping_by_device(
    device: TuyaBLEDevice,
) -> list[TuyaBLECategorySelectMapping]:
    category = mapping.get(device.category)
    if category is not None and category.products is not None:
        product_mapping = category.products.get(device.product_id)
        if product_mapping is not None:
            return product_mapping
        if category.mapping is not None:
            return category.mapping
        else:
            return []
    else:
        return []


class TuyaBLESelect(TuyaBLEEntity, SelectEntity):
    """Representation of a Tuya BLE select."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: DataUpdateCoordinator,
        device: TuyaBLEDevice,
        product: TuyaBLEProductInfo,
        mapping: TuyaBLESelectMapping,
    ) -> None:
        super().__init__(hass, coordinator, device, product, mapping.description)
        self._mapping = mapping
        self._attr_options = mapping.description.options

    def _device_value_to_option(self, device_value) -> str | None:
        """Convert a raw device value to a display option string."""
        if self._mapping.options_map:
            # Reverse lookup: find the display option whose mapped value matches
            for option, mapped in self._mapping.options_map.items():
                if device_value == mapped:
                    return option
            return None
        else:
            # Integer index into options list
            if isinstance(device_value, int) and 0 <= device_value < len(self._attr_options):
                return self._attr_options[device_value]
            # Fallback: some devices return string even for integer enums
            if isinstance(device_value, str) and device_value in self._attr_options:
                return device_value
            return None

    def _option_to_device_value(self, option: str):
        """Convert a display option string to the value sent to the device."""
        if self._mapping.options_map:
            return self._mapping.options_map.get(option)
        else:
            if option in self._attr_options:
                return self._attr_options.index(option)
            return None

    @property
    def current_option(self) -> str | None:
        """Return the selected entity option to represent the entity state."""
        datapoint = self._device.datapoints[self._mapping.dp_id]
        if datapoint:
            return self._device_value_to_option(datapoint.value)
        return None

    def select_option(self, option: str) -> None:
        """Change the selected option."""
        if option not in self._attr_options:
            return
        device_value = self._option_to_device_value(option)
        if device_value is None:
            return
        datapoint = self._device.datapoints.get_or_create(
            self._mapping.dp_id,
            TuyaBLEDataPointType.DT_ENUM,
            device_value,
        )
        if datapoint:
            self._hass.create_task(datapoint.set_value(device_value))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tuya BLE selects."""
    data: TuyaBLEData = hass.data[DOMAIN][entry.entry_id]
    mappings = get_mapping_by_device(data.device)
    entities: list[TuyaBLESelect] = []
    for mapping in mappings:
        if (
            mapping.force_add or
            data.device.datapoints.has_id(mapping.dp_id, mapping.dp_type)
        ):
            entities.append(
                TuyaBLESelect(
                    hass,
                    data.coordinator,
                    data.device,
                    data.product,
                    mapping,
                )
            )
    async_add_entities(entities)