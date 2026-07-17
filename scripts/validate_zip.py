import json
import sys
from pathlib import Path
from zipfile import BadZipFile, ZipFile


def validate(zip_path: Path) -> None:
    try:
        with ZipFile(zip_path) as archive:
            names = archive.namelist()
            if any("\\" in name for name in names):
                raise ValueError("ZIP entry paths must use forward slashes")

            plugin_jsons = [
                name for name in names
                if name.endswith("/plugin.json") and name.count("/") == 1
            ]
            if len(plugin_jsons) != 1:
                raise ValueError(f"Decky requires exactly one folder/plugin.json; found {plugin_jsons}")

            root = plugin_jsons[0].split("/", 1)[0]
            required = {
                f"{root}/plugin.json",
                f"{root}/package.json",
                f"{root}/main.py",
                f"{root}/dist/index.js",
            }
            missing = required.difference(names)
            if missing:
                raise ValueError(f"Missing required Decky files: {sorted(missing)}")

            plugin = json.loads(archive.read(f"{root}/plugin.json").decode("utf-8"))
            package = json.loads(archive.read(f"{root}/package.json").decode("utf-8"))
            for key in ("name", "author", "flags", "api_version"):
                if key not in plugin:
                    raise ValueError(f"plugin.json is missing {key!r}")
            if not isinstance(plugin["flags"], list):
                raise ValueError("plugin.json flags must be a list")
            if package.get("type") != "module":
                raise ValueError("package.json must declare ESM module loading")
    except BadZipFile as error:
        raise ValueError("Not a valid ZIP archive") from error


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_zip.py <plugin.zip>")
    target = Path(sys.argv[1]).resolve()
    validate(target)
    print(f"Decky ZIP validation: PASS ({target.name})")
