# Third-party components

HAVC is **MIT licensed** (see [`LICENSE`](../LICENSE)). The installer also
downloads and unpacks a few **external command-line tools** that the GUI needs
for video work. They are redistributed **unmodified**, as pinned archives
whose sha256 the bootstrap verifies, and each remains under its own license.

| Component | Bundled file | License | Upstream |
| --------- | ------------ | ------- | -------- |
| **x265** | `tools/x265/x265.exe` | GPL-2.0 (or commercial) | [videolan.org/developers/x265](https://www.videolan.org/developers/x265.html) |
| **x264** | `tools/x264/x264.exe` | GPL-2.0 (or commercial) | [videolan.org/developers/x264](https://www.videolan.org/developers/x264.html) |
| **MKVToolNix** (`mkvmerge`) | `tools/MKVToolNix/mkvmerge.exe` | GPL-2.0 | [mkvtoolnix.download](https://mkvtoolnix.download/) |
| **FFmpeg** (`ffprobe`) | `tools/ffmpeg/ffprobe.exe` | **GPL-3.0** | [ffmpeg.org](https://ffmpeg.org/) |
| **NVEncC** (NVEnc) | `tools/NVEncC/NVEncC64.exe` | MIT | [github.com/rigaya/NVEnc](https://github.com/rigaya/NVEnc) |

`tools.zip` and `NVEncC_9.17_x64.zip` are published under
[HAVC Assets v1.0.0](https://github.com/dan64/HAVCServerDiT/releases/tag/v1.0.0).

## FFmpeg / FFprobe

The bundled `ffprobe.exe` is a **GPL-3.0** FFmpeg build: it is compiled with
`--enable-gpl --enable-version3`, which is required by the GPL-only libraries
it links (`libx264`, `libx265`, `libxvid`, …). Its license text and build
notice ship next to the binary, inside the same `tools.zip`:

```
tools/ffmpeg/
├── ffprobe.exe
├── LICENSE.txt     GNU General Public License v3
└── README.txt      build identification, configuration and bundled libraries
```

The FFmpeg project is the upstream source of that build; its source code is
available from <https://ffmpeg.org/download.html> and the
[FFmpeg Git repository](https://git.ffmpeg.org/ffmpeg.git) (see `README.txt`
for the exact snapshot). HAVC does not modify FFmpeg.

`ffprobe` is used for one thing only: reading the source video's frame
timestamps before muxing, so a variable-frame-rate source keeps its duration.
It runs as a separate process — no FFmpeg library is linked into HAVC — and
when it is missing or fails the GUI logs a warning and falls back to
constant-frame-rate muxing.

## A note on the other binaries

`x265.exe`, `x264.exe` and `mkvmerge.exe` are GPL programs as well; they are
invoked as separate processes and their license terms are those of the
upstream projects linked above. If a license file or a source pointer is
missing from a bundled archive, treat it as a packaging bug and open an issue.
