ORIGIN = "https://zore.dev"

PAGE_ROUTES = (
    "/",
    "/docs",
    "/docs/install",
    "/docs/first-program",
    "/docs/language",
    "/docs/tools",
    "/docs/status",
)

STATIC_FILES = {
    "/": ("content/index.html", "text/html; charset=utf-8"),
    "/docs": ("content/docs/index.html", "text/html; charset=utf-8"),
    "/docs/install": ("content/docs/install.html", "text/html; charset=utf-8"),
    "/docs/first-program": (
        "content/docs/first-program.html",
        "text/html; charset=utf-8",
    ),
    "/docs/language": ("content/docs/language.html", "text/html; charset=utf-8"),
    "/docs/tools": ("content/docs/tools.html", "text/html; charset=utf-8"),
    "/docs/status": ("content/docs/status.html", "text/html; charset=utf-8"),
    "/assets/site.css": ("public/assets/site.css", "text/css; charset=utf-8"),
    "/assets/site.js": ("public/assets/site.js", "text/javascript; charset=utf-8"),
    "/assets/horizon-wordmark.svg": (
        "public/assets/horizon-wordmark.svg",
        "image/svg+xml",
    ),
    "/assets/horizon-wordmark-dark.svg": (
        "public/assets/horizon-wordmark-dark.svg",
        "image/svg+xml",
    ),
    "/assets/horizon-symbol.svg": (
        "public/assets/horizon-symbol.svg",
        "image/svg+xml",
    ),
    "/assets/horizon-symbol-dark.svg": (
        "public/assets/horizon-symbol-dark.svg",
        "image/svg+xml",
    ),
    "/assets/favicon.svg": ("public/assets/favicon.svg", "image/svg+xml"),
    "/assets/social-preview.png": ("public/assets/social-preview.png", "image/png"),
    "/examples/hello.ore": ("snippets/hello/main.ore", "text/plain; charset=utf-8"),
    "/examples/ownership.ore": (
        "snippets/ownership/main.ore",
        "text/plain; charset=utf-8",
    ),
}
