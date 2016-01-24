from binascii import unhexlify

from homeassistant.components.zigbee import ZigBeeDigitalOut, create_output_settings


DEPENDENCIES = ["zigbee"]


def setup_platform(hass, config, add_entities, discovery_info=None):
    """
    Create and add an entity based on the configuration.
    """
    add_entities([ZigBeeDigitalOut(
        config["name"],
        unhexlify(config["address"]),
        config["pin"],
        create_output_settings(config),
        config.get("poll")
    )])
