# Imports
import vapoursynth as vs
# getting Vapoursynth core
import sys
import os
core = vs.core
# Import scripts
import vscmnet2 as cmnet2
clip = cmnet2.vs_read_video(source=VideoPath)
clip = cmnet2.vs_select_reference_frames(
    ref_framedir=RefDirIn,
    out_framedir=RefDirOut,
    similarity_threshold=float(ScThtSSIM),
    select_window=int(SelectWindow),
    device="cuda",
    dry_run=bool(DryRun),
    debug_html=bool(DebugHtml),
    move_files=bool(MoveFiles),
)
# adjusting output color from RGB24 to YUV420P10 for x265Model
clip = core.resize.Bicubic(clip=clip, format=vs.YUV420P10, matrix_s="709", range_in_s="full", range_s="limited") # additional resize to match target color sampling
# output
clip.set_output()
