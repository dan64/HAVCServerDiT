# Imports
import vapoursynth as vs
# getting Vapoursynth core
import sys
import os
core = vs.core
# Import scripts
import vscmnet2 as cmnet2
clip = cmnet2.vs_read_video(source=VideoPath)
clip = cmnet2.vs_extract_reference_frames(clip, sc_threshold=float(ScThreshold), sc_tht_ssim=float(ScThtSSIM), sc_tht_offset=2, sc_min_int=int(SCMinINT), sc_min_freq=int(ScMultTht), sc_tht_white=0.70, sc_tht_black=0.09,  sc_framedir=RefDir, sc_algo=1, ref_ext="jpg", ref_jpg_quality=95, ref_override=bool(RefOverride), sc_debug=False)
# adjusting output color from RGB24 to YUV420P10 for x265Model
clip = core.resize.Bicubic(clip=clip, format=vs.YUV420P10, matrix_s="709", range_in_s="full", range_s="limited") # additional resize to match target color sampling
# output
clip.set_output(
)

