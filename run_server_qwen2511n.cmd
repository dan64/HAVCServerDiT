@echo off
:: run_server_qwen2511n.cmd : launch the server with Qwen-Image-Edit 2511 on
:: the ComfyUI-nunchaku node (QuantFunc SVDQuant FP4 + Lightning LoRA)
call "%~dp0start_server.cmd" qwen-2511-nunchaku_fp4
