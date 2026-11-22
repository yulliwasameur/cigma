# Private GitHub publication handoff

The verified target repository is the existing private repository:

```text
yulliwasameur/Introduction_a_la_cryptographie
```

GitHub metadata checked on 2026-08-26:

- visibility: `private`;
- default branch: `main`;
- authenticated account: `yulliwasameur`;
- permissions: admin and push;
- existing content: one placeholder `README.md`.

The connector available inside this ChatGPT runtime is read-only for repository
contents, so the final network push must run once in an authenticated local Git
session. `scripts/push_existing_private_repo.sh` performs that handoff without a
force push and verifies the target before changing it.

## One-command publication on the author's Mac

From the extracted clean-room repository:

```bash
chmod +x scripts/push_existing_private_repo.sh
scripts/push_existing_private_repo.sh
```

The script requires either:

- GitHub CLI (`gh`) authenticated as `yulliwasameur`; or
- normal Git HTTPS credentials already configured on the Mac.

It will:

1. verify that the exact target repository is private when `gh` is available;
2. clone its current `main` branch into a temporary directory;
3. preserve the remote history;
4. replace the placeholder tree with this verified clean-room tree;
5. commit as `Yulliwas Ameur <yulliwas.ameur@efrei.fr>`;
6. push `main` without force;
7. create and push tag `v0.1.0-clean-room`;
8. print the remote commit and visibility checks.

## Manual equivalent

```bash
gh auth login
gh repo clone yulliwasameur/Introduction_a_la_cryptographie /tmp/cigma-private
rsync -a --delete --exclude .git/ ./ /tmp/cigma-private/
cd /tmp/cigma-private
git config user.name 'Yulliwas Ameur'
git config user.email 'yulliwas.ameur@efrei.fr'
git add -A
git commit -m 'Add CIGMA clean-room reference implementation v0.1.0'
git push origin main
git tag -f -a v0.1.0-clean-room -m 'CIGMA clean-room reference implementation v0.1.0'
git push origin refs/tags/v0.1.0-clean-room --force-with-lease
```

The tag command uses `--force-with-lease` only for the tag, never for `main`, so
rerunning the handoff can update an earlier local release marker without
rewriting branch history.
