# The move under `llg179org`

> ⚠️ **AI-generated.** This page — and the code, device tree and tooling it
> describes — was written by Claude (Opus 5) working under the direction of
> Lajosházi, László Gergely, who reviewed every change and made or reviewed
> every measurement it rests on. Kernel commits carry `Co-authored-by: Claude`;
> anything prepared for the LKML carries `Assisted-by:` instead and never a
> `Signed-off-by` from the assistant, since only a human can certify the DCO.

Done on 2026-07-31. Kept as a record, because the next owner change - or the
next person reading a stale URL - needs the order and the one hazard, not a
reconstruction.

## The order that matters

Transfer first, rewrite second. Rewriting the URLs before the repositories exist
under the new owner breaks every one of them at once, including the kernel
package's source URL. Transferring first leaves **no broken window at all**:
GitHub redirects the old path, so both spellings work until the rewrite lands.

## What was actually affected

131 references across the two documented repositories, of which five do anything
at runtime:

| file | what it is | what breaks if wrong |
|---|---|---|
| `linux-fp3/APKBUILD` `source=` | the kernel source tarball | the package cannot build |
| `linux-fp3/APKBUILD` `url=` | package metadata | cosmetic |
| `tests/fp3-selftest` `_fork=` | the fork remote the coverage guard queries | one check reports a false failure |
| `userspace-audio/systemd/fp3-voiced.service` | `Documentation=` | cosmetic |
| `userspace-sensors/snsregd.service` | `Documentation=` | cosmetic |

Everything else is prose. Outside the repositories, and therefore easy to miss:
the `fork` remote of the kernel checkout (shared by its worktrees), the `origin`
remotes of the other two, and `~/.claude/CLAUDE.md`.

## The hazard, and what it measured

The kernel package fetches its source by commit, so the question is not whether
the redirect exists but whether it serves the same bytes:

```sh
C=$(grep '^_commit=' linux-fp3/APKBUILD | cut -d\" -f2)
curl -sL "https://github.com/<owner>/linux/archive/$C.tar.gz" | sha512sum
```

Measured across this move: the old path answers 301, the new one 302, and the
digest matched the APKBUILD `sha512sums` entry exactly. Nothing had to be
regenerated. Confirm it rather than assume it - the failure mode is a package
that built yesterday and does not today.

## ☠️ The rewrite rewrites this file too

The substitution that migrates the repositories also migrates **the document
describing the migration**, turning its example commands into no-ops and its
verification greps into nonsense. That happened here and had to be undone by
hand.

Two ways out, and the second is why this page now reads as history: either keep
the literal owner strings out of the substitution\'s reach, or write the page
after the fact so it has no commands left to corrupt. A page that instructs a
tree-wide edit is inside that tree.

For the same reason the pattern needs its trailing slash - matching `<old>/`
rather than `<old>` - or a second run turns the new owner into `<new>org`. The
version with the slash is idempotent; the version without it is not.

## What did not move

The kernel checkout\'s `origin` is upstream `msm8953-mainline/linux` and is never
pushed to. It was left pointing where it was.
