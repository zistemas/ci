"""Prueba app-start-release y app-make-release: corre sus pasos `run` (extraídos del YAML real) contra un
repo de prueba con origin bare, y sbt y gh de mentira. No usa red ni GitHub.

Uso: python3 -I tests/release-cycle.py .     (requiere git y python3-yaml)
"""
import os, subprocess, sys, tempfile, shutil, textwrap, yaml

CI = sys.argv[1]
WF = os.path.join(CI, ".github/workflows")


def pasos(nombre):
    d = yaml.safe_load(open(os.path.join(WF, nombre)))
    job = next(iter(d["jobs"].values()))
    return [s for s in job["steps"] if "run" in s]


def sh(cmd, cwd, env=None, check=True):
    r = subprocess.run(cmd, cwd=cwd, shell=True, env=env, capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f"{cmd}\n{r.stdout}\n{r.stderr}")
    return r


FAKE_SBT = """#!/usr/bin/env bash
# sbt de mentira: `test` respeta FAKE_TEST_EXIT; `set ThisBuild / version := "X" assembly` arma un JAR vacío.
case "$*" in
  *"version := "*) v=$(sed -E 's/.*version := "([^"]+)".*/\\1/' <<< "$*"); mkdir -p target/scala-2.13; : > "target/scala-2.13/app-$v.jar" ;;
  test*) exit "${FAKE_TEST_EXIT:-0}" ;;
esac
"""
FAKE_GH = """#!/usr/bin/env bash
# gh de mentira: releases como archivos en $GHSTATE; FAKE_GH_FAIL=1 hace fallar el create.
case "$1 $2" in
  "release view")   [ -f "$GHSTATE/$3" ] ;;
  "release create") [ "${FAKE_GH_FAIL:-0}" = 1 ] && exit 1; echo "$@" > "$GHSTATE/$3" ;;
  *) exit 2 ;;
esac
"""


class Repo:
    """origin bare + clon `work` (lo que haría el desarrollador) + un `runner` por corrida (lo que hace checkout)."""

    def __init__(self):
        self.base = tempfile.mkdtemp(prefix="ciclo-", dir=os.environ.get("TMPDIR"))
        self.origin = os.path.join(self.base, "origin.git")
        self.work = os.path.join(self.base, "work")
        self.bin = os.path.join(self.base, "bin")
        self.gh = os.path.join(self.base, "gh")
        os.makedirs(self.bin); os.makedirs(self.gh)
        for n, c in (("sbt", FAKE_SBT), ("gh", FAKE_GH)):
            p = os.path.join(self.bin, n); open(p, "w").write(c); os.chmod(p, 0o755)
        sh(f"git init -q --bare -b main {self.origin}", self.base)
        sh(f"git clone -q {self.origin} work", self.base)
        g = "git -c user.name=t -c user.email=t@t"
        self.g = g
        sh(f"mkdir -p .github && echo minor > .github/next-bump && echo base > a.txt && git add -A && {g} commit -qm base && git push -q origin main", self.work)
        sh(f"git checkout -qb develop && echo dev1 > b.txt && git add -A && {g} commit -qm dev1 && git push -q origin develop", self.work)

    def commit(self, rama, archivo, contenido, msg):
        sh(f"git fetch -q origin && git checkout -q -B {rama} origin/{rama} && echo '{contenido}' > {archivo} && git add -A && {self.g} commit -qm '{msg}' && git push -q origin {rama}", self.work)

    def refs(self):
        r = sh("git for-each-ref --format='%(refname) %(objectname:short)'", self.origin)
        return dict(l.split() for l in r.stdout.splitlines())

    def correr(self, workflow, rama, extra_env=None):
        """Simula checkout (fetch-depth 0) de `rama` y corre los pasos en orden, respetando `if` por resume."""
        runner = tempfile.mkdtemp(prefix="runner-", dir=self.base)
        sh(f"git clone -q {self.origin} . && git checkout -q {rama}", runner)
        out = os.path.join(runner, ".gh_output"); open(out, "w").close()
        summary = os.path.join(runner, ".summary"); open(summary, "w").close()
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", GHSTATE=self.gh, GITHUB_OUTPUT=out,
                   GITHUB_STEP_SUMMARY=summary, BRANCH=rama, **(extra_env or {}))
        outputs = {}
        for s in pasos(workflow):
            cond = s.get("if", "")
            if "resume == 'false'" in cond and outputs.get("resume") == "true":
                continue
            step_env = dict(env)
            for k, v in (s.get("env") or {}).items():
                for o in ("tag", "version", "kind"):
                    v = str(v).replace("${{ steps.version.outputs.%s }}" % o, outputs.get(o, ""))
                v = v.replace("${{ inputs.sbt-command }}", "assembly").replace("${{ inputs.version }}", (extra_env or {}).get("VERSION", ""))
                step_env[k] = v
            script = s["run"].replace("${{ inputs.sbt-test-command }}", "test")
            r = subprocess.run(["bash", "-c", script], cwd=runner, env=step_env, capture_output=True, text=True)
            for l in open(out).read().splitlines():
                k, _, v = l.partition("="); outputs[k] = v
            if r.returncode:
                return False, ((r.stdout + r.stderr).strip().splitlines() or [f"exit {r.returncode} en: {s.get('name')}"])[-1], outputs
        return True, open(summary).read().strip().replace("\n", " | "), outputs


def contenido(repo, ref, archivo):
    return sh(f"git show {ref}:{archivo}", repo.origin, check=False).stdout.strip()


fallas = 0
def caso(nombre, cond, detalle=""):
    global fallas
    print(("  ok   " if cond else "  FALLA ") + nombre + (f"  — {detalle}" if detalle and not cond else ""))
    fallas += not cond


print("start-release")
r = Repo()
ok, msg, o = r.correr("app-start-release.yml", "develop")
caso("sin tags y next-bump minor → release/v0.1.0", ok and "refs/heads/release/v0.1.0" in r.refs(), msg)
ok, msg, o = r.correr("app-start-release.yml", "develop")
caso("la rama ya existe → error", not ok and "ya existe la rama" in msg, msg)
ok, msg, o = r.correr("app-start-release.yml", "develop", {"VERSION": "0.3.0"})
caso("version=0.3.0 → release/v0.3.0", ok and "refs/heads/release/v0.3.0" in r.refs(), msg)
ok, msg, o = r.correr("app-start-release.yml", "develop", {"VERSION": "0.3"})
caso("version mal formada → error", not ok and "X.Y.Z" in msg, msg)

print("make-release: release/v0.3.0 con next-bump major en develop")
r.commit("develop", ".github/next-bump", "major", "breaking")
r.commit("release/v0.3.0", "a.txt", "fix-en-release", "fix")
antes = r.refs()
ok, msg, o = r.correr("app-make-release.yml", "release/v0.3.0")
refs = r.refs()
caso("termina bien", ok, msg)
caso("tag v0.3.0 en main", "refs/tags/v0.3.0" in refs and sh("git merge-base --is-ancestor v0.3.0 main", r.origin, check=False).returncode == 0)
caso("main tiene el fix del release", contenido(r, "main", "a.txt") == "fix-en-release")
caso("develop tiene el fix (back-merge)", contenido(r, "develop", "a.txt") == "fix-en-release")
caso("develop: next-bump vuelve a minor", contenido(r, "develop", ".github/next-bump") == "minor", contenido(r, "develop", ".github/next-bump"))
caso("release final creado", os.path.exists(os.path.join(r.gh, "v0.3.0")))
caso("JAR con la versión 0.3.0", "app-0.3.0.jar" in open(os.path.join(r.gh, "v0.3.0")).read())
caso("rama release/v0.3.0 borrada", "refs/heads/release/v0.3.0" not in refs)
caso("v0.3.0 ahora es el último final: start-release por defecto → 0.4.0",
     r.correr("app-start-release.yml", "develop")[0] and "refs/heads/release/v0.4.0" in r.refs())
ok, msg, o = r.correr("app-start-release.yml", "develop", {"VERSION": "0.2.9"})
caso("version menor que el último final → error", not ok and "no es mayor" in msg, msg)

print("make-release: conflicto en el back-merge")
r.commit("develop", "c.txt", "develop", "dev-c")
r.commit("release/v0.4.0", "c.txt", "release", "rel-c")
antes = r.refs()
ok, msg, o = r.correr("app-make-release.yml", "release/v0.4.0")
caso("falla con instrucciones", not ok and "back-merge" in msg, msg)
caso("no se pusheó nada (main, develop, tags iguales)", r.refs() == antes)

print("make-release: tests fallan")
ok, msg, o = r.correr("app-make-release.yml", "release/v0.4.0", {"FAKE_TEST_EXIT": "1"})
caso("falla y no pushea", not ok and r.refs() == antes)

print("make-release: re-ejecución tras fallar el release de GitHub")
r2 = Repo()
r2.correr("app-start-release.yml", "develop", {"VERSION": "0.3.0"})
ok, msg, o = r2.correr("app-make-release.yml", "release/v0.3.0", {"FAKE_GH_FAIL": "1"})
refs = r2.refs()
caso("primera corrida: refs pusheados, release no, rama sigue", not ok and "refs/tags/v0.3.0" in refs and "refs/heads/release/v0.3.0" in refs
     and not os.path.exists(os.path.join(r2.gh, "v0.3.0")), msg)
antes = r2.refs()
ok, msg, o = r2.correr("app-make-release.yml", "release/v0.3.0")
refs = r2.refs()
caso("segunda corrida: resume, crea el release y borra la rama", ok and o.get("resume") == "true"
     and os.path.exists(os.path.join(r2.gh, "v0.3.0")) and "refs/heads/release/v0.3.0" not in refs, msg)
caso("segunda corrida: main/develop/tag sin cambios",
     all(refs.get(k) == antes.get(k) for k in ("refs/heads/main", "refs/heads/develop", "refs/tags/v0.3.0")))

print("make-release: origin rechaza develop (push concurrente) → atómico")
r5 = Repo()
r5.correr("app-start-release.yml", "develop", {"VERSION": "0.3.0"})
hook = os.path.join(r5.origin, "hooks", "update")  # por ref: sin --atomic, main y el tag sí entrarían
open(hook, "w").write('#!/bin/sh\n[ "$1" = refs/heads/develop ] && { echo rechazado >&2; exit 1; }; exit 0\n')
os.chmod(hook, 0o755)
antes = r5.refs()
ok, msg, o = r5.correr("app-make-release.yml", "release/v0.3.0")
caso("falla y no actualiza ni main ni el tag", not ok and r5.refs() == antes, msg)
shutil.rmtree(r5.base)

print("make-release: hotfix no toca next-bump")
r3 = Repo()
r3.commit("develop", ".github/next-bump", "major", "breaking")
sh(f"git fetch -q origin && git checkout -q -B hotfix/v0.0.1-foto origin/main && echo hot > a.txt && git add -A && {r3.g} commit -qm hot && git push -q origin hotfix/v0.0.1-foto", r3.work)
ok, msg, o = r3.correr("app-make-release.yml", "hotfix/v0.0.1-foto")
caso("hotfix publicado como v0.0.1", ok and os.path.exists(os.path.join(r3.gh, "v0.0.1")), msg)
caso("develop tiene el hotfix", contenido(r3, "develop", "a.txt") == "hot")
caso("develop: next-bump sigue major", contenido(r3, "develop", ".github/next-bump") == "major")

print("make-release: tag existente fuera de main")
r4 = Repo()
r4.correr("app-start-release.yml", "develop", {"VERSION": "0.3.0"})
sh("git fetch -q origin && git tag v0.3.0 origin/release/v0.3.0 && git push -q origin v0.3.0", r4.work)
r4.commit("release/v0.3.0", "z.txt", "z", "z")
ok, msg, o = r4.correr("app-make-release.yml", "release/v0.3.0")
caso("error sin tocar nada", not ok and "no está en main" in msg, msg)

print("make-release: rama que no es de release")
ok, msg, o = r4.correr("app-make-release.yml", "develop")
caso("error", not ok and "make-release corre sobre" in msg, msg)

for x in (r, r2, r3, r4): shutil.rmtree(x.base)
print(f"\n{'TODO OK' if not fallas else f'{fallas} FALLAS'}")
sys.exit(1 if fallas else 0)
