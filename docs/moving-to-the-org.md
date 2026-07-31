# Moving the repositories under `llg179org`

Three repositories move: `llg179/linux`, `llg179/fp3-pmaports` and
`llg179/Claude-skills-Fairphone3`. This is the order and the checks; the
rewrite itself is one script at the end.

## ☠️ Do the transfer first, rewrite second

Rewriting the URLs before the repositories exist under the organisation breaks
every one of them at once, including the kernel package's source URL. GitHub
sets up a redirect from the old path when a repository is transferred, so the
old URLs keep working *after* the move — which means there is no window where
anything is broken, as long as the order is that way round.

Transfer in the GitHub UI: **Settings → General → Danger Zone → Transfer
ownership**, target `llg179org`. Repeat for all three.

## What is actually affected

131 references across the two documented repositories, but only five of them do
anything at runtime. Those five are the ones to verify by hand:

| file | what it is | what breaks if wrong |
|---|---|---|
| `linux-fp3/APKBUILD` `source=` | the kernel source tarball | the package cannot build |
| `linux-fp3/APKBUILD` `url=` | package metadata | cosmetic |
| `tests/fp3-selftest` `_fork=` | the fork remote the coverage guard queries | one check reports a false failure |
| `userspace-audio/systemd/fp3-voiced.service` | `Documentation=` | cosmetic |
| `userspace-sensors/snsregd.service` | `Documentation=` | cosmetic |

Everything else is prose in READMEs and skills.

Not in any repository, so easy to forget:

- the `fork` remote of the local kernel checkout and of every worktree;
- the `origin` remote of the other two checkouts;
- `~/.claude/CLAUDE.md`, which names all three repositories.

## The one real hazard

The kernel package fetches a source tarball by commit:

```
https://github.com/llg179/linux/archive/$_commit.tar.gz
```

GitHub serves that only while the commit is reachable from some ref, and after a
transfer it serves it through a redirect. Two things to confirm rather than
assume, because the failure surfaces as a build that worked yesterday:

```sh
# the redirect works at all (302, not 404)
curl -sI -o /dev/null -w '%{http_code}\n' \
  "https://github.com/llg179/linux/archive/$_commit.tar.gz"

# and the new path serves the same bytes
curl -sL "https://github.com/llg179org/linux/archive/$_commit.tar.gz" | sha512sum
```

The second command's output must match the `sha512sums` line in the APKBUILD. If
it does, nothing needs regenerating; if it does not, the tarball is not
byte-identical and `pmbootstrap checksum` has to run again.

## The rewrite

After all three transfers are done:

```sh
for r in /mnt/1TB/pmos/linux-fp3 /mnt/1TB/pmos/fp3-pmaports \
         /home/fp3/git/Claude-skills-Fairphone3; do
	git -C "$r" grep -l 'llg179' | xargs -r sed -i 's|llg179/|llg179org/|g'
done

# remotes, including every worktree of the kernel checkout
git -C /mnt/1TB/pmos/linux-fp3 remote set-url fork \
	ssh://git@ssh.github.com:443/llg179org/linux.git
git -C /mnt/1TB/pmos/fp3-pmaports remote set-url origin \
	ssh://git@ssh.github.com:443/llg179org/fp3-pmaports.git
git -C /home/fp3/git/Claude-skills-Fairphone3 remote set-url origin \
	https://github.com/llg179org/Claude-skills-Fairphone3.git
```

☠️ `sed 's|llg179/|llg179org/|g'` is written with the trailing slash on purpose.
Without it, a second run rewrites `llg179org/` into `llg179orgorg/`, and the
pattern is idempotent only with the slash present.

The kernel checkout has worktrees; `git remote set-url` on the main checkout
covers them, since they share one config.

## Checks after the rewrite

```sh
# nothing still points at the old owner
git -C <repo> grep -c 'llg179/' ; # expect 0 in each

# the fork is reachable under the new name
git -C /mnt/1TB/pmos/linux-fp3 ls-remote fork | head -3

# the package still builds from the rewritten source URL
cd /mnt/1TB/pmos && ./pmb build --arch aarch64 --force --lax linux-fp3
```

The last one is the only check that proves it: the other two say the strings are
right, and only a build says the bytes arrive.

## What does not move

The kernel checkout's `origin` is upstream `msm8953-mainline/linux` and is never
pushed to. It is unaffected, and must stay pointing where it does.
