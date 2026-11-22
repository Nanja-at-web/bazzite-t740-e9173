"""Incremental in-memory framing; a complete frame is private until EOF."""
from .reader_service_protocol import (Result, HEADER_SIZE, MAX_REQUEST, MAX_RESPONSE,
    inspect_header, decode_frame)

class Decoder:
    """No reads, waits or allocation from an unvalidated declared body length.

    feed events are bytes, finish models orderly EOF. Event driving and physical
    allocation/time enforcement remain responsibilities of a future native layer.
    """
    def __init__(self, budget, response=False):
        self._budget = budget
        self._response = response
        self._start = budget.last
        self._header = bytearray()
        self._body = bytearray()
        self._size = None
        self._terminal = False
        self._failure = ''
        if type(response) is not bool or self._start is None:
            self._failure = 'input_invalid'

    @property
    def buffered_bytes(self):
        return len(self._header) + len(self._body)

    def _fail(self, reason):
        self._terminal = True
        self._failure = reason
        self._header.clear()
        self._body.clear()
        return Result(reason=reason)

    def _ready(self):
        if self._failure:
            return self._fail(self._failure)
        if self._terminal:
            return self._fail('ipc_invalid')
        deadline = None if self._response else self._start + (.100 if self._size is None else .250)
        checked = self._budget.check(deadline)
        if not checked.ok:
            return self._fail(checked.reason)
        return checked

    def feed(self, chunk):
        checked = self._ready()
        if not checked.ok:
            return checked
        if type(chunk) is not bytes:
            return self._fail('input_invalid')
        limit = MAX_RESPONSE if self._response else MAX_REQUEST
        if len(chunk) > limit - self.buffered_bytes:
            return self._fail('ipc_limit')
        stage_deadline = None if self._response else self._start + (.100 if self._size is None else .250)
        offset = 0
        if self._size is None:
            offset = min(HEADER_SIZE - len(self._header), len(chunk))
            self._header.extend(chunk[:offset])
            if len(self._header) == HEADER_SIZE:
                checked = inspect_header(bytes(self._header), self._response)
                if not checked.ok:
                    return self._fail(checked.reason)
                self._size = checked.value
        if self._size is not None:
            if len(chunk) - offset > self._size - len(self._body):
                return self._fail('ipc_invalid')
            self._body.extend(chunk[offset:])
        checked = self._budget.check(stage_deadline)
        return self._fail(checked.reason) if not checked.ok else Result(0)

    def finish(self):
        checked = self._ready()
        if not checked.ok:
            return checked
        if self._size is None or len(self._body) != self._size:
            return self._fail('ipc_invalid')
        result = decode_frame(bytes(self._header) + bytes(self._body), self._response)
        checked = self._ready()
        self._terminal = True
        self._header.clear()
        self._body.clear()
        if not checked.ok:
            return checked
        return result
