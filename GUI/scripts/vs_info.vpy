# Imports
import vapoursynth as vs
# Import scripts
import vscmnet2 as cmnet2
clip = cmnet2.vs_read_video(source=VideoPath, return_rgb=False)
# output
clip.set_output()

