#!/bin/sh
set -eu

cd "$(dirname "$0")/../.."
build_dir="${1:-build/debian}"
output_dir="${2:-$PWD}"
mkdir -p "$build_dir" "$output_dir"
build_dir="$(realpath "$build_dir")"
output_dir="$(realpath "$output_dir")"

if [ -f "$build_dir/meson-private/coredata.dat" ]; then
    meson setup --reconfigure "$build_dir" --prefix=/usr
else
    meson setup "$build_dir" --prefix=/usr
fi
meson compile -C "$build_dir"
version="$(meson introspect "$build_dir" --projectinfo | python3 -c 'import json, sys; print(json.load(sys.stdin)["version"])')"
if [ -n "${EXPECTED_RELEASE_TAG:-}" ] && [ "$EXPECTED_RELEASE_TAG" != "v$version" ]; then
    echo "Release tag $EXPECTED_RELEASE_TAG does not match v$version" >&2
    exit 1
fi

stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
DESTDIR="$stage" meson install -C "$build_dir" --no-rebuild
mkdir -p "$stage/DEBIAN"
cat > "$stage/DEBIAN/control" <<CONTROL
Package: pinplan-notes
Version: $version
Provides: betternotes-lite
Conflicts: betternotes-lite, betternotes
Replaces: betternotes-lite, betternotes
Architecture: all
Maintainer: Community Fork <noreply@github.com>
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, gir1.2-gdkpixbuf-2.0
Recommends: pkexec
Description: PinPlan lightweight bilingual sticky notes and checklists
 GTK4 and Libadwaita sticky notes using distribution shared libraries.
CONTROL
find "$stage/usr" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$stage/usr" -type f -name '*.pyc' -delete
package="$output_dir/pinplan-notes_${version}_all.deb"
dpkg-deb --build --root-owner-group "$stage" "$package"
dpkg-deb --info "$package"
