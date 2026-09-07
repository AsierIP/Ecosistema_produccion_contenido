"""Start Upro locally, sharing an existing server only for the same repository."""
from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import sys
import traceback
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener
import webbrowser


def find_root(explicit: str | None = None) -> Path:
    if explicit:
        candidates = [Path(explicit).expanduser().resolve()]
    else:
        origin = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve()
        candidates = list(origin.parents)
    for candidate in candidates:
        if (candidate / "channels").is_dir() and (candidate / "config").is_dir():
            return candidate
    raise RuntimeError(
        "No se encuentra el proyecto Upro. Mantén el ejecutable dentro del proyecto "
        "o ejecútalo con --root seguido de la carpeta del repositorio."
    )


def same_root(first: str, second: Path) -> bool:
    return os.path.normcase(str(Path(first).resolve())) == os.path.normcase(str(second.resolve()))


def existing_server(port: int, root: Path) -> bool:
    """Do not use proxies or open another application's occupied port."""
    request = Request(f"http://127.0.0.1:{port}/api/health", headers={"Accept": "application/json"})
    try:
        # Windows can take just over two seconds to return WSAECONNREFUSED.
        with build_opener(ProxyHandler({})).open(request, timeout=5) as response:
            body = response.read(65537)
            if len(body) > 65536:
                raise ValueError("health response too large")
            health = json.loads(body)
    except HTTPError as exc:
        raise RuntimeError(f"El puerto {port} ya lo usa otro servicio. Elige otro con --port.") from exc
    except URLError as exc:
        # Connection refusal is the only normal indication that we should start.
        reason = exc.reason
        if isinstance(reason, ConnectionRefusedError) or getattr(reason, "winerror", None) == 10061:
            return False
        raise RuntimeError(f"No se puede comprobar el puerto local {port}: {reason}") from exc
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f"El servicio del puerto {port} no es una instancia válida de Upro.") from exc
    if not isinstance(health, dict) or health.get("app") != "upro" or not isinstance(health.get("root"), str):
        raise RuntimeError(f"El puerto {port} pertenece a otro servicio. Elige otro con --port.")
    if not same_root(health["root"], root):
        raise RuntimeError(
            f"Ya hay otro proyecto Upro en el puerto {port}. "
            "No se ha iniciado ni modificado esa instancia. Elige otro puerto con --port."
        )
    return True


def report_error(exc: BaseException, root: Path | None, *, gui: bool) -> None:
    message = str(exc) or type(exc).__name__
    if root:
        try:
            log = root / ".runtime" / "upro" / "launcher-error.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a", encoding="utf-8") as output:
                output.write("".join(traceback.format_exception(exc)) + "\n")
            message += f"\n\nDetalle: {log}"
        except OSError:
            pass
    if sys.stderr:
        print(f"Upro: {message}", file=sys.stderr)
    if gui and os.name == "nt":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "Upro — no se ha podido iniciar", 0x10)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Upro: producción multicanal local")
    parser.add_argument("--root", help="Carpeta del repositorio con channels/ y config/")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="Iniciar sin abrir el navegador")
    parser.add_argument("--check", action="store_true", help="Comprobar instalación sin iniciar producción")
    args = parser.parse_args(argv)
    root = None
    try:
        if sys.version_info < (3, 12):
            raise RuntimeError("Upro necesita Python 3.12 o posterior.")
        if not 1024 <= args.port <= 65535:
            raise RuntimeError("El puerto debe estar entre 1024 y 65535.")
        root = find_root(args.root)
        if not getattr(sys, "frozen", False):
            sys.path.insert(0, str(root))
        backend = importlib.import_module("ecosystem.upro")
        if args.check:
            return int(backend.main(["--root", str(root), "--check"]) or 0)
        if existing_server(args.port, root):
            if not args.no_browser:
                webbrowser.open(f"http://127.0.0.1:{args.port}/")
            return 0
        backend_args = ["--root", str(root), "--port", str(args.port)]
        if args.no_browser:
            backend_args.append("--no-browser")
        return int(backend.main(backend_args) or 0)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        report_error(exc, root, gui=not (args.no_browser or args.check))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
