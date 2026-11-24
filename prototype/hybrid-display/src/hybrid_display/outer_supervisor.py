"""Bounded orchestration over trusted injected primitives, never native I/O.

The transient service cgroup is the planned authoritative cleanup boundary.
The launcher owns one session group for first-stage TERM and the KWin lifetime.
Its KWin-created child runs supervise(); returning ends that first stage before
the main process exits. Adapter receipts do not attest live cgroup cleanup,
Same-UID authority, or sandbox enforcement.
"""
from dataclasses import dataclass
from math import isfinite
import re
from .outer_session import Result, Plan, Binary, PROGRAMS, make_plan, parse_outputs, select_outputs, valid_plan


@dataclass(frozen=True, slots=True, repr=False)
class Endpoint:
    uid: int
    runtime: str
    name: str
    expected_name: str
    owner: int
    socket: bool
    safe_components: bool
    identity: tuple


@dataclass(frozen=True, slots=True, repr=False)
class Reply:
    stdout: bytes = b''
    stderr: bytes = b''
    status: int = 0
    timed_out: bool = False
    limited: bool = False


def endpoint_valid(value):
    if type(value) is not Endpoint:
        return False
    return (type(value.uid) is int and 1 <= value.uid <= 2147483647
            and type(value.runtime) is str and value.runtime == '/run/user/' + str(value.uid)
            and type(value.name) is str and len(value.name) <= 64
            and re.fullmatch(r'[A-Za-z0-9_-]+', value.name) is not None
            and type(value.expected_name) is str and value.name == value.expected_name
            and type(value.owner) is int and value.owner == value.uid
            and value.socket is True and value.safe_components is True
            and type(value.identity) is tuple and len(value.identity) == 2
            and all(type(n) is int and n > 0 for n in value.identity))


def _time(clock, last=None):
    value = clock.now()
    if (type(value) is not int and type(value) is not float or not isfinite(value)
            or not 0 <= value <= 1e12 or last is not None and value < last):
        raise ValueError()
    return value


def capture(io, clock):
    try:
        start = last = _time(clock)
        for attempt in range(3):
            endpoint = io.endpoint()
            if not endpoint_valid(endpoint):
                return Result(reason='endpoint_invalid')
            last = _time(clock, last)
            remaining = 5 - (last - start)
            if remaining <= 0:
                return Result(reason='provider_failed')
            allowance = min(2.0, remaining)
            before = last
            reply = io.query(endpoint, allowance, 262144)
            last = _time(clock, last)
            if last - start >= 5 or last - before >= allowance:
                return Result(reason='provider_failed')
            after = io.endpoint()
            if not endpoint_valid(after) or after != endpoint:
                return Result(reason='endpoint_invalid')
            if (type(reply) is not Reply or type(reply.stdout) is not bytes
                    or type(reply.stderr) is not bytes or type(reply.status) is not int
                    or type(reply.timed_out) is not bool or type(reply.limited) is not bool):
                return Result(reason='provider_failed')
            if reply.limited or len(reply.stdout) + len(reply.stderr) > 262144:
                return Result(reason='provider_limit')
            if reply.status == 0 and not reply.timed_out:
                return parse_outputs(reply.stdout)
            if attempt < 2:
                last = _time(clock, last)
                if last - start + .1 >= 5:
                    break
                clock.sleep(.1)
                last = _time(clock, last)
    except (Exception, SystemExit):
        return Result(reason='provider_failed')
    return Result(reason='provider_failed')


def gamescope_argv(plan):
    if type(plan) is not Plan:
        return ()
    return ('/usr/bin/gamescope', '--backend', 'wayland',
            '-W', str(plan.outer_width), '-H', str(plan.outer_height),
            '-w', str(plan.inner_width), '-h', str(plan.inner_height),
            '--steam', '--', '/usr/bin/steam', '-gamepadui')


def supervise(plan, io, clock):
    if type(plan) is not Plan:
        return Result(reason='config_invalid')
    config = {name: getattr(plan, name) for name in
              ('gaming_output_name', 'side_output_name', 'inner_width', 'inner_height',
               'outer_width', 'outer_height', 'execute')}
    if not make_plan(config, tuple(Binary(p, True, True, False) for p in PROGRAMS)).ok:
        return Result(reason='config_invalid')
    if not plan.execute:
        return Result('plan_only')
    try:
        result = _supervise(plan, io, clock)
    except (Exception, SystemExit):
        result = Result(reason='session_failed')
    try:
        if io.finish() is not True:
            result = Result(reason='cleanup_failed')
    except (Exception, SystemExit):
        result = Result(reason='cleanup_failed')
    return result


def _supervise(plan, io, clock):
    try:
        checked = capture(io, clock)
        if not checked.ok:
            return checked
        selected = select_outputs(plan, checked.value)
        if not selected.ok:
            return selected
        if io.wait_ready(5.0) is not True:
            return Result(reason='script_unavailable')
        token = io.start(gamescope_argv(plan))
        if type(token) is not int or token != 1:
            return Result(reason='session_failed')
        start = last = _time(clock)
        while True:
            last = _time(clock, last)
            if last - start >= 43200:
                return Result(reason='session_timeout')
            status = io.poll(token)
            if status is not None:
                if type(status) is not int or status != 0:
                    return Result(reason='session_failed')
                result = Result('ended_without_external_placement_attestation')
                break
            clock.sleep(.05)
    except (Exception, SystemExit):
        result = Result(reason='session_failed')
    return result


def launch_outer(plan, io, clock):
    if not valid_plan(plan) or plan.execute is not True:
        return Result(reason='config_invalid')
    result = Result(reason='session_failed')
    try:
        io.prepare()
        token = io.start_kwin()
        if type(token) is not int or token != 1:
            raise ValueError()
        start = last = _time(clock)
        while True:
            last = _time(clock, last)
            if last - start >= 43200:
                break
            status = io.poll_kwin(token)
            if status is not None:
                if type(status) is int and status == 0:
                    result = Result('ended_without_external_placement_attestation')
                break
            clock.sleep(.05)
    except (Exception, SystemExit):
        result = Result(reason='session_failed')
    try:
        if io.cleanup() is not True:
            result = Result(reason='cleanup_failed')
    except (Exception, SystemExit):
        result = Result(reason='cleanup_failed')
    return result
