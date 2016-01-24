from binascii import unhexlify

from homeassistant.const import TEMP_CELCIUS
from homeassistant.helpers.entity import Entity
from homeassistant.components import zigbee


DEPENDENCIES = ["zigbee"]


def setup_platform(hass, config, add_entities, discovery_info=None):
    extra_kwargs = {}
    typ = config.get("type", "").lower()

    if typ == "temperature":
        InputClass = ZigBeeTemperatureSensor

    elif typ in ("analog", "analogue"):
        InputClass = zigbee.ZigBeeAnalogIn
        extra_kwargs.update(dict(
            pin=config["pin"],
            poll=True
        ))

    elif typ == "digital":
        InputClass = zigbee.ZigBeeDigitalIn
        extra_kwargs.update(dict(
            pin=config["pin"],
            boolean_maps=zigbee.create_boolean_maps(config),
            poll=True
        ))

    add_entities([InputClass(
        config["name"],
        unhexlify(config["address"]),
        **extra_kwargs
    )])


class ZigBeeTemperatureSensor(Entity):
    def __init__(self, name, address):
        self._name = name
        self._address = address
        self._temp = None
        self.update()

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
        self._temp = zigbee.device.get_temperature(self._address)
