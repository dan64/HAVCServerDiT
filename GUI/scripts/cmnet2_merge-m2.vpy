# Imports
import vapoursynth as vs
# getting Vapoursynth core
import sys
import os
core = vs.core
# Import scripts
import vscmnet2 as cmnet2
clip1 = cmnet2.vs_read_video(source=VideoPath1)
clip2 = cmnet2.vs_read_video(source=VideoPath2)
clip = cmnet2.vs_merge(clipa=clip2, clipb=clip1, clip_luma=clip1, weight=float(Weight), method=2)
# --------------------------------------------------------------------------------------
# adjusting output color from: RGB48 to YUV420P10 for x265Model
clip = core.resize.Bicubic(clip=clip, format=vs.YUV420P10, matrix_s="709", range_s="limited", dither_type="error_diffusion")
# Output
clip.set_output()

