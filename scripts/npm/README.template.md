# npm-offline-packages

Offline npm bundle produced by the **Npm Download** GitHub Actions workflow.

- `__TARBALL_COUNT__` package tarball(s) are bundled in this folder.
- `package.json` maps every dependency to a local tarball (`file:./xxx.tgz`), so `npm install --offline` never contacts a registry.
- `private` is set to `false`, so this folder can be published to a registry (for example a local Verdaccio) with `npm publish`.

## Packages

__PACKAGE_LIST__

## Offline install

Install from this folder:

```bash
cd packages
npm install --offline
```

Or install straight into your own project:

```bash
# bash / Git Bash
npm install ./packages/*.tgz --offline
```

On Windows PowerShell:

```powershell
npm install (Get-ChildItem ./packages/*.tgz).FullName --offline
```

## Publish to a local Verdaccio

```bash
cd packages
npm login --registry http://localhost:4873
npm publish --registry http://localhost:4873
```

Consumers then install from the internal registry:

```bash
npm config set registry http://<verdaccio-host>:4873
npm install npm-offline-packages
```

## Troubleshooting

> If you hit `npm error class extends value undefined is not a constructor or null`, that points to a broken or version-mismatched Node.js + npm installation on the offline machine (npm's own bundled modules fail to load), not to these packages — any npm command would fail the same way. Reinstall Node.js and clear stale global npm directories so `node -v` and `npm -v` are consistent.
