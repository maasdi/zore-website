# Website operations

## Deployment target

- Canonical site: `https://zore.dev`.
- Temporary Fly hostname: `https://zore-website.fly.dev`.
- Fly app: `zore-website`, organization `personal`, primary region `sin`.
- Runtime: Linux amd64, one shared CPU, 512 MiB, minimum zero running Machines; suspend when idle and resume on traffic.
- Compiler: published `v0.1.0-alpha.1`, pinned builder digest in the Dockerfile.

The canonical domain is live. Public HTTPS `GET https://zore.dev/uptime` returned the exact ready response on 2026-10-29. Keep the temporary Fly hostname available for deployment diagnostics.

## Deploy from the attached repository

Use the existing `zore-website` app in the Fly dashboard. Open Deployments and connect the GitHub repository `maasdi/zore-website`. Select the root `fly.toml` and branch `main`, then enable automatic deployment in the deployment settings. Fly builds the root Dockerfile; its final `release` stage contains the production executable and content.

Repository attachment and the automatic-deployment toggle are dashboard settings. Verify the repository and branch in the dashboard and confirm that a subsequent main push produces a successful Fly deployment before considering the connection complete.

GitHub Actions runs validation only and needs no Fly deployment credential. Its CI checks and Fly's deployments run independently; the Fly integration does not reuse the CI runtime image or wait for the GitHub test suite. The Dockerfile itself checks formatting, native application tests and executable examples during the Fly build.

Keep the existing single Machine. If a CLI deployment is needed, use `flyctl deploy --app zore-website --ha=false` to avoid creating an extra Machine automatically. A second production Machine is a deliberate availability/cost choice.

Deploy the current configuration to apply idle suspension. Fly evaluates idle capacity every few minutes and resumes the Machine for incoming requests. UptimeRobot probes also count as traffic and can wake it; the first request after suspension may take longer.

## After deployment

Verify `/`, `/docs/install`, a CSS asset and the social preview over public HTTPS. Require exact successful GET/HEAD `/uptime` responses and healthy Fly service checks. Record the deployed commit, release and image digest from Fly's deployment details.

The native process receives SIGTERM directly. It withdraws readiness and drains admitted work under its ten-second application budget; Fly provides a best-effort 20-second stop allowance. A missing required file prevents startup; a content-read failure permanently withdraws readiness until restart.

## UptimeRobot

Configure a Keyword monitor for `https://zore.dev/uptime`, using GET and alerting when the exact text `{"status":"ok"}` is absent. Restrict accepted status to 200 where supported, enable SSL-error checking and attach the selected alert contacts. The endpoint also accepts HEAD for HTTP-monitor compatibility.

Start with the subscription's available interval; the documented Free interval at planning time is five minutes. Use UptimeRobot's failure confirmation and verify downtime/recovery alert delivery. The endpoint is public and requires no application-side UptimeRobot token.

## Rollback

Record successful Fly releases and their immutable registry image digests. To roll back, deploy a recorded image using `flyctl deploy --app zore-website --ha=false --image <recorded-image-digest>`. Revert the faulty commit on main as well so future automatic deployments retain the correction. Recheck health, monitoring, homepage and docs after rollback. No database or content migration is involved.

## Outstanding launch checks

UptimeRobot monitor configuration and actual alert delivery must be recorded when completed. A successful public HTTPS probe does not establish external monitor or notification delivery.
