"""Transactional controller focus state machine."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .inputplumber import InputPlumberAdapter, InputPlumberError
from .model import FocusStatus, FocusTarget, classify_glyph_family


class JsonStateStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "target": "game", "original_profiles": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise InputPlumberError("invalid focus state file") from error
        if data.get("version") != 1 or data.get("target") not in {"game", "desktop"}:
            raise InputPlumberError("unsupported focus state file")
        if not isinstance(data.get("original_profiles"), dict):
            raise InputPlumberError("invalid original profile state")
        return data

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".state-", dir=self.path.parent, text=True
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
                json.dump(data, temporary, sort_keys=True)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, self.path)
            os.chmod(self.path, 0o600)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


class FocusController:
    def __init__(self, adapter: InputPlumberAdapter, state_store: JsonStateStore):
        self.adapter = adapter
        self.state_store = state_store

    def _status(
        self,
        target: FocusTarget,
        devices=(),
        degraded: bool = False,
        message: str = "",
    ) -> FocusStatus:
        devices = tuple(devices)
        return FocusStatus(
            target=target,
            devices=devices,
            glyph_family=classify_glyph_family(devices),
            degraded=degraded,
            message=message,
        )

    def status(self) -> FocusStatus:
        try:
            state = self.state_store.load()
            devices = self.adapter.discover()
            return self._status(FocusTarget(state["target"]), devices)
        except InputPlumberError as error:
            return self._status(FocusTarget.GAME, degraded=True, message=str(error))

    def set_target(self, target: FocusTarget) -> FocusStatus:
        try:
            state = self.state_store.load()
        except InputPlumberError as error:
            return self._status(FocusTarget.GAME, degraded=True, message=str(error))
        current = FocusTarget(state["target"])
        if current == target:
            try:
                devices = self.adapter.discover()
            except InputPlumberError as error:
                return self._status(current, degraded=True, message=str(error))
            return self._status(current, devices)
        if target == FocusTarget.DESKTOP:
            return self._enter_desktop()
        return self._return_to_game(state)

    def toggle(self) -> FocusStatus:
        try:
            state = self.state_store.load()
            current = FocusTarget(state["target"])
        except InputPlumberError as error:
            return self._status(FocusTarget.GAME, degraded=True, message=str(error))
        target = (
            FocusTarget.DESKTOP
            if current == FocusTarget.GAME
            else FocusTarget.GAME
        )
        return self.set_target(target)

    def restore(self) -> FocusStatus:
        return self.set_target(FocusTarget.GAME)

    def _enter_desktop(self) -> FocusStatus:
        try:
            devices = self.adapter.discover()
            if not devices:
                raise InputPlumberError("no InputPlumber composite controller found")
            originals = {
                device.path: self.adapter.resolve_profile(device.profile_name)
                for device in devices
            }
        except InputPlumberError as error:
            return self._status(
                FocusTarget.GAME,
                locals().get("devices", ()),
                degraded=True,
                message=str(error),
            )

        changed = []
        try:
            for device in devices:
                self.adapter.load_profile(device.path, self.adapter.desktop_profile)
                changed.append(device)
        except InputPlumberError as error:
            rollback_errors = []
            for device in reversed(changed):
                try:
                    self.adapter.load_profile(device.path, originals[device.path])
                except InputPlumberError as rollback_error:
                    rollback_errors.append(str(rollback_error))
            message = f"desktop transition failed: {error}"
            if rollback_errors:
                message += "; rollback failed: " + "; ".join(rollback_errors)
            return self._status(
                FocusTarget.GAME, devices, degraded=True, message=message
            )

        self.state_store.save({
            "version": 1,
            "target": "desktop",
            "original_profiles": {
                path: str(profile) for path, profile in originals.items()
            },
        })
        return self._status(
            FocusTarget.DESKTOP, devices, message="Controller → Desktop 2"
        )

    def _return_to_game(self, state: dict[str, Any]) -> FocusStatus:
        originals = {
            path: Path(profile)
            for path, profile in state.get("original_profiles", {}).items()
        }
        if not originals:
            return self._status(
                FocusTarget.DESKTOP,
                degraded=True,
                message="no original controller profiles recorded",
            )
        restored = []
        try:
            for device_path, profile_path in originals.items():
                self.adapter.load_profile(device_path, profile_path)
                restored.append(device_path)
        except InputPlumberError as error:
            rollback_errors = []
            for device_path in reversed(restored):
                try:
                    self.adapter.load_profile(
                        device_path, self.adapter.desktop_profile
                    )
                except InputPlumberError as rollback_error:
                    rollback_errors.append(str(rollback_error))
            message = f"game transition failed: {error}"
            if rollback_errors:
                message += "; rollback failed: " + "; ".join(rollback_errors)
            return self._status(
                FocusTarget.DESKTOP, degraded=True, message=message
            )

        self.state_store.save({
            "version": 1,
            "target": "game",
            "original_profiles": {},
        })
        try:
            devices = self.adapter.discover()
        except InputPlumberError:
            devices = ()
        return self._status(
            FocusTarget.GAME, devices, message="Controller → Game"
        )
