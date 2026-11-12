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
HEX_ID_PATTERN = re.compile(r"^(?:0x)?(?P<value>[0-9a-fA-F]{1,4})$")
KNOWN_CONTROLLER_VENDORS = frozenset({"045e", "054c", "057e"})


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


def _normalize_hex_id(value: str | None) -> str | None:
    if not value:
        return None
    match = HEX_ID_PATTERN.fullmatch(value.strip())
    if not match:
        return None
    return f"{int(match.group('value'), 16):04x}"


def resolve_source_identity(
    source_paths: tuple[str, ...],
    command_runner: Callable[[list[str]], str] = run_command,
) -> tuple[str | None, str | None]:
    """Resolve a composite controller identity without guessing from its name."""

    identities: list[tuple[str, str | None]] = []
    for source_path in source_paths:
        try:
            output = command_runner([
                "udevadm",
                "info",
                "--query=property",
                "--name",
                source_path,
            ])
        except (InputPlumberError, OSError, subprocess.CalledProcessError):
            continue
        properties = {}
        for line in output.splitlines():
            key, separator, value = line.partition("=")
            if separator:
                properties[key] = value
        vendor = _normalize_hex_id(properties.get("ID_VENDOR_ID"))
        product = _normalize_hex_id(properties.get("ID_MODEL_ID"))
        if vendor:
            identities.append((vendor, product))

    known_vendors = {
        vendor for vendor, _product in identities if vendor in KNOWN_CONTROLLER_VENDORS
    }
    if len(known_vendors) != 1:
        return None, None
    selected_vendor = next(iter(known_vendors))
    products = {
        product
        for vendor, product in identities
        if vendor == selected_vendor and product is not None
    }
    selected_product = next(iter(products)) if len(products) == 1 else None
    return selected_vendor, selected_product


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
        identity_resolver: Callable[
            [tuple[str, ...]], tuple[str | None, str | None]
        ] = resolve_source_identity,
    ):
        self.command_runner = command_runner
        self.profile_roots = tuple(Path(root) for root in profile_roots)
        self.desktop_profile = Path(desktop_profile)
        self.identity_resolver = identity_resolver

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

    def _string_array_property(
        self, device_path: str, property_name: str
    ) -> tuple[str, ...]:
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
            count = int(parts[1])
        except (ValueError, IndexError) as error:
            raise InputPlumberError(
                f"malformed {property_name} property for {device_path}"
            ) from error
        if not parts or parts[0] != "as" or count < 0 or len(parts[2:]) != count:
            raise InputPlumberError(
                f"malformed {property_name} property for {device_path}"
            )
        return tuple(parts[2:])

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
        devices = []
        for path in paths:
            name = self._string_property(path, "Name")
            profile_name = self._string_property(path, "ProfileName")
            source_paths = self._string_array_property(path, "SourceDevicePaths")
            vendor_id, product_id = self.identity_resolver(source_paths)
            devices.append(ControllerDevice(
                path=path,
                name=name,
                vendor_id=vendor_id,
                product_id=product_id,
                profile_name=profile_name,
            ))
        return devices

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
