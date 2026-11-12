"""Small, shell-free adapter for InputPlumber's system D-Bus API."""

from pathlib import Path
import re
import shlex
import subprocess
from typing import Callable, Iterable

from .model import ControllerDevice


SERVICE = "org.shadowblip.InputPlumber"
INTERFACE = "org.shadowblip.Input.CompositeDevice"
DEVICE_PATTERN = re.compile(
    r"^/org/shadowblip/InputPlumber/CompositeDevice[0-9]+$"
)
PROFILE_NAME_PATTERN = re.compile(
    r"^\s*name\s*:\s*(?P<name>.+?)\s*$", re.MULTILINE
)


class InputPlumberError(RuntimeError):
    pass


def run_command(argv: list[str]) -> str:
    try:
        result = subprocess.run(
            argv,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise InputPlumberError(f"command failed: {argv[0]}") from error
    return result.stdout


class InputPlumberAdapter:
    def __init__(
        self,
        command_runner: Callable[[list[str]], str] = run_command,
        profile_roots: Iterable[Path] = (
            Path("/usr/share/inputplumber/profiles"),
        ),
        desktop_profile: Path = Path(
            "/usr/share/bazzite-hybrid-focus/bazzite-hybrid-desktop.yaml"
        ),
    ):
        self.command_runner = command_runner
        self.profile_roots = tuple(Path(root) for root in profile_roots)
        self.desktop_profile = Path(desktop_profile)

    def _run(self, *argv: str) -> str:
        try:
            return self.command_runner(list(argv))
        except InputPlumberError:
            raise
        except Exception as error:
            raise InputPlumberError(f"InputPlumber command failed: {argv[0]}") from error

    def _string_property(self, device_path: str, property_name: str) -> str:
        output = self._run(
            "busctl",
            "--system",
            "get-property",
            SERVICE,
            device_path,
            INTERFACE,
            property_name,
        )
        try:
            parts = shlex.split(output.strip())
        except ValueError as error:
            raise InputPlumberError(
                f"malformed {property_name} property for {device_path}"
            ) from error
        if len(parts) != 2 or parts[0] != "s":
            raise InputPlumberError(
                f"malformed {property_name} property for {device_path}"
            )
        return parts[1]

    def discover(self) -> list[ControllerDevice]:
        output = self._run(
            "busctl",
            "--system",
            "tree",
            SERVICE,
            "--list",
        )
        paths = sorted(
            {
                line.strip()
                for line in output.splitlines()
                if DEVICE_PATTERN.fullmatch(line.strip())
            }
        )
        return [
            ControllerDevice(
                path=path,
                name=self._string_property(path, "Name"),
                vendor_id=None,
                product_id=None,
                profile_name=self._string_property(path, "ProfileName"),
            )
            for path in paths
        ]

    def resolve_profile(self, profile_name: str) -> Path:
        matches: list[Path] = []
        for root in self.profile_roots:
            if not root.is_dir():
                continue
            for candidate in sorted(root.glob("*.yaml")):
                try:
                    content = candidate.read_text(encoding="utf-8")
                except OSError:
                    continue
                match = PROFILE_NAME_PATTERN.search(content)
                if not match:
                    continue
                name = match.group("name").strip().strip("'\"")
                if name == profile_name:
                    matches.append(candidate)
        if not matches:
            raise InputPlumberError(f"profile {profile_name!r} not found")
        if len(matches) != 1:
            raise InputPlumberError(f"profile {profile_name!r} is ambiguous")
        return matches[0]

    def load_profile(self, device_path: str, profile_path: Path) -> None:
        self._run(
            "busctl",
            "--system",
            "call",
            SERVICE,
            device_path,
            INTERFACE,
            "LoadProfilePath",
            "s",
            str(profile_path),
        )
