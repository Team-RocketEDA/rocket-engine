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
#
# Honors:
#   TOOLS_DIR         app-owned tools dir (default: ~/tools)
#   OSS_CAD_SUITE_DIR bundle dir (default: $TOOLS_DIR/oss-cad-suite)
#   PROV_OFFLINE=1    skip every network attempt (fast air-gap path)
#
# Phase 2 (rest of the PRD matrix) is out of scope here.

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
# -------------------------------------------------------------

OSS_URL="https://github.com/YosysHQ/oss-cad-suite-build/releases"
LIBRELANE_URL="https://github.com/librelane/librelane/releases"
LIBRELANE_DOCS="https://librelane.readthedocs.io/en/stable/installation"
LIBRELANE_DOC_APPIMAGE="$LIBRELANE_DOCS/appimage_installation/installation_linux.html"
LIBRELANE_DOC_NIX="$LIBRELANE_DOCS/nix_installation/installation_linux.html"
OPENSTA_URL="https://github.com/The-OpenROAD-Project/OpenSTA"
OPENSTA_SHORT="$(printf '%s' "$OPENSTA_PIN" | cut -c1-7)"

MODE="${1:---install}"
if [ "$MODE" != "--check-only" ] && [ "$MODE" != "--install" ]; then
    echo "usage: provision_toolchain.sh [--check-only|--install]" >&2
    exit 2
fi

TOOLS_DIR="${TOOLS_DIR:-$HOME/tools}"
OSS_DIR="${OSS_CAD_SUITE_DIR:-$TOOLS_DIR/oss-cad-suite}"
LIBRELANE_DIR="$TOOLS_DIR/librelane-$LIBRELANE_PIN"
APPIMAGE="$LIBRELANE_DIR/librelane-devshell-x86_64.AppImage"
OPENSTA_PREFIX="$TOOLS_DIR/opensta-$OPENSTA_SHORT"
OFFLINE="${PROV_OFFLINE:-0}"

# Dev-PATH inside the provisioner: the bundle and tools bins win
# over ambient, so checks never depend on the caller's PATH.
PATH="$OSS_DIR/bin:$TOOLS_DIR/bin:$PATH"
export PATH

OK_COUNT=0
MISSING=""
ATTEMPTED=0

note() { printf '%s\n' "$1"; }
remedy() {  # tool, cause, next-step, url
    printf 'REMEDY %s: %s. next: %s. see: %s\n' "$1" "$2" "$3" "$4"
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
        bundle_ok="no"
        return 0
    fi
    local got
    got="$(head -n 1 "$ver_file" | tr -d '[:space:]')"
    if [ "$got" = "$OSS_CAD_SUITE_PIN" ]; then
        note "oss-cad-suite $got [$OSS_DIR]"
        bundle_ok="yes"
    else
        note "oss-cad-suite MISMATCH got $got want $OSS_CAD_SUITE_PIN"
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
        mark_missing "$tool"
        return 0
    fi
    if [ "$bundle_ok" != "yes" ]; then
        note "$tool UNPINNED ($bin resolves outside bundle $OSS_CAD_SUITE_PIN)"
        remedy "$tool" "bundle $OSS_CAD_SUITE_PIN not asserted" \
            "run scripts/provision_toolchain.sh --install" "$OSS_URL"
        mark_missing "$tool"
        return 0
    fi
    local banner
    banner="$(banner_of "$@")"
    case "$banner" in
        "$expect"*)
            note "$tool $banner [$bin]"
            mark_ok
            ;;
        *)
            note "$tool MISMATCH got '$banner' want '$expect*'"
            remedy "$tool" "banner '$banner' != pin '$expect*'" \
                "run scripts/provision_toolchain.sh --install" "$OSS_URL"
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
                    mark_missing "librelane"
                    return 0
                    ;;
            esac
        fi
        mark_ok
        return 0
    fi
    note "librelane absent [$APPIMAGE]"
    remedy "librelane" "supported distribution $LIBRELANE_PIN absent" \
        "run scripts/provision_toolchain.sh --install" \
        "$LIBRELANE_DOC_APPIMAGE"
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
            mark_ok
            return 0
        fi
        note "opensta UNRUNNABLE ($sta prints no version)"
        remedy "opensta" "$sta prints no version" \
            "rebuild via scripts/provision_toolchain.sh --install" \
            "$OPENSTA_URL"
        mark_missing "opensta"
        return 0
    fi
    local ambient
    ambient="$(command -v sta || true)"
    if [ -n "$ambient" ]; then
        note "opensta UNPINNED (ambient $ambient, no $pinfile)"
        remedy "opensta" "ambient sta is not the pinned build" \
            "run scripts/provision_toolchain.sh --install" "$OPENSTA_URL"
    else
        note "opensta absent [$sta]"
        remedy "opensta" "pinned build $OPENSTA_SHORT absent" \
            "run scripts/provision_toolchain.sh --install" "$OPENSTA_URL"
    fi
    mark_missing "opensta"
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
}

verdict() {
    if [ "$OK_COUNT" -eq 4 ]; then
        note "PROV-PHASE1: OK (4/4 version-asserted)"
        return 0
    fi
    note "PROV-PHASE1: DEGRADED (missing:$MISSING)"
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
    for tool in git cmake make g++ swig bison flex; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            missing_prereq="$missing_prereq $tool"
        fi
    done
    if [ -n "$missing_prereq" ]; then
        remedy "opensta" "build prerequisites missing:$missing_prereq" \
            "sudo apt-get install -y$missing_prereq tcl-dev libeigen3-dev" \
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
        (cd "$src/cudd" && ./configure --prefix="$src/cudd-install" \
            && make -j"$(nproc)" && make install) || {
            remedy "opensta" "CUDD build failed" \
                "see $OPENSTA_URL README prerequisites" "$OPENSTA_URL"
            return 1
        }
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

write_env() {
    # Consumer contract (DIGITAL-FLOW/TIMING-STA): source this file.
    cat >"$TOOLS_DIR/prov-phase1.env" <<EOF
# PROV phase 1 toolchain paths (generated; do not hand-edit).
OSS_CAD_SUITE_DIR="$OSS_DIR"
LIBRELANE_APPIMAGE="$APPIMAGE"
OPENSTA_PREFIX="$OPENSTA_PREFIX"
EOF
}

if [ "$MODE" = "--check-only" ]; then
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

run_checks
if [ "$OK_COUNT" -eq 4 ]; then
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

run_checks
if [ "$OK_COUNT" -eq 4 ] || [ "$ATTEMPTED" = "1" ]; then
    mkdir -p "$TOOLS_DIR" 2>/dev/null && write_env
fi
verdict
exit $?