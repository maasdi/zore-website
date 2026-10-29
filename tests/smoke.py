import argparse
import http.client
import json
from pathlib import Path
import socket
import subprocess
import time
import uuid
import xml.etree.ElementTree as ElementTree

from site_contract import ORIGIN, PAGE_ROUTES, STATIC_FILES


ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class Containers:
    def __init__(self, engine):
        self.engine = engine

    def command(self, *arguments, timeout=60, check=True):
        result = subprocess.run(
            [self.engine, *arguments], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        if check and result.returncode:
            raise RuntimeError(f"{arguments!r}: {result.stdout}{result.stderr}")
        return result

    def inspect(self, name):
        return json.loads(self.command("inspect", name).stdout)[0]

    def start(self, image, name):
        self.command("run", "--detach", "--name", name, "--publish", "127.0.0.1::8080", image)
        ports = self.inspect(name)["NetworkSettings"]["Ports"]["8080/tcp"]
        return int(ports[0]["HostPort"])

    def remove(self, name):
        self.command("rm", "--force", name, check=False)


def exchange(port, method, path, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict((key.lower(), value) for key, value in response.getheaders()), response.read()
    finally:
        connection.close()


def wait_until(predicate, message, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError(message)


def ready(port):
    try:
        status, _, body = exchange(port, "GET", "/healthz")
        return status == 200 and body == b'{"status":"ok"}'
    except (OSError, http.client.HTTPException):
        return False


def monitoring(port, status, expected):
    for route in ("/healthz", "/uptime"):
        for method in ("GET", "HEAD"):
            code, headers, body = exchange(port, method, route)
            require(code == status, f"{method} {route}: status {code}")
            require(headers.get("cache-control") == "no-store", f"{route}: cached monitoring response")
            require(headers.get("content-type") == "application/json", f"{route}: incorrect JSON type")
            require(headers.get("content-length") == str(len(expected)), f"{route}: incorrect length")
            require(body == (expected if method == "GET" else b""), f"{method} {route}: incorrect body")


def static_routes(port):
    for route, (filename, media_type) in STATIC_FILES.items():
        expected = (ROOT / filename).read_bytes()
        for method in ("GET", "HEAD"):
            code, headers, body = exchange(port, method, route)
            require(code == 200, f"{method} {route}: status {code}")
            require(body == (expected if method == "GET" else b""), f"{method} {route}: bytes differ")
            require(headers.get("content-length") == str(len(expected)), f"{route}: content length differs")
            require(headers.get("content-type") == media_type, f"{route}: MIME differs")
            require(headers.get("x-content-type-options") == "nosniff", f"{route}: nosniff missing")
            policy = headers.get("content-security-policy", "")
            require("default-src 'none'" in policy and "unsafe-inline" not in policy, f"{route}: CSP differs")
            expected_cache = "no-cache"
            require(headers.get("cache-control") == expected_cache, f"{route}: cache policy differs")


def routing(port):
    for route in PAGE_ROUTES[1:]:
        code, headers, body = exchange(port, "GET", route + "/?from=monitor")
        require(code == 308 and headers.get("location") == route + "?from=monitor", f"{route}: redirect differs")
        require(not body, f"{route}: redirect has unexpected content")
    for route in ("/not-a-page", "/.env", "/zore.toml", "/app/main.ore", "/drain"):
        code, _, _ = exchange(port, "GET", route)
        require(code in (400, 404), f"private or unknown path served: {route}: {code}")
    for route in ("/%2e%2e/zore.toml", "/assets/%2fsite.css", "/assets/%5csite.css", "/assets/%00"):
        code, _, _ = exchange(port, "GET", route)
        require(400 <= code < 500, f"malformed path accepted: {route}")
    code, headers, _ = exchange(port, "POST", "/uptime")
    require(code == 405 and "GET" in headers.get("allow", "") and "HEAD" in headers.get("allow", ""), "method policy differs")
    code, _, data = exchange(port, "GET", "/sitemap.xml", {"Host": "untrusted.invalid"})
    require(code == 200, "sitemap failed")
    tree = ElementTree.fromstring(data)
    locations = [node.text for node in tree.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    require(locations == [ORIGIN + route for route in PAGE_ROUTES], "sitemap origin or pages differ")
    code, _, robots = exchange(port, "GET", "/robots.txt")
    require(code == 200 and f"Sitemap: {ORIGIN}/sitemap.xml".encode() in robots, "robots origin differs")


def runtime_shape(containers, image):
    info = containers.inspect(image)
    require(info["Architecture"] == "amd64" and info["Os"] == "linux", "runtime architecture differs")
    require(info["Config"]["User"] == "65532:65532", "runtime is not nonroot")
    require(info["Config"]["Cmd"] == ["/app/site"] and not info["Config"].get("Entrypoint"), "runtime command intercepts signals")
    libraries = containers.command("run", "--rm", "--entrypoint", "/usr/bin/ldd", image, "/app/site").stdout
    require("not found" not in libraries, "runtime shared libraries missing")
    containers.command(
        "run", "--rm", "--entrypoint", "/bin/sh", image, "-ec",
        'test "$(id -u)" = 65532; '
        'for tool in zore rustc rustup cargo clang cc gcc git python3 node; do '
        'if command -v "$tool"; then exit 1; fi; done; '
        'test ! -e /opt/rust; test ! -e /opt/cargo; test ! -e /app/app; '
        'test "$(find /app -type f | wc -l)" -eq 18',
    )
    return {"image_id": info["Id"], "architecture": info["Architecture"], "labels": info["Config"].get("Labels")}


def shutdown(containers, image):
    name = "zore-website-drain-" + uuid.uuid4().hex
    active = None
    idle = None
    try:
        port = containers.start(image, name)
        wait_until(lambda: ready(port), "shutdown fixture did not start")
        idle = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        idle.request("GET", "/healthz")
        response = idle.getresponse()
        require(response.status == 200 and response.read() == b'{"status":"ok"}', "idle connection failed")
        idle_socket = idle.sock
        require(idle_socket is not None, "keepalive was not established")
        active = socket.create_connection(("127.0.0.1", port), timeout=5)
        active.sendall(b"POST /drain HTTP/1.1\r\nHost: localhost\r\nContent-Length: 1\r\nConnection: close\r\n\r\n")
        wait_until(lambda: "drain-request-admitted" in containers.command("logs", name).stdout, "request was not admitted")
        started = time.monotonic()
        containers.command("kill", "--signal=SIGTERM", name)
        idle_socket.settimeout(2)
        try:
            require(idle_socket.recv(1) == b"", "idle connection survived shutdown")
        except ConnectionResetError:
            pass
        require(containers.inspect(name)["State"]["Running"], "server exited before request drained")
        active.sendall(b"x")
        drained = http.client.HTTPResponse(active)
        drained.begin()
        require(drained.status == 200 and drained.read() == b"drained", "admitted request did not finish")
        require(containers.command("wait", name, timeout=6).stdout.strip() == "0", "shutdown exit status differs")
        require(time.monotonic() - started < 6, "shutdown exceeded the tested bound")
    finally:
        if active is not None:
            active.close()
        if idle is not None:
            idle.close()
        containers.remove(name)


def smoke(engine, image, fixture_image, browser):
    containers = Containers(engine)
    evidence = runtime_shape(containers, image)
    name = "zore-website-smoke-" + uuid.uuid4().hex
    try:
        port = containers.start(image, name)
        wait_until(lambda: ready(port), "website did not start")
        monitoring(port, 200, b'{"status":"ok"}')
        static_routes(port)
        routing(port)
        if browser:
            subprocess.run(["node", "tests/browser.mjs", "--base-url", f"http://127.0.0.1:{port}"], cwd=ROOT, check=True, timeout=180)
        containers.command("exec", "--user", "0:0", name, "rm", "/app/public/assets/site.css")
        code, _, body = exchange(port, "GET", "/assets/site.css")
        require(code == 500 and body == b"Internal server error\n", "content failure exposed details or remained successful")
        monitoring(port, 503, b'{"status":"unavailable"}')
        containers.command("kill", "--signal=SIGTERM", name)
        require(containers.command("wait", name, timeout=15).stdout.strip() == "0", "website did not stop cleanly")
    except BaseException:
        print(containers.command("logs", name, check=False).stdout)
        raise
    finally:
        containers.remove(name)
    failed = containers.command(
        "run", "--rm", "--user", "0:0", "--entrypoint", "/bin/sh", image,
        "-ec", "rm /app/content/docs/status.html; exec /app/site", check=False, timeout=15,
    )
    require(failed.returncode != 0 and "website stopped with an error" in failed.stderr, "missing content did not prevent startup")
    shutdown(containers, fixture_image)
    evidence.update({"static_routes": len(STATIC_FILES), "monitoring": "GET and HEAD ready/unready", "shutdown": "active request drained; idle connection closed", "browser": browser})
    destination = ROOT / ".artifacts"
    destination.mkdir(exist_ok=True)
    (destination / "smoke.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("Passed runtime, HTTP, GET/HEAD monitoring, failure and SIGTERM drain checks")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", default="docker")
    parser.add_argument("--image", default="zore-website:validated")
    parser.add_argument("--fixture-image", default="zore-website:shutdown")
    parser.add_argument("--browser", action="store_true")
    options = parser.parse_args()
    smoke(options.engine, options.image, options.fixture_image, options.browser)
