FROM zore-website:build AS checks
COPY tests/fixtures/shutdown.source /tmp/shutdown.source
RUN zore fmt --check . \
    && zore check --locked --offline app/main.ore \
    && zore test --locked --offline . \
    && zore run --locked --offline snippets/hello/main.ore > /tmp/hello-output \
    && test "$(cat /tmp/hello-output)" = 'Hello, Zore!' \
    && zore run --locked --offline snippets/ownership/main.ore > /tmp/ownership-output \
    && test "$(cat /tmp/ownership-output)" = 'John' \
    && cmp /tmp/verified.lock zore.lock
RUN mkdir /tmp/shutdown-fixture \
    && cp app/monitoring.ore app/responses.ore app/logging.ore /tmp/shutdown-fixture/ \
    && cp /tmp/shutdown.source /tmp/shutdown-fixture/main.ore \
    && zore build --offline /tmp/shutdown-fixture/main.ore \
    && mv main shutdown-fixture

FROM zore-website:validated AS smoke-fixture
COPY --from=checks /project/shutdown-fixture /app/site
