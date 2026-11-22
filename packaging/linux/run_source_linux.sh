#!/bin/bash
# Runs Lastbook from a source checkout on Linux with video working. Never packaged; the .deb does all of this itself (build_app_linux.sh, shell_linux.py).
#
#   bash packaging/linux/run_source_linux.sh [app arguments...]       e.g. --data /path/to/LastbookData
#   bash packaging/linux/run_source_linux.sh --check /path/to/LastbookData [videos/<folder>/<file>.mp4 ...]
#
# Why: the app's pages ask for videos at lastbook://app/videos/..., and only lastbooksrc (packaging/linux/gst/lastbooksrc.c) can open such an
# address for GStreamer. The packaged app ships it in /opt/lastbook/gst and shell_linux.py points WebKit at it, but only when frozen. A source run
# has no plugin and every video says "This video file couldn't be played here". This script:
#   1. checks the tools and GStreamer development files needed to build the plugin, and the decoders the library's videos need;
#   2. builds lastbooksrc into derived/gst/ (again only when gst/lastbooksrc.c is newer), with the same compiler flags as the package;
#   3. sets GST_PLUGIN_PATH_1_0 and WEBKIT_GST_ALLOWED_URI_PROTOCOLS=lastbook for this launch only, and runs app/main.py.
# --check builds the plugin, then decodes the first frames of a few library videos through lastbooksrc (no window, no sound), and says which failed.
#
# Packages (Arch / Ubuntu):
#   build:    gcc pkg-config gstreamer                     / gcc pkg-config libgstreamer1.0-dev
#   window:   webkit2gtk-4.1 python-gobject                / gir1.2-webkit2-4.1 python3-gi
#   decoders: gst-plugins-base gst-plugins-good gst-libav  / gstreamer1.0-plugins-good gstreamer1.0-libav
#             gst-plugin-dav1d (AV1: many library videos)  / gstreamer1.0-plugins-bad
# Without the AV1 decoder those videos fail or play with sound and a black picture. A virtual environment needs --system-site-packages to see gi.
set -euo pipefail
HERE="$(dirname "$(realpath "$0")")"
ROOT="$(dirname "$(dirname "$HERE")")"
GST="$ROOT/derived/gst"
SO="$GST/libgstlastbooksrc.so"
SRC="$HERE/gst/lastbooksrc.c"

if [ -n "${PYTHON:-}" ]; then PY="$PYTHON"; elif [ -x "$ROOT/.venv/bin/python" ]; then PY="$ROOT/.venv/bin/python"; else PY=python3; fi

missing=()
for t in gcc pkg-config; do command -v "$t" >/dev/null || missing+=("$t"); done
if command -v pkg-config >/dev/null && ! pkg-config --exists gstreamer-1.0 gstreamer-base-1.0; then
  missing+=("GStreamer development files (Arch: gstreamer, Ubuntu: libgstreamer1.0-dev)")
fi
if [ ${#missing[@]} -gt 0 ]; then
  printf 'cannot build lastbooksrc, missing: %s\n' "${missing[@]}" >&2
  exit 1
fi

if [ ! -f "$SO" ] || [ "$SRC" -nt "$SO" ]; then
  mkdir -p "$GST"
  # shellcheck disable=SC2046   # pkg-config's flags are meant to split
  gcc -shared -fPIC -O2 -Wall -Werror "$SRC" -o "$SO" $(pkg-config --cflags --libs gstreamer-1.0 gstreamer-base-1.0)
  echo "built $SO"
fi

export GST_PLUGIN_PATH_1_0="$GST${GST_PLUGIN_PATH_1_0:+:$GST_PLUGIN_PATH_1_0}"
export WEBKIT_GST_ALLOWED_URI_PROTOCOLS=lastbook   # WebKit's player refuses any other scheme before GStreamer sees it

# The decoders, by the element WebKit's player will look for. A warning only: the app still runs, those videos do not.
if command -v gst-inspect-1.0 >/dev/null; then
  gst-inspect-1.0 --exists lastbooksrc || { echo "GStreamer does not load $SO (gst-inspect-1.0 $SO says why)" >&2; exit 1; }
  while read -r els what arch ubuntu; do   # els: any one of these elements will do
    found=
    for el in ${els//|/ }; do gst-inspect-1.0 --exists "$el" && { found=1; break; }; done
    [ -n "$found" ] || echo "warning: no $what decoder (${els//|/ or }): install $arch (Arch) or $ubuntu (Ubuntu)" >&2
  done <<'EOF'
qtdemux MP4 gst-plugins-good gstreamer1.0-plugins-good
avdec_h264 H.264 gst-libav gstreamer1.0-libav
avdec_aac AAC gst-libav gstreamer1.0-libav
dav1ddec|av1dec AV1 gst-plugin-dav1d gstreamer1.0-plugins-bad
EOF
else
  echo "warning: gst-inspect-1.0 not found (Arch: gstreamer, Ubuntu: gstreamer1.0-tools); decoders not checked" >&2
fi

if [ "${1:-}" != --check ]; then
  cd "$ROOT"
  exec "$PY" app/main.py "$@"
fi

# --check DATA [videos/...]: decode 48 frames of each through lastbooksrc, the way WebKit's player opens them.
DATA="${2:?usage: $0 --check /path/to/LastbookData [videos/<folder>/<file>.mp4 ...]}"
export LASTBOOK_LIBRARY
LASTBOOK_LIBRARY="$(realpath "$DATA")/library-data"   # what engine/paths.py sets, and where lastbooksrc reads from
[ -d "$LASTBOOK_LIBRARY/videos" ] || { echo "no videos folder in $LASTBOOK_LIBRARY" >&2; exit 1; }
command -v gst-launch-1.0 >/dev/null || { echo "--check needs gst-launch-1.0 (Arch: gstreamer, Ubuntu: gstreamer1.0-tools)" >&2; exit 1; }
shift 2
if [ $# -eq 0 ]; then   # by default the first three videos in the library
  # read into the arguments themselves: bash 3.2 on macOS has no mapfile
  while IFS= read -r vid; do set -- "$@" "$vid"; done < <(cd "$LASTBOOK_LIBRARY" && find -L videos -type f \( -name '*.mp4' -o -name '*.webm' -o -name '*.mkv' \) | sort | head -3)
fi
[ $# -gt 0 ] || { echo "no videos found under $LASTBOOK_LIBRARY/videos" >&2; exit 1; }
fail=0
for rel in "$@"; do
  uri="lastbook://app/$("$PY" -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$rel")"
  # The codec name is only a label (gst-discoverer-1.0: Arch gstreamer, Ubuntu gstreamer1.0-plugins-base-apps); the decode below is the check.
  codec="$(gst-discoverer-1.0 "$LASTBOOK_LIBRARY/$rel" 2>/dev/null | sed -n 's/^ *video #[0-9]*: //p' | head -1 || true)"
  if out="$(timeout 60 gst-launch-1.0 -q uridecodebin uri="$uri" caps="video/x-raw(ANY)" name=d d. ! fakesink num-buffers=48 2>&1)"; then
    echo "ok    ${codec:-?}  $rel"
  else
    echo "FAIL  ${codec:-?}  $rel"; printf '%s\n' "$out" | grep -v '^$' | tail -3 | sed 's/^/      /'; fail=1
  fi
done
exit $fail
