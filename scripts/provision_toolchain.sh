#!/usr/bin/env bash
# PROV phase 1: provision the to-GDS toolchain slice.
#
# Pins + version-asserts yosys/sby (via the pinned oss-cad-suite
# bundle), installs the LibreLane supported distribution per
# upstream docs, installs OpenSTA from source, and fails loud
# with doc-cited remedies where install is impossible. Offline
# runs degrade to version-asserted ambient + loud remedy, never
# fake-green: OK is printed only when all four tools assert.
#
# Upstream methods (standing rule: most-correct per tool docs):
# - oss-cad-suite pinned tarball:
#   https://github.com/YosysHQ/oss-cad-suite-build/releases
# - LibreLane AppImage (easiest) + Nix (primary) installs:
#   https://librelane.readthedocs.io/en/stable/installation/
#     appimage_installation/installation_linux.html
#   https://librelane.readthedocs.io/en/stable/installation/
#     nix_installation/installation_linux.html
#   (`librelane --smoke-test` is the upstream post-install check;
#   non-interactive smoke inside the AppImage is NOT asserted
#   here — upstream documents interactive entry. The DIGITAL-FLOW
#   lane owns the flow-level proof.)
# - OpenSTA CMake source build (README "Build from source"):
#   https://github.com/The-OpenROAD-Project/OpenSTA
#   (clone -> cmake -DCUDD_DIR=.. -> make -> install with
#   CMAKE_INSTALL_PREFIX into the app-owned tools dir.)
#
# GTKWave is EXCLUDED from engine provisioning by the headless
# rule (display-side, RocketIDE concern) — recorded, never
# installed.
#
# Usage:
#   scripts/provision_toolchain.sh --check-only  # assert only
#   scripts/provision_toolchain.sh --install     # install+assert
#   scripts/provision_toolchain.sh --only <tool> [--check-only|--install]
#     scope the assert/install to exactly one tool (backend for
#     the install-screen per-tool install; --only klayout
#     --install provisions exactly klayout)
#   scripts/provision_toolchain.sh --list-tools  # enumerate the
#     installable tools with their per-row prereqs (install menu)
#   scripts/provision_toolchain.sh --print-path  # idempotent shell
#     block exporting the provisioned bin dirs (backend for the
#     installer "add to PATH" flag; append once, guarded by the
#     markers — the provisioner itself never touches the shell).
#
# Machine-readable verdict (BUILD-LOCAL stage 3): every check
# run emits one `PROV-ROW` TSV line per tool — id, state
# (pinned|ambient|absent|mismatch|unpinned|unrunnable|unsourced),
# version, path, remedy — so ENGINE-SETUP can drive per-tool
# install/status without parsing prose.
#
# Honors:
#   TOOLS_DIR         app-owned tools dir (default: $ROOT/.tools;
#     BUILD-LOCAL stage 2 makes the repo the default so a fresh
#     clone writes nothing outside it. Explicit env still wins:
#     existing ~/tools users keep working via TOOLS_DIR=~/tools.)
#   OSS_CAD_SUITE_DIR bundle dir (default: $TOOLS_DIR/oss-cad-suite)
#   PROV_OFFLINE=1    skip every network attempt (fast air-gap path)
#
# Phase 2 (MVP remainder: magic, netgen, klayout, ngspice,
# xyce, xschem, cace) is wired below with per-tool pins,
# version asserts, pinned-or-ambient-recorded checks, and
# doc-cited installers. The MVP verdict (PROV-PHASE2) covers
# exactly these 7: deferred packs (pymeep, openems, elmer,
# devsim) report on their own PROV-DEFERRED line and never
# gate the MVP claim (see docs/tickets/PROV-DEFERRED.md).
# Palace stays UNSOURCED until its install docs are read
# (docs/provision-sources.md 12) — recorded, never installed.

set -u

# ---- pins (single source; tests parse these exact lines) ----
OSS_CAD_SUITE_PIN="20261025"
OSS_CAD_SUITE_TAG="2026-10-25"
YOSYS_EXPECT="Yosys 0.70"
SBY_EXPECT="SBY v0.70"
LIBRELANE_PIN="3.0.17"
LIBRELANE_COMMIT="64ef80802d3d189b476636d2a6b17888c03304ee"
OPENSTA_PIN="857316ff001b2a8dbbdc5996944d08a6d38c87ab"
CUDD_PIN="3.0.0"
# ---- phase-2 pins (B10 full matrix; resolved 2026-11-01) ----
MAGIC_REPO="https://github.com/RTimothyEdwards/magic"
MAGIC_REF="707d67e6c66e10fedf1efa7e2930017032ff6716"
MAGIC_EXPECT="8.3"
NETGEN_REPO="https://github.com/RTimothyEdwards/netgen"
NETGEN_REF="e310f3049e1f07c02d77aa509742ebc04b24f808"
NETGEN_EXPECT="Netgen 1.5"
KLAYOUT_PIN="0.30.12"
KLAYOUT_DEB="https://www.klayout.org/downloads/Ubuntu-24/klayout_0.30.12-1_amd64.deb"
KLAYOUT_EXPECT="KLayout 0.30.12"
NGSPICE_PIN="47"
NGSPICE_TGZ="https://sourceforge.net/projects/ngspice/files/ng-spice-rework/47/ngspice-47.tar.gz/download"
NGSPICE_EXPECT="ngspice-4"
XYCE_REF="Release-7.10.0"
XYCE_REPO="https://github.com/Xyce/Xyce"
TRILINOS_REF="trilinos-release-14-4-0"
TRILINOS_REPO="https://github.com/trilinos/Trilinos"
XYCE_EXPECT="Xyce"
XSCHEM_REPO="https://github.com/StefanSchippers/xschem"
XSCHEM_REF="7811010c934a93b14ed07cbf2afd217fb2058ee6"
XSCHEM_EXPECT="XSCHEM V3"
CACE_PIN="2.13.0"
PYMEEP_PIN="1.35.0"
MINIFORGE_URL="https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh"
OPENEMS_REF="v0.37.0"
OPENEMS_REPO="https://github.com/thliebig/openEMS"
CSXCAD_REF="v0.7.0"
CSXCAD_REPO="https://github.com/thliebig/CSXCAD"
OPENEMS_EXPECT="openEMS"
ELMER_PPA="ppa:elmer-csc-ubuntu/elmer-csc-ppa"
ELMER_EXPECT="ElmerSolver"
DEVSIM_PIN="2.11.2"
# PALACE: UNSOURCED (docs/provision-sources.md 12) — no pin until docs read.
# -------------------------------------------------------------

OSS_URL="https://github.com/YosysHQ/oss-cad-suite-build/releases"
LIBRELANE_URL="https://github.com/librelane/librelane/releases"
LIBRELANE_DOCS="https://librelane.readthedocs.io/en/stable/installation"
LIBRELANE_DOC_APPIMAGE="$LIBRELANE_DOCS/appimage_installation/installation_linux.html"
LIBRELANE_DOC_NIX="$LIBRELANE_DOCS/nix_installation/installation_linux.html"
OPENSTA_URL="https://github.com/The-OpenROAD-Project/OpenSTA"
OPENSTA_SHORT="$(printf '%s' "$OPENSTA_PIN" | cut -c1-7)"

list_tools() {
    # Install-menu enumeration: id + per-row prereqs shown BEFORE
    # the user ticks (the honest-checkbox rule). Palace is
    # deliberately absent: unsourced, no row action.
    cat <<'EOF'
oss-cad-suite: network + ~1GB disk; fetch pinned tarball.
librelane: network + ~2GB disk; fetch pinned AppImage.
opensta: network + build prereqs (git cmake make g++ swig bison flex tcl eigen) + ~30min build.
magic: network + build prereqs (git make gcc tclsh wish) + ~10min build.
netgen: network + build prereqs (git make gcc tclsh) + ~10min build.
klayout: network + dpkg-deb; host Qt runtime libs (banner check proves liveness, else apt remedy).
ngspice: network + build prereqs (make gcc bison flex) + ~15min build.
xyce: network + heavy build prereqs (cmake g++ gfortran ...) + Trilinos first: HOURS.
xschem: network + build prereqs (git make gcc tclsh wish) + ~10min build.
cace: uv + engine venv + network; pip into the venv.
pymeep: network + ~3GB disk; miniforge bootstrap once, then conda-forge env.
openems: network + build prereqs (cmake hdf5 boost fparser tinyxml) + CSXCAD first: LONG.
elmer: sudo + network (apt PPA). No-sudo hosts get the remedy, never a silent skip.
devsim: uv + engine venv + network; pip into the venv.
EOF
}

ONLY=""
if [ "${1:---install}" = "--list-tools" ]; then
    list_tools
    exit 0
elif [ "${1:---install}" = "--only" ]; then
    ONLY="${2:-}"
    case " oss-cad-suite librelane opensta magic netgen klayout ngspice xyce xschem cace pymeep openems elmer devsim " in
        *" $ONLY "*) ;;
        *)
            echo "unknown tool: '$ONLY' (run --list-tools)" >&2
            exit 2
            ;;
    esac
    MODE="${3:---check-only}"
    case "$MODE" in
        --check-only|--install) ;;
        *)
            echo "usage: provision_toolchain.sh --only <tool> [--check-only|--install]" >&2
            exit 2
            ;;
    esac
else
    MODE="${1:---install}"
    if [ "$MODE" != "--check-only" ] && [ "$MODE" != "--install" ] \
        && [ "$MODE" != "--print-path" ]; then
        echo "usage: provision_toolchain.sh [--check-only|--install|--print-path|--list-tools|--only <tool> ...]" >&2
        exit 2
    fi
fi

# Flair: colors on interactive terminals only. Piped output
# (tests, logs, machine readers) stays byte-identical plain.
# NO_COLOR=1 disables even on a tty.
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    C_OK=$'\033[32m'
    C_WARN=$'\033[33m'
    C_ERR=$'\033[31m'
    C_HEAD=$'\033[1;36m'
    C_DIM=$'\033[2m'
    C_OFF=$'\033[0m'
else
    C_OK=''
    C_WARN=''
    C_ERR=''
    C_HEAD=''
    C_DIM=''
    C_OFF=''
fi

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TOOLS_DIR="${TOOLS_DIR:-$ROOT_DIR/.tools}"
OSS_DIR="${OSS_CAD_SUITE_DIR:-$TOOLS_DIR/oss-cad-suite}"
LIBRELANE_DIR="$TOOLS_DIR/librelane-$LIBRELANE_PIN"
APPIMAGE="$LIBRELANE_DIR/librelane-devshell-x86_64.AppImage"
OPENSTA_PREFIX="$TOOLS_DIR/opensta-$OPENSTA_SHORT"
MAGIC_SHORT="$(printf '%s' "$MAGIC_REF" | cut -c1-7)"
NETGEN_SHORT="$(printf '%s' "$NETGEN_REF" | cut -c1-7)"
XSCHEM_SHORT="$(printf '%s' "$XSCHEM_REF" | cut -c1-7)"
MAGIC_PREFIX="$TOOLS_DIR/magic-$MAGIC_SHORT"
NETGEN_PREFIX="$TOOLS_DIR/netgen-$NETGEN_SHORT"
KLAYOUT_PREFIX="$TOOLS_DIR/klayout-$KLAYOUT_PIN"
NGSPICE_PREFIX="$TOOLS_DIR/ngspice-$NGSPICE_PIN"
XYCE_PREFIX="$TOOLS_DIR/xyce-7.10.0"
XSCHEM_PREFIX="$TOOLS_DIR/xschem-$XSCHEM_SHORT"
OPENEMS_PREFIX="$TOOLS_DIR/openems-0.37.0"
MINIFORGE="$TOOLS_DIR/miniforge3"
PYMEEP_PY="$MINIFORGE/envs/pymeep/bin/python"
OFFLINE="${PROV_OFFLINE:-0}"

# Dev-PATH inside the provisioner: the bundle and tools bins win
# over ambient, so checks never depend on the caller's PATH.
PATH="$OSS_DIR/bin:$TOOLS_DIR/bin:$PATH"
export PATH

OK_COUNT=0
MISSING=""
ATTEMPTED=0

note() {
    case "$1" in
        *MISMATCH*|*UNPINNED*|*UNRUNNABLE*|*absent*)
            printf '%s\n' "${C_WARN}$1${C_OFF}" ;;
        *']')
            printf '%s\n' "${C_OK}$1${C_OFF}" ;;
        *)
            printf '%s\n' "$1" ;;
    esac
}
remedy() {  # tool, cause, next-step, url
    printf '%s\n' "${C_ERR}REMEDY $1: $2. next: $3. see: $4${C_OFF}"
}
row() {  # id, state, version, path, remedy — one TSV verdict line
    local id="$1" state="$2" version="$3" path="$4" remedy_text="$5"
    version="$(printf '%s' "$version" | tr '\t\n' '  ' | cut -c1-100)"
    path="$(printf '%s' "$path" | tr '\t\n' '  ' | cut -c1-100)"
    remedy_text="$(printf '%s' "$remedy_text" | tr '\t\n' '  ' | cut -c1-200)"
    printf 'PROV-ROW\t%s\t%s\t%s\t%s\t%s\n' \
        "$id" "$state" "$version" "$path" "$remedy_text"
}
mark_ok() { OK_COUNT=$((OK_COUNT + 1)); }
mark_missing() { MISSING="$MISSING $1"; }

banner_of() {  # version-argv... -> first banner line or ""
    "$@" </dev/null 2>&1 | head -n 1 | cut -c1-100 || true
}

bundle_ok=""
check_bundle() {
    local ver_file="$OSS_DIR/VERSION"
    if [ ! -f "$ver_file" ]; then
        note "oss-cad-suite absent [$OSS_DIR]"
        row "oss-cad-suite" "absent" "-" "$OSS_DIR" \
            "run scripts/provision_toolchain.sh --install"
        bundle_ok="no"
        return 0
    fi
    local got
    got="$(head -n 1 "$ver_file" | tr -d '[:space:]')"
    if [ "$got" = "$OSS_CAD_SUITE_PIN" ]; then
        note "oss-cad-suite $got [$OSS_DIR]"
        row "oss-cad-suite" "pinned" "$got" "$OSS_DIR" "-"
        bundle_ok="yes"
    else
        note "oss-cad-suite MISMATCH got $got want $OSS_CAD_SUITE_PIN"
        row "oss-cad-suite" "mismatch" "$got" "$OSS_DIR" \
            "run scripts/provision_toolchain.sh --install"
        bundle_ok="no"
    fi
}

check_binary() {  # tool, expect-prefix, version-argv...
    local tool="$1" expect="$2"
    shift 2
    local bin
    bin="$(command -v "$tool" || true)"
    if [ -z "$bin" ]; then
        note "$tool absent"
        remedy "$tool" "$tool not on PATH (nor in $OSS_DIR/bin)" \
            "run scripts/provision_toolchain.sh --install" "$OSS_URL"
        row "$tool" "absent" "-" "$OSS_DIR/bin/$tool" \
            "run scripts/provision_toolchain.sh --install"
        mark_missing "$tool"
        return 0
    fi
    if [ "$bundle_ok" != "yes" ]; then
        note "$tool UNPINNED ($bin resolves outside bundle $OSS_CAD_SUITE_PIN)"
        remedy "$tool" "bundle $OSS_CAD_SUITE_PIN not asserted" \
            "run scripts/provision_toolchain.sh --install" "$OSS_URL"
        row "$tool" "unpinned" "-" "$bin" \
            "run scripts/provision_toolchain.sh --install"
        mark_missing "$tool"
        return 0
    fi
    local banner
    banner="$(banner_of "$@")"
    case "$banner" in
        "$expect"*)
            note "$tool $banner [$bin]"
            row "$tool" "pinned" "$banner" "$bin" "-"
            mark_ok
            ;;
        *)
            note "$tool MISMATCH got '$banner' want '$expect*'"
            remedy "$tool" "banner '$banner' != pin '$expect*'" \
                "run scripts/provision_toolchain.sh --install" "$OSS_URL"
            row "$tool" "mismatch" "$banner" "$bin" \
                "run scripts/provision_toolchain.sh --install"
            mark_missing "$tool"
            ;;
    esac
}

check_librelane() {
    if [ -x "$APPIMAGE" ] && [ -f "$LIBRELANE_DIR/LIBRELANE_PIN" ] \
        && [ -f "$LIBRELANE_DIR/tool_versions.txt" ] \
        && [ "$(head -n 1 "$LIBRELANE_DIR/LIBRELANE_PIN")" = "$LIBRELANE_PIN" ]
    then
        note "librelane $LIBRELANE_PIN [$APPIMAGE]"
        local bin
        bin="$(command -v librelane || true)"
        if [ -n "$bin" ]; then
            local ver
            ver="$(banner_of librelane --version)"
            case "$ver" in
                *"$LIBRELANE_PIN"*)
                    note "librelane PATH $ver [$bin]"
                    ;;
                *)
                    note "librelane PATH MISMATCH got '$ver'"
                    remedy "librelane" \
                        "PATH librelane '$ver' != pin $LIBRELANE_PIN" \
                        "align the nix-shell env with $LIBRELANE_PIN" \
                        "$LIBRELANE_URL"
                    row "librelane" "mismatch" "$ver" "$bin" \
                        "align the nix-shell env with $LIBRELANE_PIN"
                    mark_missing "librelane"
                    return 0
                    ;;
            esac
        fi
        row "librelane" "pinned" "$LIBRELANE_PIN" "$APPIMAGE" "-"
        mark_ok
        return 0
    fi
    note "librelane absent [$APPIMAGE]"
    remedy "librelane" "supported distribution $LIBRELANE_PIN absent" \
        "run scripts/provision_toolchain.sh --install" \
        "$LIBRELANE_DOC_APPIMAGE"
    row "librelane" "absent" "-" "$APPIMAGE" \
        "run scripts/provision_toolchain.sh --install"
    mark_missing "librelane"
}

check_opensta() {
    local sta="$OPENSTA_PREFIX/bin/sta"
    local pinfile="$OPENSTA_PREFIX/OPENSTA_PIN"
    if [ -x "$sta" ] && [ -f "$pinfile" ] \
        && [ "$(head -n 1 "$pinfile")" = "$OPENSTA_PIN" ]
    then
        local out
        out="$(banner_of "$sta" -version)"
        if [ -z "$out" ]; then
            out="$(banner_of "$sta" --version)"
        fi
        if [ -n "$out" ]; then
            note "opensta $OPENSTA_SHORT [$sta] $out"
            row "opensta" "pinned" "$out" "$sta" "-"
            mark_ok
            return 0
        fi
        note "opensta UNRUNNABLE ($sta prints no version)"
        remedy "opensta" "$sta prints no version" \
            "rebuild via scripts/provision_toolchain.sh --install" \
            "$OPENSTA_URL"
        row "opensta" "unrunnable" "-" "$sta" \
            "rebuild via scripts/provision_toolchain.sh --install"
        mark_missing "opensta"
        return 0
    fi
    local ambient
    ambient="$(command -v sta || true)"
    if [ -n "$ambient" ]; then
        note "opensta UNPINNED (ambient $ambient, no $pinfile)"
        remedy "opensta" "ambient sta is not the pinned build" \
            "run scripts/provision_toolchain.sh --install" "$OPENSTA_URL"
        row "opensta" "unpinned" "-" "$ambient" \
            "run scripts/provision_toolchain.sh --install"
    else
        note "opensta absent [$sta]"
        remedy "opensta" "pinned build $OPENSTA_SHORT absent" \
            "run scripts/provision_toolchain.sh --install" "$OPENSTA_URL"
        row "opensta" "absent" "-" "$sta" \
            "run scripts/provision_toolchain.sh --install"
    fi
    mark_missing "opensta"
}

OK2_COUNT=0
MISSING2=""
OKD_COUNT=0
MISSINGD=""

mark2_ok() { OK2_COUNT=$((OK2_COUNT + 1)); }
mark2_missing() { MISSING2="$MISSING2 $1"; }
markd_ok() { OKD_COUNT=$((OKD_COUNT + 1)); }
markd_missing() { MISSINGD="$MISSINGD $1"; }
mark_ok_for() {  # counter, id-unused — mvp vs deferred lane
    if [ "$1" = "deferred" ]; then markd_ok; else mark2_ok; fi
}
mark_missing_for() {  # counter, id
    if [ "$1" = "deferred" ]; then markd_missing "$2"; else mark2_missing "$2"; fi
}

# Phase-2 policy: provisioned (pinfile matches pin) -> OK pinned;
# else ambient banner in the EXPECT family -> OK ambient-recorded
# (version always printed, never assumed); else missing + remedy.
check_pinned_or_ambient() {  # id, prefix, pinfile-name, pin, expect, url, bin, counter, version-argv...
    local id="$1" prefix="$2" pinname="$3" pin="$4" expect="$5" url="$6"
    local bin="$7" counter="$8"
    shift 8
    local pinfile="$prefix/$pinname"
    local prov_bin="$prefix/bin/$bin"
    if [ -x "$prov_bin" ] && [ -f "$pinfile" ] \
        && [ "$(head -n 1 "$pinfile")" = "$pin" ]
    then
        local out
        out="$(banner_of "$prov_bin" "$@")"
        case "$out" in
            *"$expect"*)
                note "$id pinned $pin [$prov_bin] $out"
                row "$id" "pinned" "$out" "$prov_bin" "-"
                mark_ok_for "$counter"
                return 0
                ;;
        esac
        note "$id UNRUNNABLE ($prov_bin banner '$out' lacks '$expect')"
        remedy "$id" "provisioned build fails its banner" \
            "rebuild via scripts/provision_toolchain.sh --install" "$url"
        row "$id" "unrunnable" "$out" "$prov_bin" \
            "rebuild via scripts/provision_toolchain.sh --install"
        mark_missing_for "$counter" "$id"
        return 0
    fi
    local ambient
    ambient="$(command -v "$bin" || true)"
    if [ -z "$ambient" ]; then
        note "$id absent [$prov_bin]"
        remedy "$id" "no provisioned build, none ambient" \
            "run scripts/provision_toolchain.sh --install" "$url"
        row "$id" "absent" "-" "$prov_bin" \
            "run scripts/provision_toolchain.sh --install"
        mark_missing_for "$counter" "$id"
        return 0
    fi
    local out
    out="$(banner_of "$ambient" "$@")"
    case "$out" in
        *"$expect"*)
            note "$id ambient $out [$ambient]"
            row "$id" "ambient" "$out" "$ambient" "-"
            mark_ok_for "$counter"
            ;;
        *)
            note "$id MISMATCH got '$out' want '*$expect*'"
            remedy "$id" "ambient '$out' outside family '$expect'" \
                "run scripts/provision_toolchain.sh --install" "$url"
            row "$id" "mismatch" "$out" "$ambient" \
                "run scripts/provision_toolchain.sh --install"
            mark_missing_for "$counter" "$id"
            ;;
    esac
}

check_magic() {
    check_pinned_or_ambient magic "$MAGIC_PREFIX" MAGIC_REF \
        "$MAGIC_REF" "$MAGIC_EXPECT" "$MAGIC_REPO" magic mvp \
        -dnull -noconsole --version
}

check_netgen() {
    check_pinned_or_ambient netgen "$NETGEN_PREFIX" NETGEN_REF \
        "$NETGEN_REF" "$NETGEN_EXPECT" "$NETGEN_REPO" netgen mvp \
        -batch -h
}

check_klayout() {
    check_pinned_or_ambient klayout "$KLAYOUT_PREFIX" KLAYOUT_PIN \
        "$KLAYOUT_PIN" "$KLAYOUT_EXPECT" \
        "https://www.klayout.de/build.html" klayout mvp -v
}

check_ngspice() {
    # ngspice --version banners on a later line; grep the family.
    local prefix="$NGSPICE_PREFIX" pinfile="$NGSPICE_PREFIX/NGSPICE_PIN"
    local prov_bin="$prefix/bin/ngspice"
    if [ -x "$prov_bin" ] && [ -f "$pinfile" ] \
        && [ "$(head -n 1 "$pinfile")" = "$NGSPICE_PIN" ]
    then
        note "ngspice pinned $NGSPICE_PIN [$prov_bin]"
        row "ngspice" "pinned" "$NGSPICE_PIN" "$prov_bin" "-"
        mark2_ok
        return 0
    fi
    local ambient
    ambient="$(command -v ngspice || true)"
    if [ -z "$ambient" ]; then
        note "ngspice absent [$prov_bin]"
        remedy "ngspice" "no provisioned build, none ambient" \
            "run scripts/provision_toolchain.sh --install" \
            "https://ngspice.sourceforge.io/download.html"
        row "ngspice" "absent" "-" "$prov_bin" \
            "run scripts/provision_toolchain.sh --install"
        mark2_missing "ngspice"
        return 0
    fi
    local out
    out="$("$ambient" --version </dev/null 2>&1 | grep -m1 -o 'ngspice-[0-9]*' || true)"
    case "$out" in
        "$NGSPICE_EXPECT"*)
            note "ngspice ambient $out [$ambient]"
            row "ngspice" "ambient" "$out" "$ambient" "-"
            mark2_ok
            ;;
        *)
            note "ngspice MISMATCH got '$out' want '$NGSPICE_EXPECT*'"
            remedy "ngspice" "ambient '$out' outside family" \
                "run scripts/provision_toolchain.sh --install" \
                "https://ngspice.sourceforge.io/download.html"
            row "ngspice" "mismatch" "$out" "$ambient" \
                "run scripts/provision_toolchain.sh --install"
            mark2_missing "ngspice"
            ;;
    esac
}

check_xyce() {
    check_pinned_or_ambient xyce "$XYCE_PREFIX" XYCE_REF \
        "$XYCE_REF" "$XYCE_EXPECT" "$XYCE_REPO" Xyce mvp -version
}

check_xschem() {
    # xschem -v buries the version after X-notice lines; grep it.
    local pinfile="$XSCHEM_PREFIX/XSCHEM_REF"
    local prov_bin="$XSCHEM_PREFIX/bin/xschem"
    local bin="$prov_bin" pinned="no"
    if [ -x "$prov_bin" ] && [ -f "$pinfile" ] \
        && [ "$(head -n 1 "$pinfile")" = "$XSCHEM_REF" ]
    then
        pinned="yes"
    else
        bin="$(command -v xschem || true)"
    fi
    if [ -z "$bin" ]; then
        note "xschem absent [$prov_bin]"
        remedy "xschem" "no provisioned build, none ambient" \
            "run scripts/provision_toolchain.sh --install" "$XSCHEM_REPO"
        row "xschem" "absent" "-" "$prov_bin" \
            "run scripts/provision_toolchain.sh --install"
        mark2_missing "xschem"
        return 0
    fi
    local out
    out="$("$bin" -v </dev/null 2>&1 | grep -m1 -o 'XSCHEM V[0-9]*' || true)"
    case "$out" in
        "$XSCHEM_EXPECT"*)
            if [ "$pinned" = "yes" ]; then
                note "xschem pinned $XSCHEM_REF [$bin] $out"
                row "xschem" "pinned" "$out" "$bin" "-"
            else
                note "xschem ambient $out [$bin]"
                row "xschem" "ambient" "$out" "$bin" "-"
            fi
            mark2_ok
            ;;
        *)
            note "xschem MISMATCH got '$out' want '$XSCHEM_EXPECT*'"
            remedy "xschem" "banner outside family" \
                "run scripts/provision_toolchain.sh --install" "$XSCHEM_REPO"
            row "xschem" "mismatch" "$out" "$bin" \
                "run scripts/provision_toolchain.sh --install"
            mark2_missing "xschem"
            ;;
    esac
}

check_pypkg() {  # id, pin, url, counter — importable in the engine venv
    local id="$1" pin="$2" url="$3" counter="$4"
    local py="${PROV_PYTHON:-$ROOT_DIR/.venv/bin/python}"
    [ -x "$py" ] || py="python3"
    local got
    got="$("$py" -c "import importlib.metadata as m; print(m.version('$id'))" 2>/dev/null || true)"
    if [ "$got" = "$pin" ]; then
        note "$id pinned $pin [engine venv]"
        row "$id" "pinned" "$pin" "$py" "-"
        mark_ok_for "$counter"
    elif [ -n "$got" ]; then
        note "$id MISMATCH got '$got' want '$pin'"
        remedy "$id" "venv has $got, pin is $pin" \
            "run scripts/provision_toolchain.sh --install" "$url"
        row "$id" "mismatch" "$got" "$py" \
            "run scripts/provision_toolchain.sh --install"
        mark_missing_for "$counter" "$id"
    else
        note "$id absent [engine venv]"
        remedy "$id" "$id==$pin not installed" \
            "run scripts/provision_toolchain.sh --install" "$url"
        row "$id" "absent" "-" "$py" \
            "run scripts/provision_toolchain.sh --install"
        mark_missing_for "$counter" "$id"
    fi
}

check_cace() { check_pypkg cace "$CACE_PIN" "https://github.com/efabless/cace" mvp; }
check_devsim() { check_pypkg devsim "$DEVSIM_PIN" "https://pypi.org/project/devsim/" deferred; }

check_pymeep() {
    if [ -x "$PYMEEP_PY" ]; then
        local got
        # import meep chatters after the version line
        # ("Elapsed run time = ..."): first line only.
        got="$("$PYMEEP_PY" -c "import meep; print(meep.__version__)" 2>/dev/null | head -n 1 || true)"
        if [ "$got" = "$PYMEEP_PIN" ]; then
            note "pymeep pinned $got [$PYMEEP_PY]"
            row "pymeep" "pinned" "$got" "$PYMEEP_PY" "-"
            markd_ok
            return 0
        fi
        note "pymeep MISMATCH got '$got' want '$PYMEEP_PIN'"
        remedy "pymeep" "conda env version drift" \
            "run scripts/provision_toolchain.sh --install" \
            "https://meep.readthedocs.io/en/latest/Installation/"
        row "pymeep" "mismatch" "$got" "$PYMEEP_PY" \
            "run scripts/provision_toolchain.sh --install"
        markd_missing "pymeep"
        return 0
    fi
    note "pymeep absent [$PYMEEP_PY]"
    remedy "pymeep" "conda-forge pymeep==$PYMEEP_PIN not installed" \
        "run scripts/provision_toolchain.sh --install" \
        "https://meep.readthedocs.io/en/latest/Installation/"
    row "pymeep" "absent" "-" "$PYMEEP_PY" \
        "run scripts/provision_toolchain.sh --install"
    markd_missing "pymeep"
}

check_openems() {
    check_pinned_or_ambient openems "$OPENEMS_PREFIX" OPENEMS_REF \
        "$OPENEMS_REF" "$OPENEMS_EXPECT" "$OPENEMS_REPO" openEMS deferred --version
}

check_elmer() {
    local bin
    bin="$(command -v ElmerSolver || true)"
    if [ -z "$bin" ]; then
        note "elmer absent [ElmerSolver]"
        remedy "elmer" "ElmerSolver not installed" \
            "run scripts/provision_toolchain.sh --install (needs sudo for $ELMER_PPA)" \
            "https://www.csc.fi/web/elmer"
        row "elmer" "absent" "-" "ElmerSolver" \
            "run scripts/provision_toolchain.sh --install (needs sudo)"
        markd_missing "elmer"
        return 0
    fi
    local out
    out="$(banner_of "$bin" --version)"
    case "$out" in
        *"$ELMER_EXPECT"*|*[Ee]lmer*|*ELMER*)
            note "elmer ambient $out [$bin]"
            row "elmer" "ambient" "$out" "$bin" "-"
            markd_ok
            ;;
        *)
            note "elmer MISMATCH got '$out'"
            remedy "elmer" "banner unrecognized" \
                "run scripts/provision_toolchain.sh --install" \
                "https://www.csc.fi/web/elmer"
            row "elmer" "mismatch" "$out" "$bin" \
                "run scripts/provision_toolchain.sh --install"
            markd_missing "elmer"
            ;;
    esac
}

check_palace() {
    note "palace UNSOURCED (docs/provision-sources.md 12) — no pin until install docs are read"
    row "palace" "unsourced" "-" "-" \
        "read awslabs palace install docs into docs/provision-sources.md section 12 first"
}

run_checks() {
    OK_COUNT=0
    MISSING=""
    check_bundle
    check_binary yosys "$YOSYS_EXPECT" yosys -V
    check_binary sby "$SBY_EXPECT" sby --version
    check_librelane
    check_opensta
    note "note: GTKWave excluded from engine provisioning by the headless rule"
    OK2_COUNT=0
    MISSING2=""
    check_magic
    check_netgen
    check_klayout
    check_ngspice
    check_xyce
    check_xschem
    check_cace
    OKD_COUNT=0
    MISSINGD=""
    check_pymeep
    check_openems
    check_elmer
    check_devsim
    check_palace
}

verdict() {
    if [ "$OK_COUNT" -eq 4 ]; then
        printf '%s\n' "${C_OK}PROV-PHASE1: OK (4/4 version-asserted)${C_OFF}"
    else
        printf '%s\n' "${C_ERR}PROV-PHASE1: DEGRADED (missing:$MISSING)${C_OFF}"
    fi
    if [ "$OK2_COUNT" -eq 7 ]; then
        printf '%s\n' "${C_OK}PROV-PHASE2: OK (7/7 MVP provisioned-or-ambient-recorded)${C_OFF}"
    else
        printf '%s\n' "${C_ERR}PROV-PHASE2: DEGRADED (MVP missing:$MISSING2)${C_OFF}"
    fi
    if [ "$OKD_COUNT" -eq 4 ]; then
        printf '%s\n' "${C_OK}PROV-DEFERRED: OK (4/4 deferred provisioned-or-ambient-recorded)${C_OFF}"
    else
        printf '%s\n' "${C_ERR}PROV-DEFERRED: DEGRADED (deferred missing:$MISSINGD — never gates the MVP claim)${C_OFF}"
    fi
    if [ "$OK_COUNT" -eq 4 ] && [ "$OK2_COUNT" -eq 7 ]; then
        return 0
    fi
    return 1
}

run_only_checks() {  # id — scoped assert for --only (BUILD-LOCAL stage 3)
    OK_COUNT=0
    MISSING=""
    OK2_COUNT=0
    MISSING2=""
    OKD_COUNT=0
    MISSINGD=""
    case "$1" in
        oss-cad-suite)
            check_bundle
            check_binary yosys "$YOSYS_EXPECT" yosys -V
            check_binary sby "$SBY_EXPECT" sby --version
            ;;
        librelane) check_librelane ;;
        opensta) check_opensta ;;
        magic) check_magic ;;
        netgen) check_netgen ;;
        klayout) check_klayout ;;
        ngspice) check_ngspice ;;
        xyce) check_xyce ;;
        xschem) check_xschem ;;
        cace) check_cace ;;
        pymeep) check_pymeep ;;
        openems) check_openems ;;
        elmer) check_elmer ;;
        devsim) check_devsim ;;
    esac
}

install_one() {  # id — scoped install for --only (BUILD-LOCAL stage 3)
    case "$1" in
        oss-cad-suite) install_bundle ;;
        librelane) install_librelane ;;
        opensta) install_opensta ;;
        magic) install_magic ;;
        netgen) install_netgen ;;
        klayout) install_klayout ;;
        ngspice) install_ngspice ;;
        xyce) install_xyce ;;
        xschem) install_xschem ;;
        cace) install_cace ;;
        pymeep) install_pymeep ;;
        openems) install_openems ;;
        elmer) install_elmer ;;
        devsim) install_devsim ;;
    esac
}

scoped_verdict() {  # id — scoped verdict for --only (BUILD-LOCAL stage 3)
    if [ -z "$MISSING" ] && [ -z "$MISSING2" ] && [ -z "$MISSINGD" ]; then
        printf '%s\n' "${C_OK}PROV-ONLY $1: OK${C_OFF}"
        return 0
    fi
    printf '%s\n' "${C_ERR}PROV-ONLY $1: DEGRADED (missing:$MISSING$MISSING2$MISSINGD)${C_OFF}"
    return 1
}

offline_stop() {  # tool
    note "install $1: skipped (offline: PROV_OFFLINE=$OFFLINE or unreachable)."
}

fetch() {  # url, dest — retry + resume where upstream supports it
    curl -fSL --retry 3 --retry-all-errors --retry-delay 5 \
        --connect-timeout 15 --max-time 600 -C - -o "$2" "$1"
}

install_bundle() {
    if [ "$OFFLINE" = "1" ]; then
        offline_stop "oss-cad-suite"
        return 1
    fi
    if [ -d "$OSS_DIR" ]; then
        remedy "oss-cad-suite" "$OSS_DIR exists but is not pin $OSS_CAD_SUITE_PIN" \
            "back it up, remove it, then retry --install" "$OSS_URL"
        return 1
    fi
    ATTEMPTED=1
    local tgz="oss-cad-suite-linux-x64-$OSS_CAD_SUITE_PIN.tgz"
    local url="$OSS_URL/download/$OSS_CAD_SUITE_TAG/$tgz"
    mkdir -p "$TOOLS_DIR" || return 1
    note "install oss-cad-suite: fetching $url"
    fetch "$url" "$TOOLS_DIR/$tgz" || {
        remedy "oss-cad-suite" "download failed (offline?)" \
            "retry with network, then re-run --install" "$OSS_URL"
        return 1
    }
    tar -xzf "$TOOLS_DIR/$tgz" -C "$TOOLS_DIR" || {
        remedy "oss-cad-suite" "extract failed" \
            "remove $TOOLS_DIR/$tgz and retry --install" "$OSS_URL"
        return 1
    }
    return 0
}

install_librelane() {
    if [ "$OFFLINE" = "1" ]; then
        offline_stop "librelane"
        return 1
    fi
    ATTEMPTED=1
    mkdir -p "$LIBRELANE_DIR" || return 1
    local base="$LIBRELANE_URL/download/$LIBRELANE_PIN"
    note "install librelane: fetching AppImage $LIBRELANE_PIN"
    fetch "$base/librelane-devshell-x86_64.AppImage" "$APPIMAGE" || {
        remedy "librelane" "AppImage download failed (offline?)" \
            "retry with network, then re-run --install" \
            "$LIBRELANE_DOC_APPIMAGE"
        note "note: alternate supported install is Nix (needs sudo + network)"
        note "note: $LIBRELANE_DOC_NIX"
        return 1
    }
    fetch "$base/tool_versions.txt" "$LIBRELANE_DIR/tool_versions.txt" || {
        remedy "librelane" "tool_versions.txt download failed" \
            "retry with network, then re-run --install" \
            "$LIBRELANE_DOC_APPIMAGE"
        return 1
    }
    chmod a+x "$APPIMAGE"
    printf '%s\n' "$LIBRELANE_PIN" >"$LIBRELANE_DIR/LIBRELANE_PIN"
    note "install librelane: enter with $APPIMAGE then run librelane --smoke-test"
    return 0
}

clone_retry() {  # url, dest, commit — 3 attempts for flaky network
    local attempt=0
    while [ "$attempt" -lt 3 ]; do
        if timeout 600 git clone "$1" "$2" 2>/dev/null; then
            (cd "$2" && (git checkout "$3" 2>/dev/null \
                || (git fetch origin "$3" 2>/dev/null \
                    && git checkout "$3" 2>/dev/null))) && return 0
            return 1
        fi
        attempt=$((attempt + 1))
        sleep 5
    done
    return 1
}

install_opensta() {
    if [ "$OFFLINE" = "1" ]; then
        offline_stop "opensta"
        return 1
    fi
    local missing_prereq=""
    for tool in git cmake make g++ swig bison flex tclsh \
        autoconf automake libtool; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            missing_prereq="$missing_prereq $tool"
        fi
    done
    if [ -n "$missing_prereq" ]; then
        # apt splits the pair: the libtool .deb ships
        # libtoolize, /usr/bin/libtool lives in libtool-bin, so
        # the remedy must name both (bare "install libtool"
        # leaves `command -v libtool` failing on --no-recommends
        # hosts, exactly tonight's failure). Likewise the tclsh
        # binary ships in the tcl package, so map it back.
        local apt_missing
        apt_missing=$(printf '%s' "$missing_prereq" \
            | sed -e 's/\blibtool\b/libtool libtool-bin/' \
                -e 's/\btclsh\b/tcl/') || return 1
        remedy "opensta" "build prerequisites missing:$missing_prereq" \
            "sudo apt-get install -y$apt_missing tcl-dev libeigen3-dev" \
            "$OPENSTA_URL"
        return 1
    fi
    ATTEMPTED=1
    local src="$TOOLS_DIR/src/opensta-$OPENSTA_SHORT"
    mkdir -p "$TOOLS_DIR/src" "$OPENSTA_PREFIX" || return 1
    if [ ! -d "$src" ]; then
        note "install opensta: cloning $OPENSTA_PIN"
        clone_retry "$OPENSTA_URL.git" "$src" "$OPENSTA_PIN" || {
            remedy "opensta" "git clone/checkout failed (offline?)" \
                "retry with network, then re-run --install" "$OPENSTA_URL"
            return 1
        }
    fi
    if [ ! -d "$src/cudd" ]; then
        note "install opensta: cloning CUDD $CUDD_PIN"
        clone_retry "https://github.com/cuddorg/cudd.git" "$src/cudd" \
            "$CUDD_PIN" || {
            remedy "opensta" "CUDD clone failed (offline?)" \
                "retry with network, then re-run --install" "$OPENSTA_URL"
            return 1
        }
    fi
    # Gate on the installed lib, not the source dir: a failed
    # build leaves $src/cudd behind, and skipping it poisons the
    # cmake step with a missing CUDD library on the rerun.
    if [ ! -f "$src/cudd-install/lib/libcudd.a" ] \
        && [ ! -f "$src/cudd-install/lib/libcudd.so" ]; then
        note "install opensta: building CUDD"
        # Git clones ship 1.14-era autotools output; regenerate
        # with the host toolchain first (cuddorg/cudd README),
        # else make chases a missing aclocal-1.14.
        (cd "$src/cudd" && autoreconf -fi \
            && ./configure --prefix="$src/cudd-install" \
            && make -j"$(nproc)" && make install) || {
            remedy "opensta" "CUDD build failed" \
                "see $OPENSTA_URL README prerequisites" "$OPENSTA_URL"
            return 1
        }
    fi
    # A stale dir from a failed cmake configure has no Makefile;
    # clear it so retries reconfigure clean (same rule as xyce).
    if [ ! -f "$src/build/Makefile" ]; then
        rm -rf "$src/build"
    fi
    note "install opensta: cmake build"
    (mkdir -p "$src/build" && cd "$src/build" \
        && cmake -DCUDD_DIR="$src/cudd-install" \
            -DCMAKE_INSTALL_PREFIX="$OPENSTA_PREFIX" .. \
        && make -j"$(nproc)" && make install) || {
        remedy "opensta" "cmake build failed" \
            "see $OPENSTA_URL README prerequisites" "$OPENSTA_URL"
        return 1
    }
    printf '%s\n' "$OPENSTA_PIN" >"$OPENSTA_PREFIX/OPENSTA_PIN"
    return 0
}

prereqs_or_remedy() {  # id, url, tools...
    local id="$1" url="$2"
    shift 2
    local missing_prereq=""
    for tool in "$@"; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            missing_prereq="$missing_prereq $tool"
        fi
    done
    if [ -n "$missing_prereq" ]; then
        remedy "$id" "build prerequisites missing:$missing_prereq" \
            "install them (see $url prerequisites), then re-run --install" \
            "$url"
        return 1
    fi
    return 0
}

autotools_git_install() {  # id, repo, ref, prefix, pinname, configure-args...
    local id="$1" repo="$2" ref="$3" prefix="$4" pinname="$5"
    shift 5
    local src="$TOOLS_DIR/src/$id-$ref"
    mkdir -p "$TOOLS_DIR/src" "$prefix" || return 1
    if [ ! -d "$src" ]; then
        note "install $id: cloning $ref"
        clone_retry "$repo" "$src" "$ref" || {
            remedy "$id" "git clone/checkout failed (offline?)" \
                "retry with network, then re-run --install" "$repo"
            return 1
        }
    fi
    note "install $id: configure + make"
    (cd "$src" && ./configure --prefix="$prefix" "$@" \
        && make -j"$(nproc)" && make install) || {
        remedy "$id" "configure/make/install failed" \
            "see the tool README prerequisites, then re-run --install" "$repo"
        return 1
    }
    printf '%s\n' "$ref" >"$prefix/$pinname"
    return 0
}

install_magic() {
    if [ "$OFFLINE" = "1" ]; then offline_stop "magic"; return 1; fi
    prereqs_or_remedy "magic" "$MAGIC_REPO" git make gcc tclsh wish || return 1
    ATTEMPTED=1
    autotools_git_install magic "$MAGIC_REPO" "$MAGIC_REF" \
        "$MAGIC_PREFIX" MAGIC_REF --enable-cairo-offscreen
}

install_netgen() {
    if [ "$OFFLINE" = "1" ]; then offline_stop "netgen"; return 1; fi
    prereqs_or_remedy "netgen" "$NETGEN_REPO" git make gcc tclsh || return 1
    ATTEMPTED=1
    autotools_git_install netgen "$NETGEN_REPO" "$NETGEN_REF" \
        "$NETGEN_PREFIX" NETGEN_REF
}

install_klayout() {
    if [ "$OFFLINE" = "1" ]; then offline_stop "klayout"; return 1; fi
    prereqs_or_remedy "klayout" "https://www.klayout.de/build.html" \
        dpkg-deb || return 1
    ATTEMPTED=1
    mkdir -p "$KLAYOUT_PREFIX" || return 1
    local deb="$TOOLS_DIR/klayout-$KLAYOUT_PIN-amd64.deb"
    if [ -s "$deb" ]; then
        note "install klayout: reusing $deb"
    else
        note "install klayout: fetching $KLAYOUT_DEB"
        fetch "$KLAYOUT_DEB" "$deb" || {
            remedy "klayout" "deb download failed (offline?)" \
                "retry with network, then re-run --install" \
                "https://www.klayout.de/build.html"
            return 1
        }
    fi
    dpkg-deb -x "$deb" "$KLAYOUT_PREFIX" || {
        remedy "klayout" "deb extract failed" \
            "remove $deb and retry --install" \
            "https://www.klayout.de/build.html"
        return 1
    }
    # .debs extract under usr/, but checks + prov-phase1.env +
    # engine setup all resolve prefix/bin: merge usr/* up one
    # level (bin/../share relative layout preserved).
    if [ -d "$KLAYOUT_PREFIX/usr" ]; then
        (cd "$KLAYOUT_PREFIX/usr" && cp -a . "$KLAYOUT_PREFIX/") \
            && rm -rf "$KLAYOUT_PREFIX/usr" || {
            remedy "klayout" "usr-prefix normalization failed" \
                "remove $KLAYOUT_PREFIX and retry --install" \
                "https://www.klayout.de/build.html"
            return 1
        }
    fi
    # .deb binaries resolve their libs via system library paths,
    # which our prefix is not on. Wrap bin/klayout so the loader
    # reaches prefix/lib/klayout (idempotent: re-extract always
    # restores a fresh ELF here, so move-then-write is safe).
    # strm* companions share the layout but the engine only
    # shells klayout itself; they stay unwrapped.
    if [ -f "$KLAYOUT_PREFIX/bin/klayout" ]; then
        mv -f "$KLAYOUT_PREFIX/bin/klayout" \
            "$KLAYOUT_PREFIX/bin/klayout.bin" || {
            remedy "klayout" "binary wrap failed" \
                "remove $KLAYOUT_PREFIX and retry --install" \
                "https://www.klayout.de/build.html"
            return 1
        }
        cat >"$KLAYOUT_PREFIX/bin/klayout" <<EOF
#!/bin/sh
# generated by provision_toolchain.sh --install; do not edit.
HERE="\$(dirname "\$0")"
LD_LIBRARY_PATH="$KLAYOUT_PREFIX/lib/klayout\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
export LD_LIBRARY_PATH
exec "\$HERE/klayout.bin" "\$@"
EOF
        chmod +x "$KLAYOUT_PREFIX/bin/klayout" || return 1
    fi
    # .deb extraction needs no root but also resolves no deps: the
    # banner check after install proves liveness; a dead binary
    # remedies toward sudo apt install ./deb instead.
    printf '%s\n' "$KLAYOUT_PIN" >"$KLAYOUT_PREFIX/KLAYOUT_PIN"
    note "install klayout: extracted to $KLAYOUT_PREFIX (deps: host Qt/runtime libs)"
    return 0
}

install_ngspice() {
    if [ "$OFFLINE" = "1" ]; then offline_stop "ngspice"; return 1; fi
    prereqs_or_remedy "ngspice" \
        "https://ngspice.sourceforge.io/download.html" \
        make gcc bison flex || return 1
    ATTEMPTED=1
    local tgz="$TOOLS_DIR/ngspice-$NGSPICE_PIN.tar.gz"
    note "install ngspice: fetching rework $NGSPICE_PIN"
    fetch "$NGSPICE_TGZ" "$tgz" || {
        remedy "ngspice" "tarball download failed (offline?)" \
            "retry with network, then re-run --install" \
            "https://ngspice.sourceforge.io/download.html"
        return 1
    }
    mkdir -p "$TOOLS_DIR/src" "$NGSPICE_PREFIX" || return 1
    tar -xzf "$tgz" -C "$TOOLS_DIR/src" || {
        remedy "ngspice" "extract failed" \
            "remove $tgz and retry --install" \
            "https://ngspice.sourceforge.io/download.html"
        return 1
    }
    (cd "$TOOLS_DIR/src/ngspice-$NGSPICE_PIN" \
        && ./configure --prefix="$NGSPICE_PREFIX" \
        && make -j"$(nproc)" && make install) || {
        remedy "ngspice" "configure/make/install failed" \
            "see the ngspice manual ch. 32 prerequisites" \
            "https://ngspice.sourceforge.io/download.html"
        return 1
    }
    printf '%s\n' "$NGSPICE_PIN" >"$NGSPICE_PREFIX/NGSPICE_PIN"
    return 0
}

install_xyce() {
    if [ "$OFFLINE" = "1" ]; then offline_stop "xyce"; return 1; fi
    prereqs_or_remedy "xyce" "https://xyce.sandia.gov/" \
        git cmake make gcc g++ gfortran bison flex \
        autoconf automake libtool || return 1
    # SuiteSparse dev files: Xyce defaults AMD on (KLU support) and
    # TriBITS only builds EpetraExt_AMD when it finds the AMD TPL at
    # Trilinos configure time. Runtime libs alone (libamd.so.3)
    # fail AC_CHECK_LIB; without the headers the later
    # EpetraExt_AMD_CrsGraph.h check fails too. Check both the
    # header and the linker symlink before the long builds start.
    if [ ! -f /usr/include/suitesparse/amd.h ] \
        || [ ! -f /usr/lib/x86_64-linux-gnu/libamd.so ]; then
        remedy "xyce" "SuiteSparse dev files absent (need amd.h + libamd.so)" \
            "sudo apt-get install -y libsuitesparse-dev, then re-run --install" \
            "https://xyce.sandia.gov/"
        return 1
    fi
    # TriBITS' FindTPLAMD does not search Debian's
    # /usr/include/suitesparse subdir, so pass the distro
    # locations explicitly (TriBITS' own documented escape:
    # "-DTPL_<name>_LIBRARIES=..."). Same paths the gate
    # above just verified; Ubuntu 24.04 layout.
    AMD_INC="/usr/include/suitesparse"
    AMD_LIB="/usr/lib/x86_64-linux-gnu"
    ATTEMPTED=1
    local tsrc="$TOOLS_DIR/src/trilinos-$TRILINOS_REF"
    local tpref="$TOOLS_DIR/trilinos-$TRILINOS_REF"
    mkdir -p "$TOOLS_DIR/src" "$tpref" "$XYCE_PREFIX" || return 1
    if [ ! -d "$tsrc" ]; then
        note "install xyce: cloning Trilinos $TRILINOS_REF (serial-first)"
        clone_retry "$TRILINOS_REPO" "$tsrc" "$TRILINOS_REF" || {
            remedy "xyce" "Trilinos clone failed (offline?)" \
                "retry with network, then re-run --install" \
                "https://xyce.sandia.gov/"
            return 1
        }
    fi
    # ShyLU deliberately NOT enabled: the Xyce building guide
    # requires it only for Parallel Xyce, and this build is
    # serial (MPI OFF).
    # gtest TPL likewise OFF: pulled in by ShyLU_NodeTacho
    # tests, and Xyce needs no Trilinos test infra. TriBITS
    # itself names this flag as the escape when gtest is
    # absent — set it up front instead of failing into it.
    # A stale dir from that failed configure has no Makefile;
    # clear it so retries reconfigure clean instead of
    # inheriting the broken cache. A dir WITH a Makefile
    # (failed make, not configure) keeps its objects.
    if [ ! -f "$tsrc/build/Makefile" ]; then
        rm -rf "$tsrc/build"
    fi
    # Fossil guard (2026-11-04): a build dir whose cache claims
    # Epetra=ON but has no packages/epetra/ is a stale
    # hand-rolled tree that incremental reconfigure will not
    # repair — wipe it so the package set configures clean.
    if [ -f "$tsrc/build/CMakeCache.txt" ] \
        && grep -q "^Trilinos_ENABLE_Epetra:BOOL=ON" \
            "$tsrc/build/CMakeCache.txt" \
        && [ ! -d "$tsrc/build/packages/epetra" ]; then
        note "install xyce: stale Trilinos build dir (no epetra package dir); wiping for a clean reconfigure"
        rm -rf "$tsrc/build"
    fi
    # Package set mirrors Xyce's own cmake/trilinos/trilinos-base.cmake
    # (Xyce 7.10 INSTALL.md: Trilinos 14.4 minimum; later versions
    # "not rigorously tested and may not work" — 17.x deleted the
    # Epetra stack outright). Epetra + Triutils stay explicit:
    # EpetraExt pulls Epetra as a required dep, but Xyce configure
    # hard-requires both EpetraExt headers and libtriutils, so pin
    # them loudly instead of trusting auto-enable.
    note "install xyce: building Trilinos (long; per the Xyce building guide)"
    (mkdir -p "$tsrc/build" && cd "$tsrc/build" \
        && cmake -DCMAKE_INSTALL_PREFIX="$tpref" \
            -DTrilinos_ENABLE_ALL_PACKAGES=OFF \
            -DTrilinos_ENABLE_ALL_OPTIONAL_PACKAGES=OFF \
            -DTrilinos_ENABLE_Teuchos=ON -DTrilinos_ENABLE_Epetra=ON \
            -DTrilinos_ENABLE_EpetraExt=ON -DTrilinos_ENABLE_Ifpack=ON \
            -DTrilinos_ENABLE_Amesos=ON -DTrilinos_ENABLE_AztecOO=ON \
            -DTrilinos_ENABLE_Belos=ON -DTrilinos_ENABLE_Amesos2=ON \
            -DTrilinos_ENABLE_Triutils=ON \
            -DTrilinos_ENABLE_Sacado=ON -DTrilinos_ENABLE_Stokhos=ON \
            -DTrilinos_ENABLE_NOX=ON -DTrilinos_ENABLE_Zoltan=ON \
            -DTrilinos_ENABLE_ROL=ON \
            -DTrilinos_ENABLE_TrilinosCouplings=ON \
            -DTrilinos_ENABLE_COMPLEX_DOUBLE=ON \
            -DNOX_ENABLE_LOCA=ON \
            -DEpetraExt_BUILD_BTF=ON \
            -DEpetraExt_BUILD_EXPERIMENTAL=ON \
            -DEpetraExt_BUILD_GRAPH_REORDERINGS=ON \
            -DAmesos_ENABLE_KLU=ON \
            -DAmesos2_ENABLE_KLU2=ON -DAmesos2_ENABLE_Basker=ON \
            -DTPL_ENABLE_AMD=ON \
            -DAMD_INCLUDE_DIRS="$AMD_INC" \
            -DAMD_LIBRARY_DIRS="$AMD_LIB" \
            -DTPL_ENABLE_BLAS=ON -DTPL_ENABLE_LAPACK=ON \
            -DTPL_ENABLE_MPI=OFF \
            -DTPL_ENABLE_gtest=OFF \
            -DCMAKE_POSITION_INDEPENDENT_CODE=TRUE \
            -DCMAKE_BUILD_TYPE=Release .. \
        && make -j"$(nproc)" && make install) || {
        remedy "xyce" "Trilinos build failed" \
            "check the Xyce building guide Trilinos section for $XYCE_REF" \
            "https://xyce.sandia.gov/"
        return 1
    }
    local xsrc="$TOOLS_DIR/src/xyce-$XYCE_REF"
    if [ ! -d "$xsrc" ]; then
        note "install xyce: cloning Xyce $XYCE_REF"
        clone_retry "$XYCE_REPO" "$xsrc" "$XYCE_REF" || {
            remedy "xyce" "Xyce clone failed (offline?)" \
                "retry with network, then re-run --install" \
                "https://xyce.sandia.gov/"
            return 1
        }
    fi
    # Building-guide verbatim: GitHub checkouts (clone or
    # release tarball) lack ./configure — run ./bootstrap
    # first (needs autoconf+automake+libtool, checked above).
    if [ ! -x "$xsrc/configure" ]; then
        note "install xyce: bootstrapping autotools (upstream: ./bootstrap)"
        (cd "$xsrc" && ./bootstrap) || {
            remedy "xyce" "Xyce bootstrap failed" \
                "sudo apt-get install -y autoconf automake libtool-bin, then re-run --install" \
                "https://xyce.sandia.gov/"
            return 1
        }
    fi
    note "install xyce: autotools build against $tpref"
    # Trilinos 14.x builds C++17 by default but Xyce configure
    # defaults to -std=gnu++11, which cannot parse Trilinos
    # headers (Kokkos needs C++14/17): configure dies in its
    # Trilinos check with no Makefile. Match the standard to the
    # just-built Trilinos (CMAKE_CXX_STANDARD from its cache).
    TRILINOS_STD="$(grep '^CMAKE_CXX_STANDARD:' "$tsrc/build/CMakeCache.txt" \
        2>/dev/null | cut -d= -f2)"
    (cd "$xsrc" && CXX="c++ -std=c++${TRILINOS_STD:-17}" ./configure \
        --prefix="$XYCE_PREFIX" \
        --with-trilinosdir="$tpref" ARCHDIR="$tpref" \
        && make -j"$(nproc)" && make install) || {
        remedy "xyce" "Xyce configure/make/install failed" \
            "check the Xyce building guide for $XYCE_REF (+Trilinos compat)" \
            "https://xyce.sandia.gov/"
        return 1
    }
    printf '%s\n' "$XYCE_REF" >"$XYCE_PREFIX/XYCE_REF"
    return 0
}

install_xschem() {
    if [ "$OFFLINE" = "1" ]; then offline_stop "xschem"; return 1; fi
    prereqs_or_remedy "xschem" "$XSCHEM_REPO" git make gcc tclsh wish || return 1
    ATTEMPTED=1
    autotools_git_install xschem "$XSCHEM_REPO" "$XSCHEM_REF" \
        "$XSCHEM_PREFIX" XSCHEM_REF
}

venv_pip_install() {  # id, pin, url
    if [ "$OFFLINE" = "1" ]; then offline_stop "$1"; return 1; fi
    if ! command -v uv >/dev/null 2>&1; then
        remedy "$1" "uv not on PATH" \
            "install uv (see install.sh), then re-run --install" "$3"
        return 1
    fi
    if [ ! -x "$ROOT_DIR/.venv/bin/python" ]; then
        remedy "$1" "engine venv missing" \
            "run scripts/install.sh --install first, then re-run" "$3"
        return 1
    fi
    ATTEMPTED=1
    note "install $1: uv pip install $1==$2 (lockfile update rides a lane commit)"
    uv pip install --python "$ROOT_DIR/.venv/bin/python" "$1==$2" || {
        remedy "$1" "uv pip install failed (offline?)" \
            "retry with network, then re-run --install" "$3"
        return 1
    }
    return 0
}

install_cace() {
    # CACE brings no tools of its own: require its deps first.
    for dep in xschem magic netgen ngspice; do
        case " $MISSING2 " in
            *" $dep "*) : ;;
            *) continue ;;
        esac
        remedy "cace" "dependency $dep not provisioned" \
            "provision $dep first (same --install run), then retry" \
            "https://github.com/efabless/cace"
        return 1
    done
    venv_pip_install cace "$CACE_PIN" "https://github.com/efabless/cace"
}

install_devsim() {
    venv_pip_install devsim "$DEVSIM_PIN" "https://pypi.org/project/devsim/"
}

install_pymeep() {
    if [ "$OFFLINE" = "1" ]; then offline_stop "pymeep"; return 1; fi
    ATTEMPTED=1
    if [ ! -x "$MINIFORGE/bin/conda" ]; then
        note "install pymeep: bootstrapping miniforge"
        local inst="$TOOLS_DIR/miniforge-installer.sh"
        fetch "$MINIFORGE_URL" "$inst" || {
            remedy "pymeep" "miniforge download failed (offline?)" \
                "retry with network, then re-run --install" \
                "https://meep.readthedocs.io/en/latest/Installation/"
            return 1
        }
        bash "$inst" -b -p "$MINIFORGE" || {
            remedy "pymeep" "miniforge bootstrap failed" \
                "see the conda-forge install docs, then re-run --install" \
                "https://meep.readthedocs.io/en/latest/Installation/"
            return 1
        }
    fi
    note "install pymeep: conda create pymeep=$PYMEEP_PIN"
    "$MINIFORGE/bin/conda" create -y -n pymeep -c conda-forge \
        "pymeep=$PYMEEP_PIN" || {
        remedy "pymeep" "conda create failed (offline?)" \
            "retry with network, then re-run --install" \
            "https://meep.readthedocs.io/en/latest/Installation/"
        return 1
    }
    return 0
}

install_openems() {
    if [ "$OFFLINE" = "1" ]; then offline_stop "openems"; return 1; fi
    prereqs_or_remedy "openems" "https://docs.openEMS.de/" \
        git cmake make gcc g++ || return 1
    ATTEMPTED=1
    local csrc="$TOOLS_DIR/src/csxcad-$CSXCAD_REF"
    mkdir -p "$TOOLS_DIR/src" "$OPENEMS_PREFIX" || return 1
    if [ ! -d "$csrc" ]; then
        note "install openems: cloning CSXCAD $CSXCAD_REF"
        clone_retry "$CSXCAD_REPO" "$csrc" "$CSXCAD_REF" || {
            remedy "openems" "CSXCAD clone failed (offline?)" \
                "retry with network, then re-run --install" \
                "https://docs.openEMS.de/"
            return 1
        }
    fi
    note "install openems: building CSXCAD"
    (mkdir -p "$csrc/build" && cd "$csrc/build" \
        && cmake -DCMAKE_INSTALL_PREFIX="$OPENEMS_PREFIX" .. \
        && make -j"$(nproc)" && make install) || {
        remedy "openems" "CSXCAD build failed" \
            "sudo apt-get install -y build-essential cmake git libhdf5-dev libboost-all-dev libtinyxml-dev zlib1g-dev libfparser-dev libcgal-dev, then re-run --install" \
            "https://docs.openEMS.de/"
        return 1
    }
    local osrc="$TOOLS_DIR/src/openems-$OPENEMS_REF"
    if [ ! -d "$osrc" ]; then
        note "install openems: cloning openEMS $OPENEMS_REF"
        clone_retry "$OPENEMS_REPO" "$osrc" "$OPENEMS_REF" || {
            remedy "openems" "openEMS clone failed (offline?)" \
                "retry with network, then re-run --install" \
                "https://docs.openEMS.de/"
            return 1
        }
    fi
    note "install openems: building openEMS"
    (mkdir -p "$osrc/build" && cd "$osrc/build" \
        && cmake -DCMAKE_INSTALL_PREFIX="$OPENEMS_PREFIX" \
            -DCSXCAD_ROOT_DIR="$OPENEMS_PREFIX" .. \
        && make -j"$(nproc)" && make install) || {
        remedy "openems" "openEMS build failed" \
            "see the openEMS manual prerequisites" \
            "https://docs.openEMS.de/"
        return 1
    }
    printf '%s\n' "$OPENEMS_REF" >"$OPENEMS_PREFIX/OPENEMS_REF"
    return 0
}

install_elmer() {
    if [ "$OFFLINE" = "1" ]; then offline_stop "elmer"; return 1; fi
    if [ "$(id -u)" -ne 0 ] && ! command -v sudo >/dev/null 2>&1; then
        remedy "elmer" "apt route needs sudo" \
            "sudo add-apt-repository -y $ELMER_PPA && sudo apt-get update && sudo apt-get install -y elmerfem-csc" \
            "https://www.csc.fi/web/elmer"
        return 1
    fi
    ATTEMPTED=1
    note "install elmer: CSC PPA + apt (needs sudo)"
    sudo add-apt-repository -y "$ELMER_PPA" \
        && sudo apt-get update \
        && sudo apt-get install -y elmerfem-csc || {
        remedy "elmer" "apt install failed" \
            "see the Elmer CSC install docs, then re-run --install" \
            "https://www.csc.fi/web/elmer"
        return 1
    }
    return 0
}

install_palace() {
    remedy "palace" "install docs not yet sourced" \
        "read awslabs palace install docs into docs/provision-sources.md 12 first" \
        "docs/provision-sources.md"
    return 1
}

print_path() {
    # Backend for the installer "add to PATH" flag (BUILD-LOCAL):
    # emit an idempotent, marker-guarded shell block exporting
    # the provisioned bin dirs. Only existing dirs are listed;
    # the AppImage dir holds no binaries and is excluded (the
    # engine-internal resolver may still probe it; PATH entries
    # cost every shell lookup, so this stays minimal). The
    # provisioner never edits the shell itself — the installer
    # appends this block once, guarded by the markers.
    local env_file="$TOOLS_DIR/prov-phase1.env"
    if [ ! -f "$env_file" ]; then
        note "print-path: no $env_file yet."
        remedy "print-path" "toolchain never provisioned" \
            "run scripts/provision_toolchain.sh --install first" \
            "docs/tickets/BUILD-LOCAL.md"
        return 1
    fi
    local dirs=""
    while IFS='=' read -r key value; do
        case "$key" in
            ''|'#'*) continue ;;
        esac
        value="$(printf '%s' "$value" | tr -d '"')"
        [ -n "$value" ] || continue
        local candidate=""
        case "$key" in
            *_PREFIX|*_DIR) candidate="$value/bin" ;;
            PYMEEP_PY) candidate="$(dirname "$value")" ;;
        esac
        [ -n "$candidate" ] || continue
        if [ -d "$candidate" ]; then
            case " $dirs " in
                *" $candidate "*) ;;
                *) dirs="$dirs $candidate" ;;
            esac
        fi
    done <"$env_file"
    if [ -z "$dirs" ]; then
        note "print-path: env file lists no existing bin dirs."
        remedy "print-path" "nothing provisioned yet" \
            "run scripts/provision_toolchain.sh --install first" \
            "docs/tickets/BUILD-LOCAL.md"
        return 1
    fi
    local joined
    joined="$(printf '%s' "$dirs" | tr ' ' '\n' | grep . \
        | tr '\n' ':' | sed 's/:$//')"
    printf '# >>> rocketeda toolchain >>>\n'
    printf '# generated by scripts/provision_toolchain.sh --print-path;\n'
    printf '# re-run after provisioning more tools.\n'
    printf 'export PATH="%s:$PATH"\n' "$joined"
    printf '# <<< rocketeda toolchain <<<\n'
    return 0
}

write_env() {
    # Consumer contract (DIGITAL-FLOW/TIMING-STA): source this file.
    cat >"$TOOLS_DIR/prov-phase1.env" <<EOF
# PROV toolchain paths (generated; do not hand-edit).
OSS_CAD_SUITE_DIR="$OSS_DIR"
LIBRELANE_APPIMAGE="$APPIMAGE"
OPENSTA_PREFIX="$OPENSTA_PREFIX"
MAGIC_PREFIX="$MAGIC_PREFIX"
NETGEN_PREFIX="$NETGEN_PREFIX"
KLAYOUT_PREFIX="$KLAYOUT_PREFIX"
NGSPICE_PREFIX="$NGSPICE_PREFIX"
XYCE_PREFIX="$XYCE_PREFIX"
XSCHEM_PREFIX="$XSCHEM_PREFIX"
OPENEMS_PREFIX="$OPENEMS_PREFIX"
MINIFORGE="$MINIFORGE"
PYMEEP_PY="$PYMEEP_PY"
EOF
}

if [ "$MODE" = "--print-path" ]; then
    print_path
    exit $?
fi

if [ -z "$ONLY" ] && [ "$MODE" = "--check-only" ]; then
    run_checks
    verdict
    exit $?
fi

net_ok() {
    # One fast preflight so air-gapped runs get offline remedies
    # at once instead of one slow timeout per tool. A passed
    # preflight that later flakes still gets per-fetch retry.
    curl -sS -o /dev/null --max-time 8 "$OSS_URL" 2>/dev/null
}

if [ -n "$ONLY" ]; then
    if [ "$OFFLINE" != "1" ] && [ "$MODE" = "--install" ] && ! net_ok; then
        note "network unreachable (preflight to $OSS_URL failed): offline remedies follow."
        OFFLINE=1
    fi
    run_only_checks "$ONLY"
    if [ "$MODE" = "--install" ] \
        && { [ -n "$MISSING" ] || [ -n "$MISSING2" ] || [ -n "$MISSINGD" ]; }; then
        install_one "$ONLY" || true
        run_only_checks "$ONLY"
    fi
    scoped_verdict "$ONLY"
    exit $?
fi

run_checks
if [ "$OK_COUNT" -eq 4 ] && [ "$OK2_COUNT" -eq 7 ]; then
    mkdir -p "$TOOLS_DIR" 2>/dev/null && write_env
    verdict
    exit $?
fi

if [ "$OFFLINE" != "1" ] && ! net_ok; then
    note "network unreachable (preflight to $OSS_URL failed): offline remedies follow."
    OFFLINE=1
fi

# Install what is missing, then re-assert everything from scratch.
if [ "$bundle_ok" != "yes" ]; then
    install_bundle || true
fi
case " $MISSING " in
    *" librelane "*) install_librelane || true ;;
esac
case " $MISSING " in
    *" opensta "*) install_opensta || true ;;
esac
for tool in magic netgen klayout ngspice xyce xschem cace pymeep openems elmer devsim; do
    case " $MISSING2 " in
        *" $tool "*) "install_$tool" || true ;;
    esac
done

run_checks
if [ "$OK_COUNT" -eq 4 ] || [ "$ATTEMPTED" = "1" ]; then
    mkdir -p "$TOOLS_DIR" 2>/dev/null && write_env
fi
verdict
exit $?