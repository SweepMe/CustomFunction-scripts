# author: Axel Fischer (sweep-me.net)
# started: 29.08.18

import numpy as np
import os
import pathlib
import math

# please defines variables and units as returned by the function 'main'
variables = ["Rectification", ""]
units = ["", ""]

# the function 'main' will be loaded as function
def main(
            current = (), # a tuple let you choose SweepMe! values from a ComboBox
            voltage = (),
        ): # angry? If you find a bug or need support for another type, please contact us
        
    # just right at the start of the function, you set the help text which will be displayed as description in the GUI
    ''' 
        <h2>Rectification</h2>
    '''
    
    # do whatever you want 
    print("Output of Evaluation example function:")
    print("data:", current)
    
    # return values according to 'variables' and 'units' defined at the beginning of this file
    return [abs(current.max()/current.min()), ""]
    
