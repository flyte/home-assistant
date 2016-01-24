import logging
from time import sleep
from datetime import timedelta, datetime
from sys import version_info

try:
    from xbee import ZigBee
except ImportError:
    ZigBee = None


DOMAIN = "zigbee"
REQUIREMENTS = ("xbee", "pyserial")

CONF_DEVICE = "device"
CONF_BAUD = "baud"

DEFAULT_DEVICE = "/dev/ttyUSB0"
DEFAULT_BAUD = 9600

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


class GPIOSetting:
    def __init__(self, name, value):
        self.name = name
        self.value = value

    def __str__(self):
        return self.name


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

log = logging.getLogger(__name__)
log.addHandler(logging.StreamHandler())
log.setLevel(logging.DEBUG)

# Service to set states on ZigBee modules
# Service to request state from ZigBee modules
# Event for incoming state notifications

ser = None
device = None


class ZigBeeException(Exception):
    """
    One exception to rule them all. Catch this if you don't care why it failed.
    """
    pass


class ZigBeeResponseTimeout(ZigBeeException):
    pass


class ZigBeeUnknownError(ZigBeeException):
    pass


class ZigBeeInvalidCommand(ZigBeeException):
    pass


class ZigBeeInvalidParameter(ZigBeeException):
    pass


class ZigBeeTxFailure(ZigBeeException):
    pass


class ZigBeeUnknownStatus(ZigBeeException):
    pass


class ZigBeePinNotConfigured(ZigBeeException):
    pass


def setup(hass, config):
    global device
    global ser
    global ZigBee

    from serial import Serial
    from xbee import ZigBee

    usb_device = config[DOMAIN].get(CONF_DEVICE, DEFAULT_DEVICE)
    baud = int(config[DOMAIN].get(CONF_BAUD, DEFAULT_BAUD))
    ser = Serial(usb_device, baud)
    device = ZigBeeHelper(ser)


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


class ZigBeeHelper(object):
    """
    Adds convenience methods for a ZigBee.
    """
    _rx_frames = {}
    _frame_id = 1

    def __init__(self, ser):
        self._ser = ser
        self._zb = ZigBee(ser, callback=self._frame_received)

    @property
    def next_frame_id(self):
        """
        Gets a byte of the next valid frame ID (1 - 255), increments the
        internal _frame_id counter and wraps it back to 1 if necessary.
        """
        # Python 2/3 compatible way of converting 1 to "\x01" in py2 or b"\x01" in py3.
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
        log.debug("Frame received: %s" % frame)

    def _send(self, **kwargs):
        """
        Send a frame to either the local ZigBee or a remote device.
        """
        if kwargs.get("dest_addr_long") is not None:
            self._zb.remote_at(**kwargs)
        else:
            self._zb.at(**kwargs)

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
        log.exception("Did not receive response within configured timeout period.")
        raise ZigBeeResponseTimeout()

    def _get_parameter(self, parameter, dest_addr_long=None):
        """
        Fetches and returns the value of the specified parameter.
        """
        frame = self._send_and_wait(command=parameter, dest_addr_long=dest_addr_long)
        return frame["parameter"]

    def get_sample(self, dest_addr_long=None):
        """
        Initiate a sample and return its data.
        """
        frame = self._send_and_wait(command=b"IS", dest_addr_long=dest_addr_long)
        if "parameter" in frame:
            return frame["parameter"][0]  # @TODO: Is there always one value? Is it always a list?
        return {}

    def read_digital_pin(self, pin_number, dest_addr_long=None):
        """
        Fetches a sample and returns the boolean value of the requested digital pin.
        """
        sample = self.get_sample(dest_addr_long=dest_addr_long)
        try:
            return sample[DIGITAL_PINS[pin_number]]
        except KeyError:
            raise ZigBeePinNotConfigured(
                "Pin %s (%s) is not configured as a digital input or output." % (
                    pin_number, IO_PIN_COMMANDS[pin_number]))

    def read_analog_pin(self, pin_number, dest_addr_long=None):
        """
        Fetches a sample and returns the integer value of the requested analog pin.
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
