"""
homeassistant.components.sensor.zigbee

Contains functionality to use a ZigBee device as a sensor.
"""

import logging
from binascii import unhexlify

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
    address = config.get("address")
    if address is not None:
        address = unhexlify(address)

    config_kwargs = dict(
        name=config["name"],
        address=address
    )
    typ = config.get("type", "").lower()

    if typ == "temperature":
        sensor_class = ZigBeeTemperatureSensor

    elif typ in ("analog", "analogue"):
        sensor_class = zigbee.ZigBeeAnalogIn
        max_volts = config.get("max_volts", zigbee.DEFAULT_ADC_MAX_VOLTS)
        config_kwargs.update(dict(
            pin=config["pin"],
            poll=True,
            max_voltage=max_volts
        ))

    elif typ == "digital":
        sensor_class = zigbee.ZigBeeDigitalIn
        config_kwargs.update(dict(
            pin=config["pin"],
            boolean_maps=zigbee.create_boolean_maps(config),
            poll=True
        ))
    else:
        # @TODO: How should we fail here?
        pass

    add_entities([sensor_class(**config_kwargs)])


class ZigBeeTemperatureSensor(Entity):
    """
    Allows usage of an XBee Pro as a temperature sensor.
    """
    def __init__(self, name, address):
        self._name = name
        self._address = address
        self._temp = None
        # @TODO: Instead of trying to update here, invoke a service to get
        #        the value instead.
        try:
            self.update()
        except zigbee.ZigBeeZigBeeTxFailure as e:
            _LOGGER.warning("Unable to get initial value of %s: %s", name, e)

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._temp

    @property
    def unit_of_measurement(self):
        return TEMP_CELCIUS

    def update(self):
        self._temp = zigbee.DEVICE.get_temperature(self._address)
