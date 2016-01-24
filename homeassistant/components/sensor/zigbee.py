from binascii import unhexlify

from homeassistant.components.zigbee import (
    ZigBeeDigitalIn, ZigBeeAnalogIn, create_boolean_maps)


DEPENDENCIES = ["zigbee"]


def setup_platform(hass, config, add_entities, discovery_info=None):
    extra_kwargs = {}
    if config.get("type", "").lower() in ("analog", "analogue"):
        InputClass = ZigBeeAnalogIn
    else:
        InputClass = ZigBeeDigitalIn
        extra_kwargs["boolean_maps"] = create_boolean_maps(config)

    add_entities([InputClass(
        config["name"],
        unhexlify(config["address"]),
        config["pin"],
        poll=True,
        **extra_kwargs
    )])
