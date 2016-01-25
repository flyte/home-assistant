"""
homeassistant.components.sensor.zigbee

Contains functionality to use a ZigBee device as a sensor.
"""

import logging

from homeassistant.const import TEMP_CELCIUS
from homeassistant.helpers.entity import Entity
from homeassistant.components import zigbee


DEPENDENCIES = ["zigbee"]
_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """
    Parses the config to work out which type of ZigBee sensor we're dealing
    with and instantiates relevant classes to handle it.
    """
    typ = config.get("type", "").lower()
    if not typ:
        _LOGGER.exception(
            "Must include 'type' when configuring a ZigBee sensor.")
        return
    try:
        sensor_class, config_class = TYPE_CLASSES[typ]
    except KeyError:
        _LOGGER.exception("Unknown ZigBee sensor type: %s", typ)
        return
    add_entities([sensor_class(config_class(config))])


class ZigBeeTemperatureSensor(Entity):
    """
    Allows usage of an XBee Pro as a temperature sensor.
    """
    def __init__(self, config):
        self._config = config
        self._temp = None
        # @TODO: Instead of trying to update here, invoke a service to get
        #        the value instead.
        try:
            self.update()
        except zigbee.ZigBeeTxFailure as exc:
            _LOGGER.warning(
                "Unable to get initial value of %s: %s", config.name, exc)

    @property
    def name(self):
        return self._config.name

    @property
    def state(self):
        return self._temp

    @property
    def unit_of_measurement(self):
        return TEMP_CELCIUS

    def update(self):
        self._temp = zigbee.DEVICE.get_temperature(self._config.address)


# This must be below the ZigBeeTemperatureSensor which it references.
TYPE_CLASSES = {
    "temperature": (ZigBeeTemperatureSensor, zigbee.ZigBeeConfig),
    "analog": (zigbee.ZigBeeAnalogIn, zigbee.ZigBeeAnalogInConfig),
    "digital": (zigbee.ZigBeeDigitalIn, zigbee.ZigBeeDigitalPinConfig)
}
