import json
import stat
import sys
import time
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo


ARCHIVE_ROOT = "deckhud-lite"


def zip_info(source: Path, archive_name: str, mode: int, is_dir: bool = False) -> ZipInfo:
    modified = time.localtime(source.stat().st_mtime)[:6]
    info = ZipInfo(archive_name, modified)
    info.create_system = 3
    info.extract_version = 20
    info.external_attr = ((stat.S_IFDIR if is_dir else stat.S_IFREG) | mode) << 16
    info.compress_type = ZIP_STORED if is_dir else ZIP_DEFLATED
    return info


def add_file(archive: ZipFile, source: Path, archive_name: str) -> None:
    archive.writestr(zip_info(source, archive_name, 0o644), source.read_bytes())


def build(project: Path, output: Path) -> None:
    required = [
        project / "LICENSE",
        project / "main.py",
        project / "package.json",
        project / "plugin.json",
        project / "README.md",
        project / "dist" / "index.js",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit(f"missing build files: {missing}")

    package = json.loads((project / "package.json").read_text(encoding="utf-8"))
    if not package.get("version"):
        raise SystemExit("package.json has no version")

    with ZipFile(output, "w") as archive:
        for source in required[:5]:
            add_file(archive, source, f"{ARCHIVE_ROOT}/{source.name}")

        dist = project / "dist"
        directory = zip_info(dist, f"{ARCHIVE_ROOT}/dist/", 0o755, True)
        archive.writestr(directory, b"")
        add_file(archive, dist / "index.js", f"{ARCHIVE_ROOT}/dist/index.js")
        source_map = dist / "index.js.map"
        if source_map.is_file():
            add_file(archive, source_map, f"{ARCHIVE_ROOT}/dist/index.js.map")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: package_plugin.py <project-root> <output.zip>")
    build(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
