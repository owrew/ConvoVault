"""Smoke-test a built wheel and Windows executable using synthetic conversations."""
import hashlib
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.parse import parse_qs, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener


def main():
    root = Path(__file__).resolve().parents[1]
    wheel = root / "dist/convovault-3.0.0-py3-none-any.whl"
    executable = root / "release/ConvoVault-Studio.exe"
    result = {}
    with tempfile.TemporaryDirectory(prefix="convovault-release-") as temporary:
        folder = Path(temporary)
        installed = folder / "installed"
        subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", "--target", str(installed), str(wheel)],
                       check=True, capture_output=True)
        environment = {**os.environ, "PYTHONPATH": str(installed)}
        code = "import json,convovault; from convovault.gui.server import STATIC; print(json.dumps({'version':convovault.__version__,'assets':sorted(p.name for p in STATIC.iterdir())}))"
        check = subprocess.run([sys.executable, "-c", code], cwd=folder, env=environment,
                               check=True, capture_output=True, text=True)
        result["installed_wheel"] = json.loads(check.stdout)
        assert result["installed_wheel"]["version"] == "3.0.0"
        assert result["installed_wheel"]["assets"] == ["app.js", "index.html", "style.css"]
        if os.name == "nt":
            source = root / "examples/studio-demo.json"
            original = hashlib.sha256(source.read_bytes()).hexdigest()
            settings, connection = folder / "settings.json", folder / "connection.json"
            settings.write_text(json.dumps({"provider": "generic", "source": str(source), "vault": str(folder / "vault")}), encoding="utf-8")
            process = subprocess.Popen([str(executable), "--no-browser", "--settings-file", str(settings),
                                        "--connection-file", str(connection)], creationflags=subprocess.CREATE_NO_WINDOW)
            opener = build_opener(HTTPCookieProcessor(CookieJar()))
            try:
                deadline = time.time() + 30
                while not connection.exists() and time.time() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError("Windows executable exited before startup")
                    time.sleep(.1)
                url = json.loads(connection.read_text())["url"]
                token = parse_qs(urlparse(url).query)["token"][0]
                base = url.split("/?")[0]
                with opener.open(url, timeout=10) as response:
                    assert "ConvoVault Studio" in response.read().decode()
                with opener.open(base + "/app.js", timeout=10) as response:
                    assert "renderReader" in response.read().decode()

                def api(path, data=None):
                    req = Request(base + path, headers={"X-ConvoVault-Token": token},
                                  data=None if data is None else json.dumps(data).encode())
                    with opener.open(req, timeout=10) as response:
                        return json.load(response)

                def complete():
                    deadline = time.time() + 20
                    while time.time() < deadline:
                        state = api("/api/state")
                        if not state["job"]["busy"]:
                            assert not state["job"]["error"], state["job"]["error"]
                            return state["job"]["result"]
                        time.sleep(.05)
                    raise RuntimeError("Windows executable job did not complete")

                api("/api/preview", {})
                preview = complete()
                assert preview["total"] == 8
                assert not (folder / "vault").exists()
                api("/api/export", {"selected": ["sample-python", "sample-research"]})
                exported = complete()
                assert exported["written"] == 2
                assert api("/api/conversations?mode=library")["total"] == 2
                assert api("/api/conversations?mode=library&q=parameterized")["total"] == 1
                assert hashlib.sha256(source.read_bytes()).hexdigest() == original
                result["windows_executable"] = {"startup": "passed", "preview_count": 8, "selected_export_count": 2,
                                                 "full_text_search": "passed", "source_unchanged": True}
                api("/api/shutdown", {})
                process.wait(timeout=15)
            finally:
                if process.poll() is None:
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
    (root / "release/verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
