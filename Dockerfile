FROM ghcr.io/maasdi/zore-builder@sha256:0d61df24b24405ff9a99a0b4bcd25bf603b1c907d70f35ade6204b502a8a7bb1 AS build
WORKDIR /project
COPY zore.toml zore.lock ./
COPY app ./app
COPY content ./content
COPY public ./public
COPY snippets ./snippets
COPY tests/fixtures/shutdown.source /tmp/shutdown.source
RUN test "$(zore --version)" = "zore 0.1.0-alpha.1" \
    && test -z "$(find app content public snippets -type l -print -quit)" \
    && test -z "$(find app content public snippets ! -type f ! -type d -print -quit)" \
    && cp zore.lock /tmp/verified.lock \
    && zore install --locked --offline . \
    && zore fmt --check . \
    && zore check --locked --offline app/main.ore \
    && zore test --locked --offline . \
    && zore run --locked --offline snippets/hello/main.ore > /tmp/hello-output \
    && test "$(cat /tmp/hello-output)" = 'Hello, Zore!' \
    && zore run --locked --offline snippets/ownership/main.ore > /tmp/ownership-output \
    && test "$(cat /tmp/ownership-output)" = 'John' \
    && zore build --locked --offline app/main.ore \
    && mv main site \
    && cmp /tmp/verified.lock zore.lock
RUN mkdir /tmp/shutdown-fixture \
    && cp app/files.ore app/monitoring.ore app/routes.ore /tmp/shutdown-fixture/ \
    && cp /tmp/shutdown.source /tmp/shutdown-fixture/main.ore \
    && zore build --offline /tmp/shutdown-fixture/main.ore \
    && mv main shutdown-fixture

FROM ubuntu:24.04@sha256:78d4744ead1f5b19b04d0df558ab182a5300903900755e515b2ca4d10eb2044d AS runtime
ARG SOURCE_REVISION=unknown
LABEL org.opencontainers.image.title="Zore website" \
      org.opencontainers.image.source="https://github.com/maasdi/zore-website" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      org.opencontainers.image.licenses="Apache-2.0" \
      dev.zore.compiler.version="0.1.0-alpha.1"
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgcc-s1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /project/site /app/site
COPY --from=build /project/content /app/content
COPY --from=build /project/public /app/public
COPY --from=build /project/snippets /app/snippets
USER 65532:65532
EXPOSE 8080
STOPSIGNAL SIGTERM
CMD ["/app/site"]

FROM runtime AS smoke-fixture
COPY --from=build /project/shutdown-fixture /app/site

FROM runtime AS release
