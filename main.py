import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import decky


MARKER = "# deckhud_lite_managed"
DEFAULT_SETTINGS: Dict[str, Any] = {
    "enabled": True,
    "battery": True,
    "battery_watt": True,
    "battery_time": True,
    "clock": True,
    "clock_seconds": False,
    "fps": False,
    "fan": False,
    "refresh_rate": False,
    "show_fps_limit": False,
    "layout": "horizontal",
    "metric_order": ["battery", "clock", "fps", "fan", "refresh_rate", "show_fps_limit"],
    "vertical_separators": True,
    "separator_style": "pipe",
    "position": "top-right",
    "font_size": 20,
    "background_alpha": 0.35,
}


class Plugin:
    def __init__(self) -> None:
        self.settings: Dict[str, Any] = dict(DEFAULT_SETTINGS)
        self.backups: Dict[str, str] = {}
        self.config_path: Optional[Path] = None
        self._watch_task: Optional[asyncio.Task] = None
        self._stopping = False

    @property
    def _settings_file(self) -> Path:
        return Path(decky.DECKY_PLUGIN_SETTINGS_DIR) / "settings.json"

    @property
    def _backups_file(self) -> Path:
        return Path(decky.DECKY_PLUGIN_SETTINGS_DIR) / "backups.json"

    def _load_json(self, path: Path, fallback: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return fallback

    def _save_json(self, path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    def _validated_settings(self, incoming: Any) -> Dict[str, Any]:
        result = dict(DEFAULT_SETTINGS)
        if not isinstance(incoming, dict):
            return result

        for key in (
            "enabled", "battery", "battery_watt", "battery_time", "clock", "clock_seconds",
            "fps", "fan", "refresh_rate", "show_fps_limit", "vertical_separators"
        ):
            if key in incoming:
                result[key] = bool(incoming[key])

        layout = incoming.get("layout")
        if layout in ("horizontal", "vertical"):
            result["layout"] = layout
        elif "horizontal" in incoming:
            result["layout"] = "horizontal" if bool(incoming["horizontal"]) else "vertical"

        allowed_metrics = list(DEFAULT_SETTINGS["metric_order"])
        incoming_order = incoming.get("metric_order")
        if isinstance(incoming_order, list):
            clean_order = []
            for item in incoming_order:
                if item in allowed_metrics and item not in clean_order:
                    clean_order.append(item)
            result["metric_order"] = clean_order + [item for item in allowed_metrics if item not in clean_order]

        if incoming.get("separator_style") in ("pipe", "dot", "none"):
            result["separator_style"] = incoming["separator_style"]

        if incoming.get("position") in ("top-left", "top-right", "bottom-left", "bottom-right"):
            result["position"] = incoming["position"]

        try:
            result["font_size"] = max(12, min(36, int(incoming.get("font_size", result["font_size"]))))
            result["background_alpha"] = max(
                0.0, min(1.0, round(float(incoming.get("background_alpha", result["background_alpha"])), 2))
            )
        except (TypeError, ValueError):
            pass
        return result

    def _find_mangoapp_config(self) -> Optional[Path]:
        proc = Path("/proc")
        try:
            entries = proc.iterdir()
        except OSError:
            return None

        for entry in entries:
            if not entry.name.isdigit():
                continue
            try:
                cmdline = (entry / "cmdline").read_bytes().replace(b"\x00", b" ").lower()
                if b"mangoapp" not in cmdline:
                    continue
                environ = (entry / "environ").read_bytes().split(b"\x00")
                for item in environ:
                    if item.startswith(b"MANGOHUD_CONFIGFILE="):
                        value = item.split(b"=", 1)[1].decode("utf-8", errors="surrogateescape")
                        path = Path(value)
                        if path.exists() and path.is_file():
                            return path
            except (OSError, ValueError):
                continue
        return None

    def _render_config(self) -> str:
        lines = [
            MARKER,
            "control=mangohud",
            "mangoapp_steam",
            "fsr_steam_sharpness=5",
            "nis_steam_sharpness=10",
            "legacy_layout=0",
            "hud_no_margin",
            f"position={self.settings['position']}",
            f"font_size={self.settings['font_size']}",
            f"background_alpha={self.settings['background_alpha']:.2f}",
            "background_color=020202",
            "alpha=1.0",
            "horizontal_separator_color=808080",
        ]
        if self.settings["layout"] == "horizontal":
            lines.extend(("horizontal", "table_columns=20"))
        else:
            lines.append("table_columns=3")

        lines.append("battery_watt=1" if self.settings["battery_watt"] else "battery_watt=0")
        lines.append("battery_time=1" if self.settings["battery_time"] else "battery_time=0")
        time_value = "%H:%M:%S" if self.settings["clock_seconds"] else "%H:%M"
        lines.append(f"time_format=TIME {time_value}" if self.settings["layout"] == "horizontal" else f"time_format={time_value}")

        enabled_blocks = {
            "battery": self.settings["battery"] or self.settings["battery_watt"] or self.settings["battery_time"],
            "clock": self.settings["clock"],
            "fps": self.settings["fps"],
            "fan": self.settings["fan"],
            "refresh_rate": self.settings["refresh_rate"],
            "show_fps_limit": self.settings["show_fps_limit"],
        }
        config_for_block = {
            "battery": ["battery"],
            "clock": ["time"],
            "fps": ["fps=1"],
            "fan": ["fan"],
            "refresh_rate": ["refresh_rate"],
            "show_fps_limit": ["show_fps_limit"],
        }
        visible_order = [item for item in self.settings["metric_order"] if enabled_blocks.get(item, False)]
        for index, item in enumerate(visible_order):
            lines.extend(config_for_block[item])
            if index < len(visible_order) - 1:
                if self.settings["layout"] == "vertical" and self.settings["vertical_separators"]:
                    lines.append("custom_text=------------")

        # With legacy_layout=0, only display entries present in the config are rendered.
        # Do not add disabled display entries: MangoHud still draws separators for them.
        lines.append("frametime=0")
        return "\n".join(lines) + "\n"

    def _write_managed_config(self, path: Path) -> bool:
        try:
            current = path.read_text(encoding="utf-8", errors="replace")
            desired = self._render_config()
            if not current.startswith(MARKER):
                self.backups[str(path)] = current
                self._save_json(self._backups_file, self.backups)
            if current != desired:
                path.write_text(desired, encoding="utf-8")
            self.config_path = path
            return True
        except OSError as error:
            decky.logger.error("Could not write MangoApp config %s: %s", path, error)
            return False

    def _restore_path(self, path: Path) -> bool:
        try:
            current = path.read_text(encoding="utf-8", errors="replace")
            if not current.startswith(MARKER):
                return True
            original = self.backups.get(str(path))
            if original is None:
                decky.logger.warning("No original config backup exists for %s", path)
                return False
            path.write_text(original, encoding="utf-8")
            return True
        except OSError as error:
            decky.logger.error("Could not restore MangoApp config %s: %s", path, error)
            return False

    def _apply(self) -> bool:
        path = self._find_mangoapp_config() or self.config_path
        if path is None or not path.exists():
            return False
        if self.settings["enabled"]:
            return self._write_managed_config(path)
        return self._restore_path(path)

    async def _watch(self) -> None:
        while not self._stopping:
            try:
                self._apply()
            except Exception as error:
                decky.logger.exception("DeckHUD watcher error: %s", error)
            await asyncio.sleep(1.5)

    async def get_settings(self) -> Dict[str, Any]:
        return dict(self.settings)

    async def save_settings(self, settings: Dict[str, Any]) -> bool:
        was_enabled = bool(self.settings.get("enabled"))
        self.settings = self._validated_settings(settings)
        self._save_json(self._settings_file, self.settings)
        if was_enabled and not self.settings["enabled"] and self.config_path:
            return self._restore_path(self.config_path)
        return self._apply() or self.config_path is None

    async def get_status(self) -> Dict[str, Any]:
        path = self._find_mangoapp_config()
        if path is not None:
            self.config_path = path
        return {
            "connected": self.config_path is not None and self.config_path.exists(),
            "config_path": str(self.config_path) if self.config_path else "",
            "enabled": bool(self.settings["enabled"]),
        }

    async def apply_now(self) -> bool:
        return self._apply()

    async def restore_original(self) -> bool:
        self.settings["enabled"] = False
        self._save_json(self._settings_file, self.settings)
        if self.config_path:
            return self._restore_path(self.config_path)
        return False

    async def _main(self) -> None:
        loaded = self._load_json(self._settings_file, {})
        self.settings = self._validated_settings(loaded)
        self.backups = self._load_json(self._backups_file, {})
        if not isinstance(self.backups, dict):
            self.backups = {}
        self._stopping = False
        self._watch_task = asyncio.create_task(self._watch())
        decky.logger.info("DeckHUD Lite started")

    async def _unload(self) -> None:
        self._stopping = True
        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
        decky.logger.info("DeckHUD Lite stopped")

    async def _uninstall(self) -> None:
        if self.config_path:
            self._restore_path(self.config_path)
