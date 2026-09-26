# Imports
import vapoursynth as vs
# getting Vapoursynth core
import sys
import os
core = vs.core
# Import scripts
import vscmnet2 as cmnet2
clip = cmnet2.vs_read_video(source=VideoPath)
# adding colors using HAVC
clip = cmnet2.vs_cmnet2(clip, method=4, sc_framedir=RefDir, render_speed=RenderSpeed, max_memory_frames=int(MemoryFrames), ref_mode=0, backbone=Backbone)
# adjusting output color from RGB24 to YUV420, bit depth selected by the caller (10 for x265/NVEnc, 8 for x264)
out_format = vs.YUV420P10 if int(BitDepth) == 10 else vs.YUV420P8
clip = core.resize.Bicubic(clip=clip, format=out_format, matrix_s="709", range_in_s="full", range_s="limited", dither_type="error_diffusion")
# output
clip.set_output()


