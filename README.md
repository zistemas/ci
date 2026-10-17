# zistemas/ci

Reusable GitHub Actions workflows para los repos de la org `zistemas`: librerías (`lib-*`) y aplicaciones (`app-*`). Para el CI de una aplicación alcanza `lib-ci` con `sbt-command: test`.

Existe porque los reusables de `BQN-UY/CI-CD` no son accesibles desde otra org
(ver [zistemas/convenciones#1](https://github.com/zistemas/convenciones/issues/1)).

**Escrito de cero.** No se copia contenido de `BQN-UY/CI-CD`: es un repo privado de BQN y
copiarlo cambiaría el titular. Tampoco se usan tokens de identidades de BQN (`SYSADMIN_PAT`);
alcanza con `GITHUB_TOKEN`.

## Workflows

| Workflow | Qué hace |
|---|---|
| [`lib-ci.yml`](.github/workflows/lib-ci.yml) | Ejecuta `sbt <sbt-command>` (default `unitTests`) con JDK `java-version` (default `21`) y los secrets `NEXUS_*` |
| [`lib-release.yml`](.github/workflows/lib-release.yml) | Si hubo cambios de código (`*.sbt`, `*.scala`, salvo `version.sbt`) desde el último tag `v*`, o con `force-release`: `sbt "release with-defaults"` desde `main` (lo que haga el `releaseProcess`) y GitHub release con `--generate-notes`. El caller debe dar `permissions: contents: write` |
| [`lib-release-hotfix.yml`](.github/workflows/lib-release-hotfix.yml) | Hotfix desde una rama de mantenimiento `release/*` (disparado a mano): exige `version.sbt` en `X.Y.Z-SNAPSHOT`, corre `sbt <sbt-command>` (default `release-hotfix`: tests, tag y Nexus según el `build.sbt`), pushea rama y tag, y crea el GitHub release con notas desde el tag anterior de la rama. Comparte el grupo de `concurrency` con `lib-release`. El caller debe dar `permissions: contents: write` |
| [`app-publish.yml`](.github/workflows/app-publish.yml) | Pre-release de una **aplicación** sbt: calcula la versión por rama y tags (`develop` → `v<NEXT>-snapshot.NNN`, con `NEXT` = último tag final + `.github/next-bump`; `release/vX.Y.Z…` y `hotfix/vX.Y.Z…` → `vX.Y.Z-rc.NNN`), corre `sbt 'set ThisBuild / version := …' <sbt-command>` (default `assembly`) y publica el JAR `*-<versión>.jar` como GitHub pre-release. Sin `version.sbt` que commitear. El caller debe dar `permissions: contents: write` |
| [`app-cleanup-snapshots.yml`](.github/workflows/app-cleanup-snapshots.yml) | Borra los pre-releases `vX.Y.Z-snapshot.NNN` viejos que deja `app-publish`, conservando los últimos `keep` (default 3) de cada versión objetivo; no toca finales ni RCs. Borra el release y su JAR, **no el tag**, para que un `NNN` nunca se reuse. `dry-run` sólo lista. El caller debe dar `permissions: contents: write` |
| [`app-start-release.yml`](.github/workflows/app-start-release.yml) | Abre `release/vX.Y.Z` desde el HEAD de `develop`. Por defecto, la versión que vienen mostrando los snapshots (último final + `.github/next-bump`); `version` la pisa, validando `X.Y.Z` y mayor que el último final. El push con `GITHUB_TOKEN` no dispara otros workflows: el primer `rc.NNN` sale con el primer push a la rama |
| [`app-make-release.yml`](.github/workflows/app-make-release.yml) | Cierra `release/vX.Y.Z` o `hotfix/vX.Y.Z[-desc]`, **todo o nada**: merge `--no-ff` a `main`, `sbt test`, tag `vX.Y.Z` en el merge y back-merge a `develop` en el runner, y `git push --atomic` de los tres refs. Después, JAR con la versión final, GitHub release y borrado de la rama. **Re-ejecutable**: si el tag ya está en `main`, sólo completa lo que falte. En `release/**` vuelve `next-bump` a `minor` en `develop` (en `hotfix/**` no). Conflicto en el back-merge → no pushea nada y explica cómo resolverlo |

## Uso

```yaml
jobs:
  ci:
    uses: zistemas/ci/.github/workflows/lib-ci.yml@v1
    secrets: inherit
```

Los callers referencian el tag `v1`. Un cambio en `main` no afecta a nadie hasta que se mueve el tag.

## Pruebas

`tests/release-cycle.py` corre los pasos de `app-start-release` y `app-make-release`, extraídos del YAML, contra un repo de prueba local (origin *bare*, `sbt` y `gh` de mentira): versión por defecto y forzada, merges, back-merge con conflicto, tests que fallan, push atómico rechazado, re-ejecución, hotfix y `next-bump`.

```bash
python3 -I tests/release-cycle.py .
```
