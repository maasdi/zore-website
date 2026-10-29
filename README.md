# Zore website

The standalone source for [zore.dev](https://zore.dev), implemented in Zore with the approved Horizon identity. It serves the homepage, six documentation pages, downloadable examples and public monitoring endpoints.

The application uses the published `v0.1.0-alpha.1` compiler. No compiler checkout, submodule or source build is required. Native application compilation still uses the Rust and clang toolchain bundled in the pinned builder image.

## Run locally

Install Docker or Podman, then build the Linux amd64 runtime:

```sh
docker build --platform linux/amd64 --target release -t zore-website:validated .
docker run --rm -p 127.0.0.1:8080:8080 zore-website:validated
```

Open `http://127.0.0.1:8080`. Replace `docker` with `podman` when using Podman. The final image runs a native executable as UID/GID 65532 and contains no compiler, Rust, clang, Node or Python.

The Docker build verifies the compiler version, locked offline installation, formatting, application tests, executable sample output and unchanged dependency lockfile. It also builds a separate shutdown-test executable, which is excluded from the release image.

The public builder is pinned to:

```text
ghcr.io/maasdi/zore-builder@sha256:0d61df24b24405ff9a99a0b4bcd25bf603b1c907d70f35ade6204b502a8a7bb1
```

For direct local Zore commands, install the [matching alpha archive](https://github.com/maasdi/zore/releases/tag/v0.1.0-alpha.1). `check` and `fmt` work without a native toolchain; `build`, `run` and `test` need the documented Rust, clang and host linker prerequisites. `ZORE_SITE_ADDR` changes the bind address; its default is `0.0.0.0:8080`.

## Validate

Python 3.13+, Node 22+ and Chrome/Chromium are used by the development checks. They are not production dependencies.

```sh
python tests/validate_content.py
node --check public/assets/site.js
docker build --platform linux/amd64 --target smoke-fixture -t zore-website:shutdown .
python tests/smoke.py --browser
```

With Podman, use `python tests/smoke.py --engine podman --browser`. Set `BROWSER_PATH` when Chrome is installed outside the detected locations.

The checks verify:

- Fixed page/asset routes, exact binary bytes, MIME, cache policy, security headers, HEAD framing, redirects and rejected private/malformed paths.
- Shared readiness withdrawal after an asset failure and refused startup when required content is missing.
- Nonroot execution, shared libraries and absence of build tools in the runtime.
- An admitted request finishing during SIGTERM while an idle keepalive closes, using an isolated fixture image with no production drain route.
- Seven pages at 320, 375, 768, 1024 and 1440px, menus, copy controls, keyboard skip link, an emulated 200% viewport, and useful documentation without JavaScript.
- Local links/fragments, canonical/social metadata, trusted SVGs, size limits and displayed code matching downloadable source.

Evidence and browser captures are written to `.artifacts/`. Browser clipboard checks use a stub and do not replace the developer's clipboard.

## Content and identity

Author complete trusted HTML in `content/`; shared CSS and progressive clipboard behavior live in `public/assets/`. Add any new file to the explicit Zore route inventory and test contract. Never turn URL input into a filesystem path.

Canonical URLs and sitemap entries use `https://zore.dev`. Essential pages and navigation work without JavaScript. Assets currently use revalidation; content-hashed filenames are required before enabling long immutable caching.

The Horizon identity assets live in `public/assets/`: [light wordmark](public/assets/horizon-wordmark.svg), [dark wordmark](public/assets/horizon-wordmark-dark.svg), [light symbol](public/assets/horizon-symbol.svg) and [dark symbol](public/assets/horizon-symbol-dark.svg). The favicon and social preview are kept alongside them. Use these files directly when updating the identity. Executable examples are in `snippets/`; deployment and monitoring guidance is in [operations](docs/operations.md).

## Monitoring

`GET /uptime` and `HEAD /uptime` support UptimeRobot. `/healthz` uses the same readiness state for Fly service checks.

| State | Status | GET body |
| --- | --- | --- |
| Ready | 200 | `{"status":"ok"}` |
| Unavailable | 503 | `{"status":"unavailable"}` |

Both methods send `Cache-Control: no-store`; HEAD sends the matching headers and content length without a body. Configure UptimeRobot's keyword monitor to GET `https://zore.dev/uptime`, alert when `{"status":"ok"}` is missing, and notify on failure/recovery. Use the interval available in your plan. No UptimeRobot API key is needed by the website.

## Deployment

The Fly app is `zore-website` in the personal organization, initially in Singapore. `fly.toml` configures HTTPS, a service-level `/healthz` check, a 20-second stop allowance and one minimum running Machine. The Zore server drains for up to ten seconds. Initial deployment must disable automatic high availability to avoid creating an extra Machine unexpectedly.

CI builds and tests a runtime image before storing it as an artifact. The manual deployment workflow accepts a successful main CI run, verifies its source and image identity, then promotes that tested image by immutable digest. It does not rebuild during deployment. PR jobs receive no Fly credentials.

Before deploying, configure the GitHub `production` environment, an app-scoped `FLY_API_TOKEN` secret, and optionally `FLY_APP` if the app name changes. Keep credentials in the secret store. Domain/DNS, deployment evidence and rollback details are recorded in [operations](docs/operations.md).

## License

Apache-2.0. Zore remains early alpha; neither this website nor the compiler release declares full MVP conformance or stable language compatibility.
