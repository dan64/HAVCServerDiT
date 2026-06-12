import sys
import FreeSimpleGUI as sg
from tkinterdnd2 import TkinterDnD, DND_FILES

def on_drop(event):
    window["-FILE-"].update(event.data)

layout = [
    [sg.Text("Drag & Drop a File Here, or Browse")],
    [sg.Input("", key="-FILE-"),
     sg.FileBrowse(file_types=(("Images", "*.png *.jpg *.jpeg *.bmp"),))],
    [sg.Button("OK"), sg.Button("Cancel")],
]

window = sg.Window("File Drop", layout, finalize=True)

# Inject DnD into PySimpleGUI's own root
TkinterDnD.require(window.TKroot)

# Register the input widget as a drop target
window["-FILE-"].widget.drop_target_register(DND_FILES)
window["-FILE-"].widget.dnd_bind("<<Drop>>", on_drop)

selected_path = ""
while True:
    event, values = window.read()
    if event in (sg.WIN_CLOSED, "Cancel"):
        break
    if event == "OK":
        selected_path = values["-FILE-"].strip()
        break

window.close()

# Print the path to stdout so the parent process can read it
print(selected_path)
