# zistemas/ci

Reusable GitHub Actions workflows para los repos de la org `zistemas`.

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

## Uso

```yaml
jobs:
  ci:
    uses: zistemas/ci/.github/workflows/lib-ci.yml@v1
    secrets: inherit
```

Los callers referencian el tag `v1`. Un cambio en `main` no afecta a nadie hasta que se mueve el tag.
