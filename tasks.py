"""Cross-platform task runner (the Makefile delegates here; use directly where `make` is absent).

    python tasks.py setup | prep | dev | test | demo | inventory
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
IS_WIN = os.name == "nt"


def venv_python() -> str:
    for name in ("skyfall_env", ".venv"):
        p = ROOT / name / ("Scripts/python.exe" if IS_WIN else "bin/python")
        if p.exists():
            return str(p)
    return sys.executable


PY = venv_python()
NPM = shutil.which("npm") or "npm"

TEXTURES = {
    "earth-blue-marble.jpg": "https://cdn.jsdelivr.net/npm/three-globe/example/img/earth-blue-marble.jpg",
    "earth-night.jpg": "https://cdn.jsdelivr.net/npm/three-globe/example/img/earth-night.jpg",
    "earth-topology.png": "https://cdn.jsdelivr.net/npm/three-globe/example/img/earth-topology.png",
    "night-sky.png": "https://cdn.jsdelivr.net/npm/three-globe/example/img/night-sky.png",
}


def run(cmd: list[str], cwd: Path = ROOT, env: dict | None = None) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True, env={**os.environ, **(env or {})}, shell=False)


def setup() -> None:
    if PY == sys.executable and not (ROOT / ".venv").exists() and not (ROOT / "skyfall_env").exists():
        run([sys.executable, "-m", "venv", ".venv"])
    py = venv_python()
    run([py, "-m", "pip", "install", "-r", "backend/requirements.txt"])
    if (FRONTEND / "package.json").exists():
        run([NPM, "install"], cwd=FRONTEND)
    tex = FRONTEND / "public" / "textures"
    tex.mkdir(parents=True, exist_ok=True)
    for name, url in TEXTURES.items():
        dst = tex / name
        if dst.exists():
            continue
        try:
            urllib.request.urlretrieve(url, dst)
            print("downloaded", name)
        except Exception as e:  # globe falls back to a solid sphere + country outlines
            print(f"texture {name} not downloaded ({e}); globe will use the fallback style")
    if not (ROOT / ".env").exists():
        shutil.copyfile(ROOT / ".env.example", ROOT / ".env")


def inventory() -> None:
    run([PY, "-m", "backend.scripts.inventory"], env={"PYTHONIOENCODING": "utf-8"})


def prep() -> None:
    inventory()
    if (ROOT / "backend" / "scripts" / "prep.py").exists():
        run([PY, "-m", "backend.scripts.prep"], env={"PYTHONIOENCODING": "utf-8"})


def dev() -> None:
    # no --reload: file watching is unreliable inside OneDrive-synced folders
    procs = [subprocess.Popen([PY, "-m", "uvicorn", "backend.app:app", "--port", "8000"], cwd=ROOT)]
    if (FRONTEND / "package.json").exists():
        procs.append(subprocess.Popen([NPM, "run", "dev"], cwd=FRONTEND, shell=IS_WIN))
    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        for p in procs:
            p.terminate()


def test() -> None:
    run([PY, "-m", "pytest", "backend/tests", "-q"])


def demo() -> None:
    os.environ["DEMO_REPLAY"] = "1"
    dev()


if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "dev"
    {"setup": setup, "prep": prep, "dev": dev, "test": test, "demo": demo, "inventory": inventory}[task]()
