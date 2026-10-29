import gzip
import re
import struct
import sys
import xml.etree.ElementTree as ElementTree
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

from site_contract import ORIGIN, PAGE_ROUTES, STATIC_FILES


class Page(HTMLParser):
    def __init__(self, route):
        super().__init__(convert_charrefs=True)
        self.route = route
        self.ids = Counter()
        self.metadata = {}
        self.canonicals = []
        self.title_parts = []
        self.title_count = 0
        self.in_title = False
        self.headings = 0
        self.languages = []
        self.charsets = []
        self.links = []
        self.resources = set()
        self.snippets = []
        self.active_snippet = None
        self.errors = []

    @property
    def title(self):
        return "".join(self.title_parts).strip()

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        for name, value in attributes:
            if name == "style" or name.startswith("on"):
                self.errors.append(f"{tag}: forbidden inline attribute {name}")
            if value and "javascript:" in value.lower():
                self.errors.append(f"{tag}: forbidden javascript URL")
        if attrs.get("id"):
            self.ids[attrs["id"]] += 1
        if tag == "html":
            self.languages.append(attrs.get("lang", ""))
        if tag == "h1":
            self.headings += 1
        if tag == "title":
            self.title_count += 1
            self.in_title = True
        if tag == "meta":
            if "charset" in attrs:
                self.charsets.append(attrs["charset"].lower())
            key = attrs.get("name", attrs.get("property", "")).lower()
            if key:
                self.metadata.setdefault(key, []).append(attrs.get("content", ""))
        if tag == "link" and "canonical" in attrs.get("rel", "").split():
            self.canonicals.append(attrs.get("href", ""))
        if tag in {"style", "iframe", "object", "embed", "base", "foreignobject"}:
            self.errors.append(f"forbidden element {tag}")
        if tag == "script" and not attrs.get("src"):
            self.errors.append("script requires an external same-origin src")
        if tag == "img" and not attrs.get("alt"):
            self.errors.append("image requires nonempty alt text")
        for name in ("href", "src", "xlink:href", "poster"):
            if name in attrs:
                resource = name in {"src", "poster"} or (
                    tag == "link" and "canonical" not in attrs.get("rel", "").split()
                ) or tag in {"use", "image"}
                self.links.append((attrs[name], resource))
                if resource:
                    self.resources.add(attrs[name])
        if "srcset" in attrs:
            for candidate in attrs["srcset"].split(","):
                if candidate.strip():
                    reference = candidate.strip().split()[0]
                    self.links.append((reference, True))
                    self.resources.add(reference)
        if "data-source" in attrs:
            if tag != "code" or self.active_snippet is not None:
                self.errors.append("data-source must identify a distinct code element")
            self.active_snippet = (attrs["data-source"], [])

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag == "code" and self.active_snippet is not None:
            source, parts = self.active_snippet
            self.snippets.append((source, "".join(parts)))
            self.active_snippet = None

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)
        if self.active_snippet is not None:
            self.active_snippet[1].append(data)


def contained_file(root, relative):
    candidate = root / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError(f"unsafe file path {relative}")
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"file escapes repository: {relative}")
    for parent in (candidate, *candidate.parents):
        if parent == root:
            break
        if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
            raise ValueError(f"symlink or junction is forbidden: {relative}")
    if not candidate.is_file():
        raise ValueError(f"missing regular file: {relative}")
    return candidate


def resolve_reference(page_route, reference):
    return urlsplit(urljoin(ORIGIN + page_route, reference))


def validate_reference(page_route, reference, resource, pages, errors):
    try:
        parsed = resolve_reference(page_route, reference)
    except ValueError as error:
        errors.append(f"{page_route}: invalid URL {reference!r}: {error}")
        return
    if parsed.scheme not in {"https", "mailto"}:
        errors.append(f"{page_route}: unsupported URL {reference!r}")
        return
    if parsed.netloc != urlsplit(ORIGIN).netloc:
        if resource:
            errors.append(f"{page_route}: external resource forbidden: {reference!r}")
        return
    route = unquote(parsed.path)
    if route not in STATIC_FILES:
        errors.append(f"{page_route}: unregistered internal URL {reference!r}")
        return
    if parsed.fragment:
        target = pages.get(route)
        if target is None or unquote(parsed.fragment) not in target.ids:
            errors.append(f"{page_route}: missing fragment target {reference!r}")


def validate_metadata(page, errors):
    expected_url = ORIGIN + page.route
    if page.languages != ["en"]:
        errors.append(f"{page.route}: expected one html element with lang=en")
    if page.charsets != ["utf-8"]:
        errors.append(f"{page.route}: expected one UTF-8 charset declaration")
    if page.headings != 1 or page.title_count != 1 or not page.title:
        errors.append(f"{page.route}: expected one nonempty title and one h1")
    if page.canonicals != [expected_url]:
        errors.append(f"{page.route}: canonical must be {expected_url}")
    required = (
        "description", "viewport", "og:type", "og:site_name", "og:title",
        "og:description", "og:url", "og:image", "og:image:width",
        "og:image:height", "og:image:alt", "twitter:card", "twitter:title",
        "twitter:description", "twitter:image", "twitter:image:alt",
    )
    for key in required:
        values = page.metadata.get(key, [])
        if len(values) != 1 or not values[0].strip():
            errors.append(f"{page.route}: expected one nonempty {key} metadata value")
    value = lambda key: page.metadata.get(key, [""])[0]
    expected = {
        "og:url": expected_url,
        "og:type": "website",
        "og:site_name": "Zore",
        "og:title": page.title,
        "twitter:title": page.title,
        "og:description": value("description"),
        "twitter:description": value("description"),
        "og:image": ORIGIN + "/assets/social-preview.png",
        "twitter:image": ORIGIN + "/assets/social-preview.png",
        "og:image:width": "1200",
        "og:image:height": "630",
        "twitter:card": "summary_large_image",
    }
    for key, content in expected.items():
        if value(key) != content:
            errors.append(f"{page.route}: {key} must equal {content!r}")
    viewport = value("viewport").replace(" ", "")
    if "width=device-width" not in viewport or "initial-scale=1" not in viewport:
        errors.append(f"{page.route}: viewport must use device width and initial scale 1")
    for identifier, count in page.ids.items():
        if count > 1:
            errors.append(f"{page.route}: duplicate id {identifier!r}")
    if page.active_snippet is not None:
        errors.append(f"{page.route}: unclosed data-source code element")
    errors.extend(f"{page.route}: {error}" for error in page.errors)


def validate_svg(relative, data, errors):
    if re.search(rb"<!DOCTYPE|<!ENTITY", data, re.IGNORECASE):
        errors.append(f"{relative}: SVG document declarations are forbidden")
        return
    try:
        svg = ElementTree.fromstring(data)
    except ElementTree.ParseError as error:
        errors.append(f"{relative}: invalid SVG: {error}")
        return
    if svg.tag != "{http://www.w3.org/2000/svg}svg":
        errors.append(f"{relative}: expected SVG namespace and root")
    for element in svg.iter():
        tag = element.tag.rsplit("}", 1)[-1].lower()
        if tag in {"script", "foreignobject", "style", "image", "iframe", "animate", "set"}:
            errors.append(f"{relative}: unsafe SVG element {tag}")
        for attribute, value in element.attrib.items():
            name = attribute.rsplit("}", 1)[-1].lower()
            if name.startswith("on") or name == "style":
                errors.append(f"{relative}: unsafe SVG attribute {name}")
            if name == "href" and not value.startswith("#"):
                errors.append(f"{relative}: external SVG reference {value!r}")
            for reference in re.findall(r"url\(\s*['\"]?([^)'\"]+)", value):
                if not reference.startswith("#"):
                    errors.append(f"{relative}: external SVG paint reference {reference!r}")


def validate(root):
    errors = []
    files = {}
    try:
        registration = (root / "app/files.ore").read_text(encoding="utf-8")
        registered_files = re.findall(
            r'siteFile\{route: "([^"]+)", path: "([^"]+)", mediaType: "([^"]+)"',
            registration,
        )
        if len(registered_files) != len(STATIC_FILES) or {
            route: (path, media_type) for route, path, media_type in registered_files
        } != STATIC_FILES:
            errors.append("app/files.ore registrations differ from the static route contract")
    except (OSError, UnicodeError) as error:
        errors.append(f"cannot read app/files.ore registrations: {error}")
    for route, (relative, media_type) in STATIC_FILES.items():
        try:
            path = contained_file(root, relative)
            limit = 262144 if media_type.startswith(("text/html", "text/plain")) else 1048576
            if not 0 < path.stat().st_size <= limit:
                raise ValueError(f"{relative}: size must be between 1 and {limit} bytes")
            files[route] = path.read_bytes()
        except (OSError, ValueError) as error:
            errors.append(str(error))
    for directory in ("content", "public", "snippets"):
        for path in (root / directory).rglob("*"):
            try:
                if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                    raise ValueError(f"symlink or junction is forbidden: {path.relative_to(root)}")
                if not path.is_dir():
                    contained_file(root, path.relative_to(root))
            except (OSError, ValueError) as error:
                errors.append(str(error))
    pages = {}
    for route in PAGE_ROUTES:
        if route not in files:
            continue
        try:
            page = Page(route)
            page.feed(files[route].decode("utf-8").replace("\r\n", "\n").replace("\r", "\n"))
            page.close()
            pages[route] = page
        except (UnicodeError, ValueError) as error:
            errors.append(f"{route}: invalid HTML: {error}")
    titles = Counter(page.title for page in pages.values())
    snippet_count = 0
    snippet_files = {relative for relative, _ in STATIC_FILES.values() if relative.startswith("snippets/")}
    rendered_snippets = set()
    for page in pages.values():
        validate_metadata(page, errors)
        if titles[page.title] > 1:
            errors.append(f"{page.route}: title is not unique: {page.title!r}")
        for reference, resource in page.links:
            validate_reference(page.route, reference, resource, pages, errors)
        for source, rendered in page.snippets:
            snippet_count += 1
            rendered_snippets.add(source)
            if source not in snippet_files:
                errors.append(f"{page.route}: unregistered snippet source {source!r}")
                continue
            try:
                expected = contained_file(root, source).read_text(encoding="utf-8")
                if rendered != expected:
                    errors.append(f"{page.route}: rendered source differs from {source}")
            except (OSError, ValueError) as error:
                errors.append(f"{page.route}: {error}")
    for source in snippet_files - rendered_snippets:
        errors.append(f"snippet has no rendered data-source example: {source}")
    for route, data in files.items():
        relative, media_type = STATIC_FILES[route]
        if media_type == "image/svg+xml":
            validate_svg(relative, data, errors)
        if media_type.startswith(("text/css", "text/javascript")):
            try:
                text = data.decode("utf-8")
                if re.search(r"(?:https?:)?//[^\s'\"]+|@import\b", text, re.IGNORECASE):
                    errors.append(f"{relative}: remote dependency or CSS import is forbidden")
                if media_type.startswith("text/css"):
                    for reference in re.findall(r"url\(\s*['\"]?([^)'\"]+)", text):
                        validate_reference(route, reference, True, pages, errors)
            except UnicodeError as error:
                errors.append(f"{relative}: invalid UTF-8: {error}")
    png = files.get("/assets/social-preview.png", b"")
    if len(png) < 24 or png[:8] != b"\x89PNG\r\n\x1a\n" or png[12:16] != b"IHDR":
        errors.append("social preview must have a PNG signature and IHDR")
    elif struct.unpack(">II", png[16:24]) != (1200, 630):
        errors.append("social preview must be 1200 by 630 pixels")
    javascript_size = len(gzip.compress(files.get("/assets/site.js", b""), mtime=0))
    if javascript_size > 10240:
        errors.append(f"JavaScript gzip size {javascript_size} exceeds 10240 bytes")
    home_resources = {"/", "/assets/site.css", "/assets/site.js"}
    if "/" in pages:
        for item in pages["/"].resources:
            try:
                home_resources.add(resolve_reference("/", item).path)
            except ValueError:
                pass
    homepage_size = sum(
        len(data) if STATIC_FILES[route][1] == "image/png" else len(gzip.compress(data, mtime=0))
        for route, data in files.items() if route in home_resources
    )
    print(f"Content: {len(pages)} pages, {len(files)} registered files, {snippet_count} matching-source blocks checked")
    print(f"JavaScript gzip: {javascript_size} bytes / 10240 bytes")
    print(f"Homepage compressed resources: {homepage_size} bytes; 307200-byte goal {'met' if homepage_size <= 307200 else 'exceeded'}")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if not errors:
        print("Content validation passed")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(validate(Path(__file__).resolve().parent.parent))
