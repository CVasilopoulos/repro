# Repro

**Turns a GitHub bug report into a verified reproduction, with every command run in a throwaway sandbox on Vultr.**

Built for the Vultr Agent Rush hackathon (challenge 1, Blast Radius Zero). Work in progress: the full README, architecture and demo link are coming during the build week (Nov 3-8, 2026).

## What it does

Paste a GitHub issue URL. Repro:

1. reads the issue (as untrusted input);
2. starts a fresh sandbox, clones the repository and writes `setup.sh` and `repro.sh`, a minimal reproduction that exits 1 when the bug is present and 0 when it is not;
3. hands both scripts to the backend, which re-runs them in two new sandboxes, at the reported commit and on the default branch;
4. derives the verdict from those exit codes: reproduced, fixed on the default branch, not reproducible, flaky or inconclusive;
5. returns an evidence report with every command, exit code, duration and output hash, plus every network request the sandboxes made.

The model proposes; the sandbox decides.

## Containment

- one container per task, destroyed afterwards, on gVisor (`runsc`);
- read-only root filesystem, writable tmpfs only, non-root user, all capabilities dropped, `no-new-privileges`;
- memory, CPU, process and wall-clock limits on every run;
- no Docker socket, no host mounts, no API keys or tokens in the sandbox environment;
- the sandbox network has no route out; the only exit is an allowlisting egress gate that also refuses private, loopback, link-local and cloud-metadata addresses after DNS resolution, and logs every attempt.

## License

MIT
