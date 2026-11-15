"""Single-step lifecycle policy; no operating-system adapter or runtime probes.

Only start accepts launch data, never a caller-selected PID/handle to adopt.
Each instance is one attempt, with a caller label AND a fresh opaque run token.
The trusted spawn adapter alone creates the opaque object() handle and binds it
to a stable native process capability. No integer PID is a signal target here.
Python objects are not a security sandbox against a malicious in-process adapter.

Transitions: PREPARED -> START_REQUESTED -> RUNNING -> EXITED/UNEXPECTED_EXIT.
START_REQUESTED may also exit early (UNEXPECTED_EXIT). stop first inspects and
then verifies ownership; a live owned process -> TERMINATION_REQUESTED.
poll/wait preserve that state until observed exit -> TERMINATED, or the stop
deadline -> TIMEOUT. Adapter/data/clock errors -> BLOCKED/OWNERSHIP_LOST;
spawn exceptions -> START_FAILED. All these terminal states forbid new actions.
Invalid operations return a blocking result without changing the stored state.
There is no restart, escalation, name lookup, process group or child discovery.
An unresolved child needs separately authorized manual recovery, never a claim
that the desktop/display has been restored. No hardware acceptance is implied.
"""

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from typing import Protocol
from collections.abc import Mapping
from .command import ArgvResult, EnvironmentResult, build_child_env


class State(Enum):
    PREPARED = 'prepared'
    START_REQUESTED = 'start_requested'
    RUNNING = 'running'
    EXITED = 'exited'
    START_FAILED = 'start_failed'
    UNEXPECTED_EXIT = 'unexpected_exit'
    TERMINATION_REQUESTED = 'termination_requested'
    TERMINATED = 'terminated'
    TIMEOUT = 'timeout'
    OWNERSHIP_LOST = 'ownership_lost'
    BLOCKED = 'blocked'


@dataclass(frozen=True)
class OwnedIdentity:
    """Adapter receipt. PID describes; opaque handle + generation + run bind.

handle must be an adapter-created object() sentinel, with identity semantics.
The future adapter must retain its association with a stable native handle;
verify-then-signal by numeric PID is explicitly outside this contract.
All fields are hidden because adapter metadata is not diagnostic output.
"""
    handle: object = field(repr=False)
    pid: int = field(repr=False)
    generation: str = field(repr=False)
    run_id: str = field(repr=False)
    run_token: object = field(default=None, repr=False)


@dataclass(frozen=True)
class Observation:
    """Adapter-reported status: running/no exit code or exited/integer code."""
    identity: OwnedIdentity = field(repr=False)
    status: str = field(repr=False)
    exit_code: int | None = field(default=None, repr=False)


@dataclass(frozen=True)
class RunResult:
    """Immutable snapshot. Only fixed policy codes; never adapter exception text."""
    state: State
    reasons: tuple[str, ...] = ()
    handle: OwnedIdentity | None = field(default=None, repr=False)
    exit_code: int | None = None

    @property
    def ok(self):
        return not self.reasons

    @property
    def status(self):
        return 'success' if self.ok else 'blocked'


class ProcessAdapter(Protocol):
    """Declarations only. No OS implementation is supplied in this stage.

spawn creates one new owned process and returns a receipt bound to run_token.
A failure after creating a child must be reported as unresolved, not retried.
inspect/wait refer only to that stable handle and return an identity receipt.
verify_ownership returns the complete current identity, or None on uncertainty.
request_terminate atomically addresses the SAME stable native instance, never
a numeric PID after a separate check. True acknowledges only the request,
not process exit. It offers no force/kill option. wait performs at most one
bounded progress operation, never exceeds timeout, and never signals/restarts.
Adapters may raise ordinary exceptions; messages are discarded by this policy.
"""

    def spawn(self, argv: tuple[str, ...], child_env: Mapping[str, str],
              run_id: str, run_token: object) -> OwnedIdentity: ...

    def inspect(self, handle: OwnedIdentity) -> Observation: ...

    def verify_ownership(self, handle: OwnedIdentity) -> OwnedIdentity | None: ...

    def request_terminate(self, handle: OwnedIdentity) -> bool: ...

    def wait(self, handle: OwnedIdentity, timeout: float) -> Observation: ...


class Clock(Protocol):
    """Supplied monotonic, finite, nonnegative seconds; no real clock imported."""

    def now(self) -> float: ...


def _finite_number(value):
    try:
        return type(value) in (int, float) and isfinite(value)
    except OverflowError:
        return False


class Lifecycle:
    """One in-memory run; adapter and clock injected, no background progress.

timeout is a stop grace period, strictly positive and at most 300 seconds
(conservative MVP policy, not a discovered runtime limit). wait is explicit;
no automatic action is taken when wall time elapses. Running a game has no
global lifetime limit. Safe handles are withheld after terminal/error outcomes.
"""

    def __init__(self, run_id: str, adapter: ProcessAdapter, clock: Clock, timeout=5):
        self._run_id, self._adapter, self._clock = run_id, adapter, clock
        self._run_token = object()
        self._timeout = timeout
        self._last_time = None
        self._result = RunResult(State.PREPARED)
        reasons = []
        if not _finite_number(timeout) or not 0 < timeout <= 300:
            reasons.append('timeout_invalid')
        if not isinstance(run_id, str) or not run_id.strip() or '\0' in run_id:
            reasons.append('run_id_invalid')
        if reasons:
            self._result = RunResult(State.BLOCKED, tuple(sorted(reasons)))

    @property
    def result(self):
        return self._result

    def start(self, command, environment):
        if self._result.state is State.BLOCKED:
            return self._result
        if self._result.state is not State.PREPARED:
            return RunResult(self._result.state, ('invalid_transition',))
        if (not isinstance(command, ArgvResult) or not command.ok
                or not isinstance(command.argv, tuple) or not command.argv
                or any(not isinstance(a, str) or '\0' in a for a in command.argv)
                or not command.argv[0].strip()):
            self._result = RunResult(State.BLOCKED, ('command_blocked',))
            return self._result
        if not isinstance(environment, EnvironmentResult) or not environment.ok:
            self._result = RunResult(State.BLOCKED, ('environment_blocked',))
            return self._result
        checked = build_child_env(environment.child_env)
        if not checked.ok or checked.child_env != environment.child_env:
            self._result = RunResult(State.BLOCKED, ('environment_blocked',))
            return self._result
        if self._now() is None:
            return self._result
        self._result = RunResult(State.START_REQUESTED)
        try:
            identity = self._adapter.spawn(tuple(command.argv), dict(checked.child_env), self._run_id, self._run_token)
        except Exception:
            self._result = RunResult(State.START_FAILED, ('spawn_failed',))
            return self._result
        if not self._valid_identity(identity):
            self._result = RunResult(State.OWNERSHIP_LOST, ('identity_invalid',))
            return self._result
        self._identity = identity
        self._result = RunResult(State.START_REQUESTED, handle=identity)
        return self._result

    def _valid_identity(self, identity):
        return (isinstance(identity, OwnedIdentity) and type(identity.handle) is object
                and type(identity.pid) is int and identity.pid > 0
                and isinstance(identity.generation, str) and bool(identity.generation.strip())
                and isinstance(identity.run_id, str) and identity.run_id == self._run_id
                and identity.run_token is self._run_token)

    def poll(self):
        if self._result.state not in (State.START_REQUESTED, State.RUNNING, State.TERMINATION_REQUESTED):
            return RunResult(self._result.state, ('invalid_transition',))
        if self._now() is None:
            return self._result
        if self._result.state is State.TERMINATION_REQUESTED and self._last_time >= self._deadline:
            self._result = RunResult(State.TIMEOUT, ('termination_timeout',))
            return self._result
        try:
            observation = self._adapter.inspect(self._identity)
        except Exception:
            self._result = RunResult(State.BLOCKED, ('inspect_failed',))
            return self._result
        if self._now() is None:
            return self._result
        return self._observe(observation)

    def stop(self):
        if self._result.state not in (State.START_REQUESTED, State.RUNNING):
            return RunResult(self._result.state, ('invalid_transition',))
        if self._now() is None:
            return self._result
        self.poll()
        if self._result.state is not State.RUNNING:
            return self._result
        if not self._verify():
            return self._result
        if self._now() is None:
            return self._result
        self._deadline = self._last_time + self._timeout
        if not _finite_number(self._deadline) or self._deadline <= self._last_time:
            self._result = RunResult(State.BLOCKED, ('deadline_invalid',))
            return self._result
        self._result = RunResult(State.TERMINATION_REQUESTED, handle=self._identity)
        try:
            acknowledged = self._adapter.request_terminate(self._identity)
        except Exception:
            self._result = RunResult(State.BLOCKED, ('termination_failed',))
            return self._result
        if acknowledged is not True:
            self._result = RunResult(State.BLOCKED, ('termination_unconfirmed',))
        return self._result

    def wait(self):
        if self._result.state is not State.TERMINATION_REQUESTED:
            return RunResult(self._result.state, ('invalid_transition',))
        now = self._now()
        if now is None:
            return self._result
        if now >= self._deadline:
            self._result = RunResult(State.TIMEOUT, ('termination_timeout',))
            return self._result
        if not self._verify():
            return self._result
        now = self._now()
        if now is None:
            return self._result
        if now >= self._deadline:
            self._result = RunResult(State.TIMEOUT, ('termination_timeout',))
            return self._result
        try:
            observation = self._adapter.wait(self._identity, self._deadline - now)
        except Exception:
            self._result = RunResult(State.BLOCKED, ('wait_failed',))
            return self._result
        if self._now() is None:
            return self._result
        return self._observe(observation)

    def _verify(self):
        try:
            receipt = self._adapter.verify_ownership(self._identity)
        except Exception:
            self._result = RunResult(State.OWNERSHIP_LOST, ('ownership_check_failed',))
            return False
        if not self._same_identity(receipt):
            self._result = RunResult(State.OWNERSHIP_LOST, ('ownership_unverified',))
            return False
        return True

    def _now(self):
        try:
            now = self._clock.now()
        except Exception:
            self._result = RunResult(State.BLOCKED, ('clock_failed',))
            return None
        if not _finite_number(now) or now < 0:
            self._result = RunResult(State.BLOCKED, ('clock_invalid',))
            return None
        if self._last_time is not None and now < self._last_time:
            self._result = RunResult(State.BLOCKED, ('clock_reversed',))
            return None
        self._last_time = now
        return now

    def _same_identity(self, identity):
        return (self._valid_identity(identity)
                and identity.handle is self._identity.handle
                and identity.pid == self._identity.pid
                and identity.generation == self._identity.generation)

    def _observe(self, observation):
        if isinstance(observation, Observation) and not self._same_identity(observation.identity):
            self._result = RunResult(State.OWNERSHIP_LOST, ('identity_mismatch',))
            return self._result
        if (not isinstance(observation, Observation)
                or observation.status not in ('running', 'exited')
                or (observation.status == 'running' and observation.exit_code is not None)
                or (observation.status == 'exited' and type(observation.exit_code) is not int)):
            self._result = RunResult(State.BLOCKED, ('observation_invalid',))
            return self._result
        if observation.status == 'exited':
            if self._result.state is State.TERMINATION_REQUESTED:
                self._result = RunResult(State.TERMINATED, exit_code=observation.exit_code)
                return self._result
            early = self._result.state is State.START_REQUESTED
            reasons = ('early_exit',) if early else ('nonzero_exit',) if observation.exit_code else ()
            self._result = RunResult(State.UNEXPECTED_EXIT if reasons else State.EXITED,
                                     reasons, exit_code=observation.exit_code)
        else:
            state = State.TERMINATION_REQUESTED if self._result.state is State.TERMINATION_REQUESTED else State.RUNNING
            if state is State.TERMINATION_REQUESTED and self._last_time >= self._deadline:
                self._result = RunResult(State.TIMEOUT, ('termination_timeout',))
            else:
                self._result = RunResult(state, handle=self._identity)
        return self._result
