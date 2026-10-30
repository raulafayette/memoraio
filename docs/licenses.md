# Licensing and dependency audit

Original code: MIT. It supports public contributions and commercial use while retaining notices and warranty disclaimer. It does not grant rights in captured media, names, personal data, third-party code, models or platform services.

| Option | Commercial use | Main obligations/tradeoff |
|---|---|---|
| MIT | Allowed | Simple permissive terms and notice retention; no express patent grant |
| Apache-2.0 | Allowed | Express patent terms, notice/change requirements; requires care with GPLv2-only combinations |
| GPLv3 | Allowed | Copyleft obligations for covered conveyed derivatives; different implications for an open-core boundary |

MIT was chosen for original source. CLI dependencies installed separately keep their own terms; subprocess separation is not a blanket legal exemption for any future bundled/combined distribution. Reassess the actual package before release.

The installed Python inventory contains 70 distributions with license evidence, including transitive packages. See dependencies.json for versions, declarations, classifiers, requirements and license-file names. Evidence availability is not a completed legal opinion or a vulnerability audit. Review embedded third-party notices as well as top-level SPDX labels.

Highlights: yt-dlp Unlicense; youtube-transcript-api and Instaloader MIT; gallery-dl GPL family; mutagen GPL-2.0-or-later; MLX/MLX-LM/MLX Whisper MIT; E5 and Whisper model licenses must remain with downloaded models; the selected Qwen model declares Apache-2.0. cryptography is Apache-2.0 OR BSD-3-Clause. certifi and tqdm include MPL obligations. Numerical/ML wheels have additional bundled-license expressions; do not label all wheels MIT.

The locally installed FFmpeg was configured with --enable-gpl and --enable-version3, so its effective binary licensing differs from a minimal LGPL build. FFmpeg is not copied into the shell/source package. Node, Python, Swift runtimes, system frameworks and any future bundled native libraries require their own notice/redistribution review. No standalone executable is assumed to share this project's MIT license.

Sources: [MIT](https://opensource.org/license/mit), [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0), [GPLv3](https://www.gnu.org/licenses/gpl-3.0.html), [FFmpeg legal](https://ffmpeg.org/legal.html), [yt-dlp](https://github.com/yt-dlp/yt-dlp), [Instaloader](https://github.com/instaloader/instaloader), [gallery-dl](https://github.com/mikf/gallery-dl), and the distribution metadata/license files recorded in the inventory.
