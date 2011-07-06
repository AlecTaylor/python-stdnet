'''
This file was originally forked from redis-py in January 2011.
Since than it has moved on a different directions.

Copyright (c) 2010 Andy McCurdy
    BSD License   


'''
import errno
import socket
from itertools import chain

from stdnet.conf import settings
from stdnet.utils import to_bytestring, to_string, is_string,\
                         iteritems, map, ispy3k, is_int, range

if ispy3k:
    toint = lambda x : int(x)
    LENCRLF = 1
    LENCR = 0
else:
    toint = lambda x : long(x)
    LENCRLF = 2
    LENCR = 2

from .exceptions import ConnectionError, ResponseError, InvalidResponse
from .exceptions import RedisError, AuthenticationError


EMPTY = b''
CRLF = b'\r\n'
STAR = b'*'
DOLLAR = b'$'

OK = 'OK'
ERR = 'ERR '
LOADING = 'LOADING '


class PythonParser(object):
    def __init__(self):
        self._fp = None

    def on_connect(self, connection):
        "Called when the socket connects"
        self._fp = connection._sock.makefile('r')

    def on_disconnect(self):
        "Called when the socket disconnects"
        if self._fp is not None:
            self._fp.close()
            self._fp = None

    def read(self, length=None):
        """
        Read a line from the socket is no length is specified,
        otherwise read ``length`` bytes. Always strip away the newlines.
        """
        try:
            if length is not None:
                return self._fp.read(length+LENCRLF)[:-LENCRLF]
            return self._fp.readline()[:-LENCRLF]
        except (socket.error, socket.timeout) as e:
            raise ConnectionError("Error while reading from socket: %s" % \
                (e.args,))

    def read_response(self):
        response = self.read()
        if not response:
            raise ConnectionError("Socket closed on remote end")

        byte, response = response[0], response[1:]

        # server returned an error
        if byte == '-':
            if response.startswith(ERR):
                response = response[4:]
                return ResponseError(response)
            if response.startswith(LOADING):
                # If we're loading the dataset into memory, kill the socket
                # so we re-initialize (and re-SELECT) next time.
                raise ConnectionError("Redis is loading data into memory")
        # single value
        elif byte == '+':
            return response
        # int value
        elif byte == ':':
            return toint(response)
        # bulk response
        elif byte == '$':
            length = int(response)
            if length == -1:
                return None
            return self.read(length)
        # multi-bulk response
        elif byte == '*':
            length = int(response)
            if length == -1:
                return None
            read_response = self.read_response
            return [read_response() for _ in range(length)]
        raise InvalidResponse("Protocol Error")


class HiredisParser(object):
    def on_connect(self, connection):
        self._sock = connection._sock
        self._reader = hiredis.Reader(
            protocolError=InvalidResponse,
            replyError=ResponseError)

    def on_disconnect(self):
        self._sock = None
        self._reader = None

    def read_response(self):
        response = self._reader.gets()
        while response is False:
            try:
                buffer = self._sock.recv(4096)
            except (socket.error, socket.timeout) as e:
                raise ConnectionError("Error while reading from socket: %s" % \
                    (e.args,))
            if not buffer:
                raise ConnectionError("Socket closed on remote end")
            self._reader.feed(buffer)
            # if the data received doesn't end with \r\n, then there's more in
            # the socket
            if not buffer.endswith(CRLF):
                continue
            response = self._reader.gets()
        return response

try:
    import hiredis
    DefaultParser = HiredisParser
except ImportError:
    DefaultParser = PythonParser


class Connection(object):
    "Manages TCP communication to and from a Redis server"
    def __init__(self, host='localhost', port=6379, db=0, password=None,
                 socket_timeout=None, encoding='utf-8',
                 encoding_errors='strict', parser_class=None):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.socket_timeout = socket_timeout
        self.encoding = encoding
        self.encoding_errors = encoding_errors
        self._sock = None
        if parser_class is None:
            if settings.REDIS_PARSER == 'python':
                parser_class = PythonParser
            else:
                parser_class = DefaultParser
        self._parser = parser_class()

    def connect(self):
        "Connects to the Redis server if not already connected"
        if self._sock:
            return
        try:
            sock = self._connect()
        except socket.error as e:
            raise ConnectionError(self._error_message(e))

        self._sock = sock
        self.on_connect()

    def _connect(self):
        "Create a TCP socket connection"
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.socket_timeout)
        sock.connect((self.host, self.port))
        return sock

    def _error_message(self, exception):
        # args for socket.error can either be (errno, "message")
        # or just "message"
        if len(exception.args) == 1:
            return "Error connecting to %s:%s. %s." % \
                (self.host, self.port, exception.args[0])
        else:
            return "Error %s connecting %s:%s. %s." % \
                (exception.args[0], self.host, self.port, exception.args[1])

    def on_connect(self):
        "Initialize the connection, authenticate and select a database"
        self._parser.on_connect(self)

        # if a password is specified, authenticate
        if self.password:
            self.send_command('AUTH', self.password)
            if self.read_response() != 'OK':
                raise ConnectionError('Invalid Password')

        # if a database is specified, switch to it
        if self.db:
            self.send_command('SELECT', self.db)
            if self.read_response() != OK:
                raise ConnectionError('Invalid Database')

    def disconnect(self):
        "Disconnects from the Redis server"
        self._parser.on_disconnect()
        if self._sock is None:
            return
        try:
            self._sock.close()
        except socket.error:
            pass
        self._sock = None

    def _send(self, command):
        "Send the command to the socket"
        if not self._sock:
            self.connect()
        try:
            self._sock.sendall(command)
        except socket.error as e:
            if e.args[0] == errno.EPIPE:
                self.disconnect()
            if len(e.args) == 1:
                _errno, errmsg = 'UNKNOWN', e.args[0]
            else:
                _errno, errmsg = e.args
            raise ConnectionError("Error %s while writing to socket. %s." % \
                (_errno, errmsg))

    def send_packed_command(self, command):
        "Send an already packed command to the Redis server"
        try:
            self._send(command)
        except ConnectionError:
            # retry the command once in case the socket connection simply
            # timed out
            self.disconnect()
            # if this _send() call fails, then the error will be raised
            self._send(command)

    def send_command(self, *args):
        "Pack and send a command to the Redis server"
        self.send_packed_command(self.pack_command(*args))

    def read_response(self):
        "Read the response from a previously sent command"
        response = self._parser.read_response()
        if response.__class__ == ResponseError:
            raise response
        return response

    def encode(self, value):
        "Return a bytestring representation of the value"
        return to_bytestring(value, self.encoding, self.encoding_errors)

    def pack_command(self, *args):
        "Pack a series of arguments into a value Redis command"
        command = [DOLLAR+to_bytestring(len(value))+CRLF+value+CRLF
                   for value in map(self.encode, args)]
        return STAR+to_bytestring(len(command))+CRLF+EMPTY.join(command)
    

class UnixDomainSocketConnection(Connection):
    def __init__(self, path='', db=0, password=None,
                 socket_timeout=None, encoding='utf-8',
                 encoding_errors='strict', parser_class=DefaultParser):
        self.path = path
        self.db = db
        self.password = password
        self.socket_timeout = socket_timeout
        self.encoding = encoding
        self.encoding_errors = encoding_errors
        self._sock = None
        self._parser = parser_class()

    def _connect(self):
        "Create a Unix domain socket connection"
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.socket_timeout)
        sock.connect(self.path)
        return sock

    def _error_message(self, exception):
        # args for socket.error can either be (errno, "message")
        # or just "message"
        if len(exception.args) == 1:
            return "Error connecting to unix socket: %s. %s." % \
                (self.path, exception.args[0])
        else:
            return "Error %s connecting to unix socket: %s. %s." % \
                (exception.args[0], self.path, exception.args[1])


