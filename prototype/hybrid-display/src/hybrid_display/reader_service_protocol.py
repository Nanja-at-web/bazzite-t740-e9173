"""Pure Reader-Service v1 data contract; no transport or runtime integration."""
from dataclasses import dataclass, field
from enum import Enum

VERSION = 1
MAGIC = b'HDR1'
HEADER_SIZE = 16
MAX_REQUEST = 4096
MAX_RESPONSE = 262144
REASONS = ('input_invalid', 'source_not_allowed', 'source_unavailable',
    'source_denied', 'source_limit', 'source_timeout', 'source_type_invalid',
    'ipc_invalid', 'ipc_limit', 'owner_missing', 'owner_invalid',
    'session_unverified', 'inventory_changed', 'kscreen_profile_unverified',
    'client_inventory_unverified', 'reader_deadline_unverified', 'reader_failed',
    'edid_invalid', 'kscreen_unavailable', 'kscreen_schema_invalid')

class MessageType(Enum):
    CAPTURE_IPC = 1
    IPC_CAPTURE_OK = 0x8001
    BLOCKED = 0xffff

@dataclass(frozen=True, slots=True, repr=False)
class Request:
    client_pids: tuple = ()

    def __repr__(self):
        return '<Request>'

    def __post_init__(self):
        if not request_valid(self):
            object.__setattr__(self, 'client_pids', None)

@dataclass(frozen=True, slots=True, repr=False)
class Response:
    reason: str = 'kscreen_profile_unverified'

    def __repr__(self):
        return '<Response>'

    def __post_init__(self):
        if not reason_valid(self.reason):
            object.__setattr__(self, 'reason', None)

@dataclass(frozen=True, slots=True, repr=False)
class Result:
    value: object = field(default=None, repr=False)
    reason: str = ''

    def __repr__(self):
        return '<Result>'

    def __post_init__(self):
        reason = self.reason
        if type(reason) is not str or (reason != '' and not reason_valid(reason)):
            reason = 'reader_failed'
        value = self.value
        valid = (type(value) is bytes and len(value) <= MAX_RESPONSE
                 or integer(value, 0, MAX_RESPONSE)
                 or request_valid(value) or response_valid(value))
        if not valid and not reason:
            reason = 'input_invalid'
        object.__setattr__(self, 'reason', reason)
        if reason:
            object.__setattr__(self, 'value', None)

    @property
    def ok(self):
        return self.value is not None and self.reason == ''


def integer(value, low, high):
    return type(value) is int and low <= value <= high


def reason_valid(value):
    return type(value) is str and len(value) <= 32 and value in REASONS


def request_valid(value):
    if type(value) is not Request:
        return False
    try:
        pids = value.client_pids
        return (type(pids) is tuple and len(pids) <= 16
                and all(integer(pid, 1, 2147483647) for pid in pids)
                and len(set(pids)) == len(pids))
    except AttributeError:
        return False


def response_valid(value):
    if type(value) is not Response:
        return False
    try:
        return reason_valid(value.reason)
    except AttributeError:
        return False


def header(message_type, size):
    return (MAGIC + VERSION.to_bytes(2, 'big') + message_type.value.to_bytes(2, 'big')
            + size.to_bytes(4, 'big') + b'\x00\x00\x00\x01')


def inspect_header(value, response=False):
    if type(value) is not bytes or len(value) != HEADER_SIZE or type(response) is not bool:
        return Result(reason='ipc_invalid')
    if value[:6] != MAGIC + b'\x00\x01' or value[12:] != b'\x00\x00\x00\x01':
        return Result(reason='ipc_invalid')
    number = int.from_bytes(value[6:8], 'big')
    size = int.from_bytes(value[8:12], 'big')
    if size + HEADER_SIZE > (MAX_RESPONSE if response else MAX_REQUEST):
        return Result(reason='ipc_limit')
    if response:
        if number == MessageType.IPC_CAPTURE_OK.value:
            # No native KScreen profile is approved. This is a deliberate gate,
            # not a generic successful-payload escape hatch.
            return Result(reason='kscreen_profile_unverified')
        if number != MessageType.BLOCKED.value or size != 2:
            return Result(reason='ipc_invalid')
    elif number != MessageType.CAPTURE_IPC.value or not 1 <= size <= 65 or (size - 1) % 4:
        return Result(reason='ipc_invalid')
    return Result(size)


def encode_request(value):
    if not request_valid(value):
        return Result(reason='input_invalid')
    body = bytes((len(value.client_pids),)) + b''.join(pid.to_bytes(4, 'big') for pid in value.client_pids)
    return Result(header(MessageType.CAPTURE_IPC, len(body)) + body)


def decode_frame(value, response=False):
    if type(value) is not bytes or len(value) < HEADER_SIZE:
        return Result(reason='ipc_invalid')
    checked = inspect_header(value[:HEADER_SIZE], response)
    if not checked.ok:
        return checked
    if len(value) != HEADER_SIZE + checked.value:
        return Result(reason='ipc_invalid')
    body = value[HEADER_SIZE:]
    if response:
        code = int.from_bytes(body, 'big')
        return Result(Response(REASONS[code - 1] if 1 <= code <= 20 else 'reader_failed'))
    count = body[0]
    if count > 16 or len(body) != 1 + 4 * count:
        return Result(reason='ipc_invalid')
    request = Request(tuple(int.from_bytes(body[index:index + 4], 'big')
                            for index in range(1, len(body), 4)))
    if not request_valid(request):
        return Result(reason='ipc_invalid')
    return Result(request)


def encode_response(value):
    if not response_valid(value):
        return Result(reason='input_invalid')
    return Result(header(MessageType.BLOCKED, 2) + (REASONS.index(value.reason) + 1).to_bytes(2, 'big'))
