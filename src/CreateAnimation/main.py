# author: Axel Fischer (sweep-me.net)
# started: 23.01.19

import numpy as np
import os
import pathlib

import FolderManager
FoMa = FolderManager.FolderManager()
FolderManager.addFolderToPATH()

import imageio


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
    '''
    
    tempfolder = FoMa.get_path("TEMP")
    
    images = []
    for filename in Pictures:
        images.append(imageio.imread(filename))
     
    animation_path = tempfolder + os.sep + "temp_Animation.gif"
    
    imageio.mimsave(animation_path, images, duration = Duration)

    return [animation_path]
    
