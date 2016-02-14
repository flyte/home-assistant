"""
homeassistant.components.sensor.tcp
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Provides a sensor which gets its values from a TCP socket.
"""
import logging
import socket
import re
from select import select

from homeassistant.components import tcp
from homeassistant.helpers.entity import Entity


DEPENDENCIES = [tcp.DOMAIN]

CONF_HOST = "host"
CONF_PORT = "port"
CONF_TIMEOUT = "timeout"
CONF_PAYLOAD = "payload"
CONF_UNIT = "unit"
CONF_VALUE_REGEX = "value_regex"
CONF_VALUE_ON = "value_on"
CONF_VALUE_OFF = "value_off"
CONF_BUFFER_SIZE = "buffer_size"

DEFAULT_TIMEOUT = 10
DEFAULT_BUFFER_SIZE = 1024

_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """ Create the Sensor. """
    if not validate_sensor_config(config):
        return False
    add_entities((Sensor(config),))


def validate_sensor_config(config):
    """  Ensure the config has all of the necessary values for a Sensor. """
    for required in (CONF_HOST, CONF_PORT, CONF_PAYLOAD):
        if required not in config:
            _LOGGER.error(
                "You must provide %r to create a tcp sensor.", required)
            return False
    return True


class Sensor(Entity):
    """ Generic sensor entity which gets its value from a TCP socket. """
    def __init__(self, config):
        self._name = config.get("name")
        self._host = config[CONF_HOST]
        self._port = config[CONF_PORT]
        self._timeout = config.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
        self._payload = config[CONF_PAYLOAD]
        self._unit = config.get(CONF_UNIT)
        self._value_regex = config.get(CONF_VALUE_REGEX)
        self._buffer_size = config.get(CONF_BUFFER_SIZE, DEFAULT_BUFFER_SIZE)
        self._state = None
        self.update()

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def unit_of_measurement(self):
        return self._unit

    def update(self):
        """ Get the latest value for this sensor. """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect((self._host, self._port))
        except socket.error as err:
            _LOGGER.error(
                "Unable to connect to %s on port %s: %s",
                self._host, self._port, err)
            return
        try:
            sock.send(self._payload.encode())
        except socket.error as err:
            _LOGGER.error(
                "Unable to send payload %r to %s on port %s: %s",
                self._payload, self._host, self._port, err)
            return
        readable, _, _ = select([sock], [], [], self._timeout)
        if not readable:
            _LOGGER.warning(
                "Timeout (%s second(s)) waiting for a response after sending "
                "%r to %s on port %s.",
                self._timeout, self._payload, self._host, self._port)
            return
        value = sock.recv(self._buffer_size).decode()
        if self._value_regex is not None:
            match = re.match(self._value_regex, value)
            if match is None:
                _LOGGER.warning(
                    "Unable to match value using value_regex of %r: %r",
                    self._value_regex, value)
                return
            self._state = match.groups()[0]
            return
        self._state = value
