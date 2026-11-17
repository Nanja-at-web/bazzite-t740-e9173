"""Every command request is rejected without inspecting argv or invoking spawn."""
from .host_reader import ReadResult


def reject_command(argv, spawn=None):
    return ReadResult(reasons=('command_not_allowed',))
