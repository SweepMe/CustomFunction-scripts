# author: Axel Fischer (sweep-me.net)
# started: 23.01.19

import os

from PIL import Image

import FolderManager
FoMa = FolderManager.FolderManager()


# please defines variables and units as returned by the function 'main'
variables = ["Path animation"]
units = [""]

# the function 'main' will be loaded as function
def main(
            Pictures = (), # a tuple let you choose SweepMe! values from a ComboBox
            Duration = 0.1,
            #Format = ["gif", "avi"],

        ):

    # just right at the start of the function, you set the help text which will be displayed as description in the GUI
    '''
        <h2>Animation</h2>
        <br>
        create an animation based on a list of files<br>
        select a variable that stores paths to image files<br>
        Duration is the display time of each frame in seconds<br>
    '''

    tempfolder = FoMa.get_path("TEMP")

    # copy each frame into memory so that the file is closed again before opening the next one
    images = []
    for filename in Pictures:
        with Image.open(str(filename)) as image:
            images.append(image.copy())

    animation_path = tempfolder + os.sep + "temp_Animation.gif"

    # Pillow expects the frame duration in milliseconds
    images[0].save(animation_path, save_all=True, append_images=images[1:], duration=int(Duration * 1000), loop=0)

    return [animation_path]

