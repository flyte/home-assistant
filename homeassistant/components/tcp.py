"""
homeassistant.components.tcp
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
A generic TCP socket component.
"""
import logging
import socket
import re
from select import select

from homeassistant.const import CONF_NAME, CONF_HOST
from homeassistant.helpers.entity import Entity


DOMAIN = "tcp"

CONF_PORT = "port"
CONF_TIMEOUT = "timeout"
CONF_PAYLOAD = "payload"
CONF_UNIT = "unit"
CONF_VALUE_REGEX = "value_regex"
CONF_VALUE_ON = "value_on"
CONF_BUFFER_SIZE = "buffer_size"

DEFAULT_TIMEOUT = 10
DEFAULT_BUFFER_SIZE = 1024

_LOGGER = logging.getLogger(__name__)


def setup(hass, config):
    """ Nothing to do! """
    return True


class TCPEntity(Entity):
    required = tuple()

    """ Generic Entity which gets its value from a TCP socket. """
    def __init__(self, config):
        """ Set all the config values if they exist and get initial state. """
        self._name = config.get(CONF_NAME)
        self._host = config[CONF_HOST]
        self._port = config[CONF_PORT]
        self._timeout = config.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
        self._payload = config[CONF_PAYLOAD]
        self._unit = config.get(CONF_UNIT)
        self._value_regex = config.get(CONF_VALUE_REGEX)
        self._value_on = config.get(CONF_VALUE_ON)
        self._buffer_size = config.get(
            CONF_BUFFER_SIZE, DEFAULT_BUFFER_SIZE)
        self._state = None
        self.update()

    @classmethod
    def validate_config(cls, config):
        """ Ensure the config has all of the necessary values. """
        always_required = (CONF_HOST, CONF_PORT, CONF_PAYLOAD)
        for key in always_required + tuple(cls.required):
            if key not in config:
                _LOGGER.error(
                    "You must provide %r to create any TCP entity.", key)
                return False
        return True

    @property
    def name(self):
        if self._name is not None:
            return self._name
        return super(TCPEntity, self).name

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
