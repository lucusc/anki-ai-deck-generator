import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Unit tests load core modules without invoking Anki's entry point.
package = types.ModuleType("addon")
package.__path__ = [str(ROOT)]
sys.modules.setdefault("addon", package)


def load_build():
    spec = importlib.util.spec_from_file_location("addon_build", ROOT / "tools" / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
