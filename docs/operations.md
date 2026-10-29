# Website operations

## Deployment target

- Canonical site: `https://zore.dev`.
- Temporary Fly hostname: `https://zore-website.fly.dev`.
- Fly app: `zore-website`, organization `personal`, primary region `sin`.
- Runtime: Linux amd64, one shared CPU, 512 MiB, minimum one running Machine.
- Compiler: published `v0.1.0-alpha.1`, pinned builder digest in the Dockerfile.

The domain was not configured when implementation began. Verify the temporary hostname first. Add the app's exact DNS records at the domain provider, then validate the certificate and canonical origin before reporting the public domain as live.

## Promote a tested image

Use the manual Deploy workflow with the run ID of successful main CI. Promotion checks the workflow, repository, branch, event, conclusion, source commit, archive checksum, image identity and provenance labels before deployment. Run only from `main`.

Create a narrowly scoped Fly deploy token with an explicit expiry, store it as the GitHub `FLY_API_TOKEN` secret, and rotate it before expiry. Do not put it in files, command examples or application responses. Restrict production environment access to maintainers as appropriate.

The workflow uses `--ha=false` for the initial single-Machine deployment. A second production Machine is a deliberate availability/cost choice, not a default to create silently.

## After deployment

Verify `/`, `/docs/install`, a CSS asset and the social preview over public HTTPS. Require exact successful GET/HEAD `/uptime` responses and healthy Fly service checks. Check the running image digest and revision against the selected CI artifact.

The native process receives SIGTERM directly. It withdraws readiness and drains admitted work under its ten-second application budget; Fly provides a best-effort 20-second stop allowance. A missing required file prevents startup; a content-read failure permanently withdraws readiness until restart.

## UptimeRobot

Configure a Keyword monitor for `https://zore.dev/uptime`, using GET and alerting when the exact text `{"status":"ok"}` is absent. Restrict accepted status to 200 where supported, enable SSL-error checking and attach the selected alert contacts. The endpoint also accepts HEAD for HTTP-monitor compatibility.

Start with the subscription's available interval; the documented Free interval at planning time is five minutes. Use UptimeRobot's failure confirmation and verify downtime/recovery alert delivery. The endpoint is public and requires no application-side UptimeRobot token.

## Rollback

Retain successful main CI runtime artifacts and their deployed registry digests. To roll back, manually promote a previous successful main run or deploy its recorded immutable registry image. Recheck health, monitoring, homepage and docs after rollback. No database or content migration is involved.

## Outstanding launch checks

DNS/certificate setup for `zore.dev`, UptimeRobot monitor configuration and actual alert delivery must be recorded when completed. Local tests and temporary-hostname checks do not establish those results.
