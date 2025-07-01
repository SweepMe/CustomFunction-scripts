# author: Axel Fischer (sweep-me.net)
# started: 13.10.18

import numpy as np
import os
import pathlib
import math

# please defines variables and units as returned by the function 'main'
variables = ["Gradient"]
units = [""]

global xlast
xlast = None

global ylast
ylast = None


# the function 'main' will be loaded as function
def main(
            x = (), # x value
            y = (), # y value
        ): # angry? If you find a bug or need support for another type, please contact us
        
    # just right at the start of the function, you set the help text which will be displayed as description in the GUI
    ''' 
        <h2>Gradient</h2>
        <br>
        Calculate the gradient of a curve or the two last measurement points<br>
        Arguments are x and y values.<br>
    '''
    
    global xlast
    global ylast
    
    if len(y) > 1:
        diff = np.gradient(y,x)
    else:
        if ylast != None:
            if (x[0] - xlast) != 0:
                diff = (y[0] - ylast) / (x[0] - xlast)
            else:
                diff = float('nan')
        else:
            diff = float('nan')
            
        ylast = y[-1]
        xlast = x[-1]
    
    # return values according to 'variables' and 'units' defined at the beginning of this file
    return diff
    
