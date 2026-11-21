"""Build a dependency-free local .ankiaddon; never install or deploy it."""

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def build(destination: Path) -> None:
    source = Path(__file__).resolve().parents[1]
    files = [source / name for name in ("__init__.py", "config.json", "manifest.json")]
    for directory in ("models", "services", "ui"):
        files.extend(sorted((source / directory).glob("*.py")))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(source).as_posix())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    build(parser.parse_args().destination)
