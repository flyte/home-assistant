from binascii import unhexlify

from homeassistant.components import zigbee
from homeassistant.components.light import Light


DEPENDENCIES = ["zigbee"]


def setup_platform(hass, config, add_entities, discovery_info=None):
    # @TODO: For each item, do the below:
    if config["on_state"].lower() == "low":
        output_settings = {
            True: zigbee.GPIO_DIGITAL_OUTPUT_LOW,
            False: zigbee.GPIO_DIGITAL_OUTPUT_HIGH
        }
    else:
        output_settings = {
            True: zigbee.GPIO_DIGITAL_OUTPUT_HIGH,
            False: zigbee.GPIO_DIGITAL_OUTPUT_LOW
        }
    add_entities([ZigBeeLight(
        config["name"],
        unhexlify(config["address"]),
        config["pin"],
        output_settings,
        config.get("poll")
    )])


class ZigBeeLight(Light):
    def __init__(self, name, address, pin, output_settings, poll):
        self._name = name
        self._address = address
        self._pin = pin
        self._output_settings = output_settings
        # A reversed output_settings so we can look up our True/False state from pin high/low.
        self._output_settings_state = {v: k for k, v in output_settings.items()}
        self._should_poll = bool(poll)
        self._state = False

        # Poll for initial value
        self.update()

    @property
    def name(self):
        return self._name

    @property
    def should_poll(self):
        return self._should_poll

    @property
    def is_on(self):
        return self._state

    def _set_state(self, state):
        zigbee.device.set_gpio_pin(
            self._pin,
            self._output_settings[state],
            self._address)
        self._state = state
        self.update_ha_state()

    def turn_on(self, **kwargs):
        self._set_state(True)

    def turn_off(self, **kwargs):
        self._set_state(False)

    def update(self):
        """
        Ask the ZigBee device what its outputs are set to.
        """
        pin_state = zigbee.device.get_gpio_pin(
            self._pin,
            self._address)
        self._state = self._output_settings_state[pin_state]
