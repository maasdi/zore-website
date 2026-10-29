# Working on the Zore website

Use the README for development guidance and `docs/operations.md` for deployment and monitoring.

- The application is written in Zore and uses only the published `v0.1.0-alpha.1` compiler distribution. Do not build, vendor or patch the compiler in this repository.
- Follow the authoritative language contracts at the matching compiler tag. Do not invent standard-library APIs or source syntax.
- Never add comments to code, references to Markdown files from code, or co-author trailers.
- Keep the Zore logo artwork in `public/assets/` as the single source for website logos.
- The canonical production origin is `https://zore.dev`.
- Register explicit trusted page and asset routes. Never derive a filesystem path from user input.
- `/uptime` supports GET and HEAD, uses no-store caching and returns the application readiness status. Fly uses `/healthz`.
- Keep deployment credentials out of pull-request jobs and source files.
- Validate formatting, locked offline install/check/test/build, content links, HTTP/container behavior and responsive browser rendering. Distinguish local checks from hosted CI and production verification.
- The orchestrator owns integration, validation and reporting. Delegate only focused tasks and keep one writer per file.
