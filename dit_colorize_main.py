"""
-------------------------------------------------------------------------------
Author: Dan64
Date: 2024-12-26
version:
LastEditors: Dan64
LastEditTime: 2026-01-14
-------------------------------------------------------------------------------
Batch colorization using the SVDQuant FP4 model:
  svdq-fp4_r128-qwen-image-edit-2509-lightning-4steps-251115.safetensors

- Optimized for RTX 50 (Blackwell)
- Uses Nunchaku SVDQuant (4-bit) for the transformer
- Maintains FP16/BF16 for peripheral layers
-------------------------------------------------------------------------------
"""

import os
import argparse
import time
import math
from pathlib import Path
from PIL import Image, ImageEnhance, ImageStat, ImageOps


def set_hf_cache_dir(hf_cache_dir: str):

    if os.path.isdir(hf_cache_dir):
        os.environ['HF_HOME'] = hf_cache_dir
        os.environ['HF_HUB_CACHE'] = os.path.join(hf_cache_dir, 'hub')
        from huggingface_hub import constants
        print(f"HF_HOME: {constants.HF_HOME}")
        print(f"HF_HUB_CACHE: {constants.HF_HUB_CACHE}")

# ----------------------------
# Load SVDQuant FP4 pipeline
# ----------------------------
def load_nunchaku_pipeline(model_name: str, model_precision: str, model_rank, model_inference_steps,
                           cache_dir: str, base_model_path: str="", full_model_path: str="", torch_compile=False, device="cuda"):

    if model_name not in ('nunchaku-qwen'):
        return None

    set_hf_cache_dir(cache_dir)

    if full_model_path != "":
        return load_qwen_pipeline(full_model_path, cache_dir, torch_compile, device)

    if base_model_path == "":
        base_model_path = "nunchaku-ai/nunchaku-qwen-image-edit-2509/lightning-251115"

    model_path = f"{base_model_path}/svdq-{model_precision}_r{model_rank}-qwen-image-edit-2509-lightning-{model_inference_steps}steps-251115.safetensors"

    return load_qwen_pipeline(model_path, cache_dir, torch_compile, device)

def load_qwen_pipeline(model_path: str, cache_dir: str, torch_compile=False, device="cuda"):
    print(f"Loading SVDQuant FP4 transformer from: {model_path}")

    import torch
    # Nunchaku (SVDQuant transformer)
    from nunchaku.models import NunchakuQwenImageTransformer2DModel

    # Hugging Face
    from diffusers import (
        QwenImageEditPlusPipeline,
        FlowMatchEulerDiscreteScheduler,
    )

    # Global CUDA flags
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    torch.set_float32_matmul_precision("high")

    # SDPA flags (necessari per Flash2)
    torch.backends.cuda.enable_flash_sdp(True)
    torch.backends.cuda.enable_mem_efficient_sdp(True)
    torch.backends.cuda.enable_math_sdp(False)

    # 1. Setup Scheduler exactly as the sample code does
    scheduler_config = {
        "base_image_seq_len": 256,
        "base_shift": math.log(3),
        "num_train_timesteps": 1000,
        "shift": 1.0,
        "use_dynamic_shifting": True,
    }
    scheduler = FlowMatchEulerDiscreteScheduler.from_config(scheduler_config)

    # 2. Initialize the Transformer from your local FP4 file
    transformer = NunchakuQwenImageTransformer2DModel.from_pretrained(
        model_path,
        torch_dtype=torch.bfloat16,
        device=device,
    )

    # 3. Load the Pipeline
    # This will automatically download the correct VAE and VL Encoder
    # from Hugging Face and plug in your local transformer.
    pipe = QwenImageEditPlusPipeline.from_pretrained(
        "Qwen/Qwen-Image-Edit-2509",
        transformer=transformer,
        scheduler=scheduler,
        torch_dtype=torch.bfloat16,
    )

    # 4. VRAM Optimization for 16GB (RTX 5070 Ti)
    # The sample uses a custom offload if memory is low
    if torch.cuda.get_device_properties(0).total_memory / (1024 ** 3) < 18:
        print("Optimizing VRAM for 16GB card...")
        transformer.set_offload(True, use_pin_memory=True, num_blocks_on_gpu=1)
        pipe._exclude_from_cpu_offload.append("transformer")
        pipe.enable_sequential_cpu_offload()
    else:
        pipe.enable_model_cpu_offload()

    if torch_compile:
        pipe.transformer = torch.compile(pipe.transformer, fullgraph=False, dynamic=False)

    return pipe


# ----------------------------
# Image Processing Utilities
# ----------------------------

def upscale_with_lanczos(image, target_size):
    return image.resize(target_size, Image.Resampling.LANCZOS)

def resize_long_side(img: Image.Image, dim: int = 1024) -> Image.Image:
    w, h = img.size
    max_size = max(w, h)
    if max_size < dim:
        return img  # no resize is needed
    ratio = dim / max_size
    new_w = int(w * ratio)
    new_h = int(h * ratio)
    new_w = new_w if new_w % 2 == 0 else new_w + 1
    new_h = new_h if new_h % 2 == 0 else new_h + 1
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)

def colorize_image(pipe, img: Image, prompt:str, steps: int = 2, seed: int=42) -> Image:
    import torch
    generator = torch.Generator(device="cuda").manual_seed(seed)
    with torch.inference_mode():
        output = pipe(
            image=img,
            prompt=prompt,
            num_inference_steps=steps,  # Optimized for lightning model
            true_cfg_scale=1.0,
            generator=generator,
        )
    img_out = output.images[0]
    return img_out

def is_image_dark(img: Image, threshold: int = 20):
    """
    Returns True if the image is totally black or very dark.

    :param img      : image.
    :param threshold: Average pixel intensity below which image is considered "dark".
                      0 = completely black, 255 = completely white (for grayscale).
                      For RGB, average across channels.
    """
    # Convert to grayscale to simplify brightness assessment
    grayscale = img.convert('L')
    stat = ImageStat.Stat(grayscale)
    avg_brightness = stat.mean[0]  # Mean of grayscale channel
    return avg_brightness < threshold

def merge_two_images_with_gap(img1: Image.Image, img2: Image.Image, gap_px: int = 16) -> Image.Image:
    """Merge two same-height images with neutral gray gap."""
    w1, h1 = img1.size
    w2, h2 = img2.size
    assert h1 == h2, "Images must have the same height"
    total_width = w1 + gap_px + w2
    merged = Image.new("RGB", (total_width, h1), (127, 127, 127))
    merged.paste(img1, (0, 0))
    merged.paste(img2, (w1 + gap_px, 0))
    return merged

def split_merged_output(colorized_merged: Image.Image, width1: int, gap_px: int = 16) -> tuple[Image.Image, Image.Image]:
    """Split merged output back into two images."""
    total_w, h = colorized_merged.size
    left = colorized_merged.crop((0, 0, width1, h))
    right = colorized_merged.crop((width1 + gap_px, 0, total_w, h))
    return left, right

def process_image(input_path, output_path, pipe, prompt: str = None, img_size:int = 0, steps: int = 2, log_fn=None) -> float:

    if output_path.exists():
        if log_fn is not None:
            log_fn(f'ℹ️ Image: "{output_path}" already colorized')
        return 0

    original = Image.open(input_path).convert("RGB")

    if is_image_dark(original, threshold=9):
        if log_fn is not None:
            log_fn(f'⚠️ Image: "{input_path}" too dark to be colorized')
        return 0

    t_elapsed = process_image_standard(pipe, original, output_path, prompt, img_size=img_size, steps=steps)

    if log_fn is not None:
        log_fn(f"✅ colored: {output_path} [{t_elapsed:.2f} sec.]")

    return t_elapsed

def process_single_image(pipe, img_path: Path, output_dir: Path, prompt: str) -> float:
    """Fallback for odd-numbered batches."""
    out_path = output_dir / (img_path.stem + ".jpg")
    original = Image.open(img_path).convert("RGB")

    if is_image_dark(original, threshold=9):
        return 0

    return process_image_standard(pipe, original, out_path, prompt)

def process_image_standard(pipe, original, output_path, prompt, img_size: int = 1024, steps: int = 2) -> float:

    bw = ImageEnhance.Color(original).enhance(0.0)
    orig_size = original.size

    if img_size == 0:
        bw_lowres = bw
    else:
        bw_lowres = resize_long_side(bw, img_size)

    t_start = time.perf_counter()
    colorized_lowres = colorize_image(pipe, bw_lowres, prompt, steps)
    t_end = time.perf_counter()

    colorized_upscaled = upscale_with_lanczos(colorized_lowres, orig_size)
    colorized_upscaled.save(output_path)

    return t_end - t_start

# ----------------------------
# Pair Processing
# ----------------------------
def process_image_pair(pipe, img1_path: Path, img2_path: Path, output_dir: Path, prompt: str, gap_px=16) -> float:
    # Load originals
    orig1 = Image.open(img1_path).convert("RGB")
    orig2 = Image.open(img2_path).convert("RGB")
    orig_size1 = orig1.size
    orig_size2 = orig2.size

    # set output path, save as JPG
    out1 = output_dir / (img1_path.stem + ".jpg")
    out2 = output_dir / (img2_path.stem + ".jpg")

    # set flags dark
    orig1_dark = is_image_dark(orig1, threshold=9)
    orig2_dark = is_image_dark(orig2, threshold=9)

    if orig1_dark and orig2_dark:
        return 0

    if orig1_dark:
        return process_image_standard(pipe, orig2, out2, prompt)

    if orig2_dark:
        return process_image_standard(pipe, orig1, out1, prompt)

    # Convert to B&W
    bw1 = ImageEnhance.Color(orig1).enhance(0.0)
    bw2 = ImageEnhance.Color(orig2).enhance(0.0)

    # Resize to 1024px long side
    lowres1 = resize_long_side(bw1, 1024)
    lowres2 = resize_long_side(bw2, 1024)
    #lowres1 = bw1
    #lowres2 = bw2

    # Ensure same height
    if lowres1.height != lowres2.height:
        target_h = max(lowres1.height, lowres2.height)
        lowres1 = ImageOps.pad(lowres1, (lowres1.width, target_h), color=(127, 127, 127))
        lowres2 = ImageOps.pad(lowres2, (lowres2.width, target_h), color=(127, 127, 127))

    # Merge with gap
    merged_input = merge_two_images_with_gap(lowres1, lowres2, gap_px=gap_px)

    # Single inference
    t_start = time.perf_counter()
    colorized_merged = colorize_image(pipe, merged_input, prompt)
    t_end = time.perf_counter()

    resized_colorized_merged = upscale_with_lanczos(colorized_merged, merged_input.size)

    # Split output
    left_img, right_img = split_merged_output(resized_colorized_merged, lowres1.width, gap_px=gap_px)

    # Upscale to original sizes
    left_final = upscale_with_lanczos(left_img, orig_size1)
    right_final = upscale_with_lanczos(right_img, orig_size2)

    # save images as JPG
    left_final.save(out1)
    right_final.save(out2)

    return t_end - t_start


# ----------------------------
# Main Execution
# ----------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_dir", default="./clips/casablanca/ref_tht10")
    parser.add_argument("--output_dir", default="./clips/casablanca/ref_qwen")
    parser.add_argument("--model_path",
                        default="./models/svdq-fp4_r128-qwen-image-edit-2509-lightning-4steps-251115.safetensors")
    parser.add_argument("--cache_dir", default="./hf_cache")
    parser.add_argument('--keep_ext', action='store_true', help='keep the input image format, otherwise is used the jpg format' )
    parser.add_argument("--prompt", default="Colorize this photo, natural skin tones, vibrant environment. Maintain consistency and details.")
    args = parser.parse_args()

    Path(args.output_dir).mkdir(exist_ok=True, parents=True)

    pipe = load_nunchaku_pipeline(
        full_model_path=args.model_path,
        cache_dir=args.cache_dir
    )
    keep_ext : bool = args.keep_ext
    tot_time = 0
    count = 0
    extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}
    for img_file in sorted(Path(args.input_dir).iterdir()):
        if img_file.suffix.lower() in extensions:
            if keep_ext:
                out_file = Path(args.output_dir) / img_file
            else:
                out_file = Path(args.output_dir) / (img_file.stem + ".jpg")
            try:
                count += 1
                t_elapsed = process_image(img_file, out_file, pipe, args.prompt)
                print(f"✅ {count}) {img_file} → {out_file} [{t_elapsed:.2f} sec.]")
                tot_time += t_elapsed
            except Exception as e:
                print(f"❌ Failed on {img_file.name}: {e}")
    print(f"✅ Colorized {count} images at average speed of {tot_time / count:.4f} image/sec.")

if __name__ == "__main__":
    main()
