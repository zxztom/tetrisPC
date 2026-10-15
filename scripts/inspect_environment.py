"""Read only public wrapper metadata and selected window dimensions."""
import json
import os
from pathlib import Path
import platform
import struct
import sys

ROOT = Path(__file__).resolve().parent.parent


def inspect():
    report = {"platform": platform.platform(), "python": sys.version.split()[0],
              "executable": str(ROOT / "tetrio-desktop/TETR.IO.exe"),
              "game_rules_confirmed": False,
              "note": "客户端壳版本不等于在线游戏规则版本；SRS+、180°、重力和键位尚待实际校准。"}
    asar = ROOT / "tetrio-desktop/resources/app.asar"
    if asar.is_file():
        with asar.open("rb") as handle:
            prefix = handle.read(16)
            header = json.loads(handle.read(struct.unpack_from("<I", prefix, 12)[0]))
            package = header["files"]["package.json"]
            handle.seek(8 + struct.unpack_from("<I", prefix, 4)[0] + int(package["offset"]))
            report["desktop_version"] = json.loads(handle.read(package["size"]))["version"]
    config = Path(os.environ.get("APPDATA", "")) / "tetrio-desktop/config.json"
    if config.is_file():
        data = json.loads(config.read_text(encoding="utf-8-sig"))
        report["window"] = {key: data.get(key) for key in
                            ("window-width", "window-height", "window-maximized", "window-fullscreen")}
    return report


if __name__ == "__main__":
    report = inspect()
    destination = ROOT / "output/environment.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(destination)
