"""
homeassistant.components.zigbee
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Sets up and provides access to a ZigBee device and contains generic entity
classes.
"""

import logging
from time import sleep
from datetime import timedelta, datetime
from sys import version_info
from binascii import unhexlify

try:
    from xbee import ZigBee as ZigBeeDevice
except ImportError:
    ZigBeeDevice = None

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers.entity import Entity, ToggleEntity


DOMAIN = "zigbee"
REQUIREMENTS = ("xbee", "pyserial")

CONF_DEVICE = "device"
CONF_BAUD = "baud"

DEFAULT_DEVICE = "/dev/ttyUSB0"
DEFAULT_BAUD = 9600
DEFAULT_ADC_MAX_VOLTS = 1.2

RX_TIMEOUT = timedelta(seconds=10)

# @TODO: Split these out to a separate module containing the
#        specifics for each type of XBee module. (This is Series 2 non-pro)
DIGITAL_PINS = (
    "dio-0", "dio-1", "dio-2",
    "dio-3", "dio-4", "dio-5",
    "dio-10", "dio-11", "dio-12"
)
ANALOG_PINS = (
    "adc-0", "adc-1", "adc-2", "adc-3"
)
IO_PIN_COMMANDS = (
    b"D0", b"D1", b"D2",
    b"D3", b"D4", b"D5",
    b"P0", b"P1", b"P2"
)
ADC_MAX_VAL = 1023


class GPIOSetting:
    """
    Class to contain a human readable name and byte value of a GPIO setting.
    """
    def __init__(self, name, value):
        self._name = name
        self._value = value

    def __str__(self):
        return self.name

    @property
    def name(self):
        """
        Human readable name for the GPIO setting.
        """
        return self._name

    @property
    def value(self):
        """
        Byte value of the GPIO setting.
        """
        return self._value


GPIO_DISABLED = GPIOSetting("DISABLED", b"\x00")
GPIO_STANDARD_FUNC = GPIOSetting("STANDARD_FUNC", b"\x01")
GPIO_ADC = GPIOSetting("ADC", b"\x02")
GPIO_DIGITAL_INPUT = GPIOSetting("DIGITAL_INPUT", b"\x03")
GPIO_DIGITAL_OUTPUT_LOW = GPIOSetting("DIGITAL_OUTPUT_LOW", b"\x04")
GPIO_DIGITAL_OUTPUT_HIGH = GPIOSetting("DIGITAL_OUTPUT_HIGH", b"\x05")
GPIO_SETTINGS = {
    GPIO_DISABLED.value: GPIO_DISABLED,
    GPIO_STANDARD_FUNC.value: GPIO_STANDARD_FUNC,
    GPIO_ADC.value: GPIO_ADC,
    GPIO_DIGITAL_INPUT.value: GPIO_DIGITAL_INPUT,
    GPIO_DIGITAL_OUTPUT_LOW.value: GPIO_DIGITAL_OUTPUT_LOW,
    GPIO_DIGITAL_OUTPUT_HIGH.value: GPIO_DIGITAL_OUTPUT_HIGH
}

_LOGGER = logging.getLogger(__name__)
_LOGGER.addHandler(logging.StreamHandler())
_LOGGER.setLevel(logging.DEBUG)

# Service to set states on ZigBee modules
# Service to request state from ZigBee modules
# Event for incoming state notifications

DEVICE = None


class ZigBeeException(Exception):
    """
    One exception to rule them all. Catch this if you don't care why it failed.
    """
    pass


class ZigBeeResponseTimeout(ZigBeeException):
    """
    The ZigBee device didn't return a frame within the configured timeout.
    """
    pass


class ZigBeeUnknownError(ZigBeeException):
    """
    The ZigBee device returned an 0x01 status byte.
    """
    pass


class ZigBeeInvalidCommand(ZigBeeException):
    """
    The requested ZigBee command was not valid.
    """
    pass


class ZigBeeInvalidParameter(ZigBeeException):
    """
    The requested ZigBee parameter was not valid.
    """
    pass


class ZigBeeTxFailure(ZigBeeException):
    """
    The ZigBee device attempted to send the frame but it could not communicate
    with the target device (usually out of range or switched off).
    """
    pass


class ZigBeeUnknownStatus(ZigBeeException):
    """
    The ZigBee device returned a status code which we're not familiar with.
    """
    pass


class ZigBeePinNotConfigured(ZigBeeException):
    """
    An operation was attempted on a GPIO pin which it was not configured for.
    """
    pass


def setup(hass, config):
    """
    Set up the connection to the ZigBee device and instantiate the helper
    class for it.
    """
    global DEVICE

    from serial import Serial

    usb_device = config[DOMAIN].get(CONF_DEVICE, DEFAULT_DEVICE)
    baud = int(config[DOMAIN].get(CONF_BAUD, DEFAULT_BAUD))
    ser = Serial(usb_device, baud)
    DEVICE = ZigBee(ser)
    hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, close_serial_port)
    return True


def close_serial_port():
    """
    Close the serial port we're using to communicate with the ZigBee.
    """
    DEVICE.zb.serial.close()


def raise_if_error(frame):
    """
    Checks a frame and raises the relevant exception if required.
    """
    if "status" not in frame or frame["status"] == b"\x00":
        return
    codes_and_exceptions = {
        b"\x01": ZigBeeUnknownError,
        b"\x02": ZigBeeInvalidCommand,
        b"\x03": ZigBeeInvalidParameter,
        b"\x04": ZigBeeTxFailure
    }
    if frame["status"] in codes_and_exceptions:
        raise codes_and_exceptions[frame["status"]]()
    raise ZigBeeUnknownStatus()


def hex_to_int(value):
    """
    Convert hex string like 0xAE3 to 2787.
    """
    if version_info.major >= 3:
        return int.from_bytes(value, "big")
    return int(value.encode("hex"), 16)


class ZigBee(object):
    """
    Adds convenience methods for a ZigBee.
    """
    _rx_frames = {}
    _frame_id = 1

    def __init__(self, ser):
        self._ser = ser
        # I think it's obvious that zb refers to a ZigBee.
        # pylint: disable=invalid-name
        self.zb = ZigBeeDevice(ser, callback=self._frame_received)

    @property
    def next_frame_id(self):
        """
        Gets a byte of the next valid frame ID (1 - 255), increments the
        internal _frame_id counter and wraps it back to 1 if necessary.
        """
        # Python 2/3 compatible way of converting 1 to "\x01" in py2 or b"\x01"
        # in py3.
        fid = bytes(bytearray((self._frame_id,)))
        self._frame_id += 1
        if self._frame_id > 0xFF:
            self._frame_id = 1
        try:
            del self._rx_frames[fid]
        except KeyError:
            pass
        return fid

    def _frame_received(self, frame):
        """
        Put the frame into the _rx_frames dict with a key of the frame_id.
        """
        try:
            self._rx_frames[frame["frame_id"]] = frame
        except KeyError:
            # Has no frame_id, ignore?
            pass
        _LOGGER.debug("Frame received: %s", frame)

    def _send(self, **kwargs):
        """
        Send a frame to either the local ZigBee or a remote device.
        """
        if kwargs.get("dest_addr_long") is not None:
            self.zb.remote_at(**kwargs)
        else:
            self.zb.at(**kwargs)

    def _send_and_wait(self, **kwargs):
        """
        Send a frame to either the local ZigBee or a remote device and wait
        for a pre-defined amount of time for its response.
        """
        frame_id = self.next_frame_id
        kwargs.update(dict(frame_id=frame_id))
        self._send(**kwargs)
        timeout = datetime.now() + RX_TIMEOUT
        while datetime.now() < timeout:
            try:
                frame = self._rx_frames.pop(frame_id)
                raise_if_error(frame)
                return frame
            except KeyError:
                sleep(0.1)
                continue
        _LOGGER.exception(
            "Did not receive response within configured timeout period.")
        raise ZigBeeResponseTimeout()

    def _get_parameter(self, parameter, dest_addr_long=None):
        """
        Fetches and returns the value of the specified parameter.
        """
        frame = self._send_and_wait(
            command=parameter, dest_addr_long=dest_addr_long)
        return frame["parameter"]

    def get_sample(self, dest_addr_long=None):
        """
        Initiate a sample and return its data.
        """
        frame = self._send_and_wait(
            command=b"IS", dest_addr_long=dest_addr_long)
        if "parameter" in frame:
            # @TODO: Is there always one value? Is it always a list?
            return frame["parameter"][0]
        return {}

    def read_digital_pin(self, pin_number, dest_addr_long=None):
        """
        Fetches a sample and returns the boolean value of the requested digital
        pin.
        """
        sample = self.get_sample(dest_addr_long=dest_addr_long)
        try:
            return sample[DIGITAL_PINS[pin_number]]
        except KeyError:
            raise ZigBeePinNotConfigured(
                "Pin %s (%s) is not configured as a digital input or output."
                % (pin_number, IO_PIN_COMMANDS[pin_number]))

    def read_analog_pin(self, pin_number, dest_addr_long=None):
        """
        Fetches a sample and returns the integer value of the requested analog
        pin.
        """
        sample = self.get_sample(dest_addr_long=dest_addr_long)
        try:
            return sample[ANALOG_PINS[pin_number]]
        except KeyError:
            raise ZigBeePinNotConfigured(
                "Pin %s (%s) is not configured as an analog input." % (
                    pin_number, IO_PIN_COMMANDS[pin_number]))

    def set_gpio_pin(self, pin_number, setting, dest_addr_long=None):
        """
        Set a gpio pin setting.
        """
        assert setting in GPIO_SETTINGS.values()
        self._send_and_wait(
            command=IO_PIN_COMMANDS[pin_number],
            parameter=setting.value,
            dest_addr_long=dest_addr_long)

    def get_gpio_pin(self, pin_number, dest_addr_long=None):
        """
        Get a gpio pin setting.
        """
        frame = self._send_and_wait(
            command=IO_PIN_COMMANDS[pin_number], dest_addr_long=dest_addr_long)
        value = frame["parameter"]
        return GPIO_SETTINGS[value]

    def get_supply_voltage(self, dest_addr_long=None):
        """
        Fetches the value of %V and returns it as volts.
        """
        value = self._get_parameter(b"%V", dest_addr_long=dest_addr_long)
        return (hex_to_int(value) * (1200/1024.0)) / 1000

    def get_node_name(self, dest_addr_long=None):
        """
        Fetches and returns the value of NI.
        """
        return self._get_parameter(b"NI", dest_addr_long=dest_addr_long)

    def get_temperature(self, dest_addr_long=None):
        """
        Fetches and returns the degrees Celcius value measured by the XBee Pro
        module.
        """
        return hex_to_int(self._get_parameter(
            b"TP", dest_addr_long=dest_addr_long))


class ZigBeeConfig(object):
    """
    Handles the fetching of configuration from the config file for any ZigBee
    entity.
    """
    def __init__(self, config):
        self._config = config
        self._should_poll = config.get("poll", True)

    @property
    def name(self):
        """
        The name given to the entity.
        """
        return self._config["name"]

    @property
    def address(self):
        """
        If an address has been provided, unhexlify it, otherwise return None
        as we're talking to our local ZigBee device.
        """
        address = self._config.get("address")
        if address is not None:
            address = unhexlify(address)
        return address

    @property
    def should_poll(self):
        """
        A bool depicting whether HA should repeatedly poll this device for its
        value.
        """
        return self._should_poll


class ZigBeePinConfig(ZigBeeConfig):
    """
    Handles the fetching of configuration from the config file for a ZigBee
    GPIO pin.
    """
    @property
    def pin(self):
        """
        The GPIO pin number.
        """
        return self._config["pin"]


class ZigBeeDigitalPinConfig(ZigBeePinConfig):
    """
    Handles the fetching of configuration from the config file for a ZigBee
    GPIO pin set to digital in or out.
    """
    def __init__(self, config):
        super(ZigBeeDigitalPinConfig, self).__init__(config)
        self._bool2state, self._state2bool = self.boolean_maps

    @property
    def boolean_maps(self):
        """
        Create dicts to map booleans to pin high/low and vice versa. Depends on
        the config item "on_state" which should be set to "low" or "high".
        """
        if self._config.get("on_state", "").lower() == "low":
            bool2state = {
                True: GPIO_DIGITAL_OUTPUT_LOW,
                False: GPIO_DIGITAL_OUTPUT_HIGH
            }
        else:
            bool2state = {
                True: GPIO_DIGITAL_OUTPUT_HIGH,
                False: GPIO_DIGITAL_OUTPUT_LOW
            }
        state2bool = {v: k for k, v in bool2state.items()}
        return bool2state, state2bool

    @property
    def bool2state(self):
        """
        A dictionary mapping booleans to GPIOSetting objects to translate
        on/off as being pin high or low.
        """
        return self._bool2state

    @property
    def state2bool(self):
        """
        A dictionary mapping GPIOSetting objects to booleans to translate
        pin high/low as being on or off.
        """
        return self._state2bool


class ZigBeeDigitalOutConfig(ZigBeeDigitalPinConfig):
    """
    A subclass of ZigBeeDigitalPinConfig which sets _should_poll to default as
    False instead of True. The value will still be overridden by the presence
    of a 'poll' config entry.
    """
    def __init__(self, config):
        super(ZigBeeDigitalOutConfig, self).__init__(config)
        self._should_poll = config.get("poll", False)


class ZigBeeAnalogInConfig(ZigBeePinConfig):
    """
    Handles the fetching of configuration from the config file for a ZigBee
    GPIO pin set to analog in.
    """
    @property
    def max_voltage(self):
        """
        The voltage at which the ADC will report its highest value.
        """
        return float(self._config.get("max_volts", DEFAULT_ADC_MAX_VOLTS))


class ZigBeeDigitalIn(ToggleEntity):
    """
    ToggleEntity to represent a GPIO pin configured as a digital input.
    """
    def __init__(self, config):
        self._config = config
        self._state = False

        # Poll for initial value
        # @TODO: Make this asynchronous by calling a HA service to do it.
        self.update()

    @property
    def name(self):
        return self._config.name

    @property
    def should_poll(self):
        return self._config.should_poll

    @property
    def is_on(self):
        return self._state

    def update(self):
        """
        Ask the ZigBee device what its output is set to.
        """
        pin_state = DEVICE.get_gpio_pin(
            self._config.pin,
            self._config.address)
        self._state = self._config.state2bool[pin_state]


class ZigBeeDigitalOut(ZigBeeDigitalIn):
    """
    Adds functionality to ZigBeeDigitalIn to control an output.
    """
    def _set_state(self, state):
        DEVICE.set_gpio_pin(
            self._config.pin,
            self._config.bool2state[state],
            self._config.address)
        self._state = state
        self.update_ha_state()

    def turn_on(self, **kwargs):
        self._set_state(True)

    def turn_off(self, **kwargs):
        self._set_state(False)


class ZigBeeAnalogIn(Entity):
    """
    Entity to represent a GPIO pin configured as an analog input.
    """
    def __init__(self, config):
        self._config = config

        # @TODO: Make this asynchronous by calling a HA service to do it.
        self.update()

    @property
    def name(self):
        return self._config.name

    @property
    def should_poll(self):
        return self._config.should_poll

    @property
    def state(self):
        # @TODO: Either decide what type of value to return consistently or
        #        allow it to be configurable.
        return int(self._value_percentage)

    @property
    def unit_of_measurement(self):
        # @TODO: Either decide what type of value to return consistently or
        #        allow it to be configurable.
        return "%"

    @property
    def _value_millivolts(self):
        return self._value_volts * 1000

    @property
    def _value_volts(self):
        return ((self._config.max_voltage / ADC_MAX_VAL) * self._value) * 1000

    @property
    def _value_percentage(self):
        def clamp(num, minn, maxn):
            """
            Clamp num between minn and maxn.
            """
            return max(min(maxn, num), minn)

        return clamp((100.0 / ADC_MAX_VAL) * self._value, 0, 100)

    def update(self):
        """
        Get the latest reading from the ADC.
        """
        # Store the _value as the raw number returned from the device and
        # handle conversion in the properties.
        self._value = DEVICE.read_analog_pin(
            self._config.pin, self._config.address)
