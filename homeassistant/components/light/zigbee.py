"""
homeassistant.components.light.zigbee

Contains functionality to use a ZigBee device as a light.
"""

from binascii import unhexlify

from homeassistant.components.zigbee import (
    ZigBeeDigitalOut, create_boolean_maps)


DEPENDENCIES = ["zigbee"]


def setup_platform(hass, config, add_entities, discovery_info=None):
    """
    Create and add an entity based on the configuration.
    """
    add_entities([ZigBeeDigitalOut(
        config["name"],
        unhexlify(config["address"]),
        config["pin"],
        create_boolean_maps(config),
        config.get("poll")
    )])
