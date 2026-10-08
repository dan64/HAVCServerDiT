# Troubleshooting

**`CUDA out of memory`**
Close other GPU applications. On 16 GB cards the server automatically enables sequential CPU offload for layers that do not fit in VRAM.

**`dit_colorize_main.py NOT FOUND`**
Use `--module-dir` to point the server to the directory that contains `dit_colorize_main.py`:

```bash
python dit_rpc_server.py --module-dir /path/to/dit_colorize_main
```

**`Model 'xxx' is not supported`**
Supported values for `model_name` are `"nunchaku-qwen"` (FP4/INT4), `"gguf-qwen"` (Q3_K_S, Q4_K_S, Q5_K_M, Q6_K, Q8_0), `"longcat-gguf"`, and `"qwen21-viggle"`. For `"gguf-qwen"`, the quantization is selected via the `quant` field in the config (e.g. `"q4"`).

**Pipeline takes a long time to load**
**Nunchaku**: on the first run the model weights (~15–30 GB) are downloaded from HuggingFace.
Subsequent runs load from the local cache.
**GGUF**: only the VAE and tokenizer (~320 MB) are downloaded from HuggingFace; the UNet and CLIP are loaded directly from the local `.gguf` files. Set `cache_dir` in the config to control where the cache is stored.

**Colors look faded or grayish**
Increase the number of **Colorization Steps** and/or disable **Fast Pipeline**, then re-run. See [Suggested Inference Steps](usage.md#-suggested-inference-steps) for the recommended per-model values.

---

## Installation and updates

**SmartScreen warning on `HAVC-Setup-*.exe`**
The installer is not code-signed yet: *Windows protected your PC* → **More info** → **Run anyway**. The sha256 of every asset is published in the release notes if you want to verify the download first.

**"The manifest could not be fetched" in the installer**
Check the connection first. As fallbacks: keep a `release.json` next to the exe (it ships in the release assets), or launch the manager with `--release-tag vX`.

**An update brought no new files, and Repair did not either**
*Repair* restores the currently installed version from the cached wheel — it never upgrades. New or changed files arrive with an *update* ("Check for updates").

**The uninstaller asks about the models folder**
The default keeps `<install>\comfy_bridge\models` (tens of GB): reinstalling into the same folder reuses them without re-downloading.
