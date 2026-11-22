# Third-party notices

Lastbook builds on the work below. Each part keeps its own licence. The **Where** column says whether it is in this
repository, bundled into the apps by the build, or downloaded by setup.

**Checked** means the licence was read from the licence file or package metadata of the exact version the builds use.
**Upstream** means it is taken from the project's own published licence because no local copy was at hand when this list
was written. Check those before a public release.

Versions are the pins in `packaging/requirements*.txt`, `packaging/llm/*.sh`, `packaging/build_app_windows.sh` and
`llm_local.py`.

## Vendored in this repository

| Component | Version | Licence | Source | Checked |
|---|---|---|---|---|
| Nunito (`web/Nunito-Variable.woff2`, the Ask page's headings; the same file as `website-next/fonts/`), copied into the app with `web/` | variable, as in `website-next/fonts/` | SIL Open Font License 1.1 | https://github.com/googlefonts/nunito | Checked: `web/Nunito-OFL.txt` |
| pypdfium2 (`engine/vendor-macos/` on Mac; installed from PyPI for the Windows build) | 5.14.0 | Apache-2.0 or BSD-3-Clause; data files CC-BY-4.0 | https://github.com/pypdfium2-team/pypdfium2 | Checked: `pypdfium2-5.14.0.dist-info/licenses/` |
| PDFium, inside pypdfium2's `libpdfium.dylib` | as built by pdfium-binaries | BSD-3-Clause (The PDFium Authors) | https://pdfium.googlesource.com/pdfium, https://github.com/bblanchon/pdfium-binaries | Checked: `BUILD_LICENSES/pdfium.txt`, `pdfium-binaries.txt` |
| Libraries built into PDFium: abseil, agg 2.3, fast_float, FreeType, ICU, Little CMS, libjpeg-turbo, OpenJPEG, libpng, LLVM libc, simdutf, zlib | as built | Each under its own licence (Apache-2.0, BSD-style, FreeType/FTL, Unicode, MIT, IJG, zlib and others) | see each file | Checked: the full texts are in `engine/vendor-macos/pypdfium2-5.14.0.dist-info/licenses/data/darwin_arm64/BUILD_LICENSES/` |

## Bundled into the apps by the build

| Component | Version | Licence | Source | Checked |
|---|---|---|---|---|
| Python (runtime bundled by PyInstaller) | 3.11.18 (Mac), 3.14.10 or a later 3.14 (Windows) | PSF-2.0 | https://www.python.org | Upstream |
| PyInstaller bootloader | 6.22.3 | GPL-2.0-or-later with the PyInstaller exception, which allows bundling programs under any licence | https://github.com/pyinstaller/pyinstaller | Checked: package metadata |
| python-libzim | 3.13.1 (Mac), 3.13.0 (Windows) | **GPL-3.0-or-later** | https://github.com/openzim/python-libzim | Checked: `libzim-3.13.1.dist-info/licenses/LICENSE` |
| libzim (C++, inside python-libzim's wheel) | 9 | GPL-2.0 | https://github.com/openzim/libzim | Upstream |
| Xapian and ICU 73, built into libzim | as built | Xapian: GPL-2.0-or-later; ICU: Unicode License | https://xapian.org, https://icu.unicode.org | Upstream (both found in the binary) |
| zstd and liblzma (xz), used by libzim | as built | zstd: BSD-3-Clause or GPL-2.0; liblzma: 0BSD/public domain | https://github.com/facebook/zstd, https://tukaani.org/xz/ | Upstream |
| NumPy | 2.4.6 (Mac), 2.5.4 (Windows) | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | https://numpy.org | Checked: package metadata (2.4.6) |
| Beautiful Soup 4 | 4.15.0 | MIT | https://www.crummy.com/software/BeautifulSoup/ | Checked: package metadata |
| soupsieve (used by Beautiful Soup) | 3.0.4 | MIT | https://github.com/facelessuser/soupsieve | Checked: package metadata |
| PyObjC: pyobjc-core, Cocoa, WebKit (Mac) | 13.0 | MIT | https://github.com/ronaldoussoren/pyobjc | Checked: package metadata |
| onnxruntime (Windows) | 1.31.1 | MIT; its bundled components are listed in its `ThirdPartyNotices.txt` | https://github.com/microsoft/onnxruntime | Checked: metadata and notices of 1.31.0 |
| Hugging Face tokenizers (Windows) | 0.23.3 | Apache-2.0; the Rust crates built into it are listed in its SBOM (`dist-info/sboms`) | https://github.com/huggingface/tokenizers | Checked: package metadata |
| pythonnet (Windows) | 3.2.1 | MIT | https://github.com/pythonnet/pythonnet | Upstream |
| clr_loader (Windows) | 0.3.1 | MIT | https://github.com/pythonnet/clr-loader | Upstream |
| Microsoft WebView2 SDK: `Microsoft.Web.WebView2.Core.dll`, `Microsoft.Web.WebView2.WinForms.dll`, `WebView2Loader.dll` (Windows) | 1.0.3856.49 | Microsoft's licence in the NuGet package (`LICENSE.txt`), which allows redistributing these files with an app | https://www.nuget.org/packages/Microsoft.Web.WebView2 | Upstream: check the package's `LICENSE.txt` before release |
| Microsoft Edge WebView2 Runtime (Windows) | installed by Windows | Microsoft software licence terms | https://developer.microsoft.com/microsoft-edge/webview2/ | Not bundled: the app uses the copy Windows provides |
| llama.cpp and ggml, in `lastbook-llm` (optional local AI runner) | tag b12032 (dde879bc) | MIT (Copyright the ggml authors) | https://github.com/ggml-org/llama.cpp | Checked: `LICENSE`; it ships beside the runner as `LICENSE-llama.cpp.txt` |
| nlohmann/json, used by llama.cpp's `common/` | as vendored in b12032 | MIT | https://github.com/nlohmann/json | Checked: `licenses/LICENSE-jsonhpp` |
| LLVM libc++, libunwind, OpenMP runtime (`libc++.dll`, `libunwind.dll`, `libomp.dll`, Windows runner) | llvm-mingw 20261020 | Apache-2.0 WITH LLVM-exception | https://github.com/mstorsjo/llvm-mingw | Checked: ships as `LICENSE-llvm-mingw.txt` |

Build-only tools (uv, CMake, Ninja, glslc/shaderc, Vulkan and SPIR-V headers, pyinstaller-hooks-contrib, altgraph,
macholib, setuptools, packaging) are used to make the apps, and none of their code is bundled except as their licences
allow. The Vulkan loader (`vulkan-1.dll`) comes with the graphics driver and is not bundled.

## Downloaded by setup, never bundled

| Component | Version | Licence | Source | Checked |
|---|---|---|---|---|
| Gemma 4 26B A4B instruct, GGUF quantization by Unsloth (`gemma-4-26B-A4B-it-UD-Q4_K_M.gguf`) | revision pinned in `llm_local.py` | Apache-2.0, per the model card | https://huggingface.co/unsloth (Google's Gemma 4 release) | Upstream: check the model card and its licence file before release |
| BAAI bge-small-en-v1.5 (ONNX), meaning-based search | as pinned | MIT, per the model card | https://huggingface.co/BAAI/bge-small-en-v1.5 | Upstream: the local copy has no licence file beside it |

## Development and test tools (not bundled, not downloaded by the apps)

These are used only to run optional tests from a checkout. They are not in any package, are not required to build or
run Lastbook, and the build's package scan rejects test code. All of them work offline once installed.

| Component | Used by | Licence | Source | Checked |
|---|---|---|---|---|
| Playwright for Python (`pip install playwright`; the wheel carries its own Node.js driver). Run it against a Chromium you already have, so no browser download is needed | `app/tests/i18n_browser.py` | Apache-2.0 | https://github.com/microsoft/playwright-python | Checked: package metadata of 1.65.2 (`License-Expression: Apache-2.0`) |
| pyatspi (Ubuntu package `python3-pyatspi`, part of at-spi2) | `app/tests/linux_i18n_smoke.py`, `app/tests/linux_at.py` | LGPL-2.0-or-later | https://gitlab.gnome.org/GNOME/at-spi2-core | Upstream |
| xdotool (Ubuntu package `xdotool`) | `app/tests/linux_i18n_smoke.py` | BSD-3-Clause | https://github.com/jordansissel/xdotool | Upstream |

## iPad development preview (`mobile/ipad/`)

There is no published iPad build. These parts go into an iPad app that a contributor builds from this source.

| Component | Version | Licence | Source | Checked |
|---|---|---|---|---|
| llama.cpp and ggml, compiled into the app as a static library (`scripts/build_llama_ios.sh`) | dde879bc (as the desktop runner) | MIT (Copyright the ggml authors) | https://github.com/ggml-org/llama.cpp, fetched by `scripts/prepare_dependencies.sh`, not stored here | Checked: `LICENSE`, copied into the app as `licenses/llama.cpp-LICENSE.txt` |
| nlohmann/json, used by llama.cpp's fitting code | as vendored in dde879bc | MIT | https://github.com/nlohmann/json | Checked: `licenses/LICENSE-jsonhpp`, copied into the app as `licenses/LICENSE-jsonhpp.txt` |
| Root CA certificates pinned for setup downloads (`Lastbook/Engine/Install/DownloadRoots.swift`, generated from `engine/setup/roots.pem`) | as in `roots.pem` | Public certificates; no licence restriction on use for verification | the issuing certificate authorities | Upstream |
| Lastbook web UI (`web/`) and guides (`content/`), copied into the app at build time | this repository | MIT (Lastbook) | this repository | n/a |
| Apple frameworks (SwiftUI, WebKit, AVFoundation, VideoToolbox, PDFKit, Metal, Accelerate, SQLite) | system | Apple SDK terms; part of iPadOS, not bundled | Apple | n/a |
| Gemma 4 26B A4B (local AI model) | as desktop | see "Downloaded by setup" above | Hugging Face, downloaded only when the person chooses it | as above |
| ffmpeg (Mac development tools only: `tools/videocompat --ffmpeg`, `tools/validate_videocompat.py`) | supplied by the developer | LGPL-2.1+ or GPL, depending on the build | https://ffmpeg.org | Not bundled, downloaded or required by the app |

## Website

| Component | Licence | Source | Checked |
|---|---|---|---|
| Atkinson Hyperlegible Next (`website/fonts/`) | SIL Open Font License 1.1 | https://github.com/googlefonts/atkinson-hyperlegible-next | Checked: `website/fonts/OFL.txt` |
| Nunito (`website-next/fonts/`) | SIL Open Font License 1.1 | https://github.com/googlefonts/nunito | Checked: `website-next/fonts/OFL.txt` |

## Library content

The manuals, videos, encyclopedias and map data in the library packs are not part of this repository. Each pack has a
Sources and permissions page with the publisher and terms of every item. The offline map uses OpenStreetMap data
(ODbL, © OpenStreetMap contributors) and US government data such as USGS, NOAA and USACE, as credited on the map.
