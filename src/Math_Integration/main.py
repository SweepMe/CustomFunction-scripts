# author: Axel Fischer (sweep-me.net)
# started: 13.10.18

import numpy as np
import os
import pathlib
import math


class Main():
    
    # please defines variables and units as returned by the function 'main'
    variables = ["Integration x"]
    units = [""]

    def __init__(self):
        self.valx = None
        self.xlast = None
       
    # the function 'main' will be loaded as function
    def main(
                self,
                x = (), # y value
                offsetx = 0.0, # x value
                factorx = 1.0,
            ): # angry? If you find a bug or need support for another type, please contact us
           
        # just right at the start of the function, you set the help text which will be displayed as description in the GUI           
        ''' 
        <h2>Integration</h2>
        <br>
        Sums all input values x and starts with offset<br>
        '''
        
        if self.valx == None:
            self.valx = offsetx
                      
        if len(x) > 1:
            diff = np.sum(x)
            
        else:
            if not np.isnan(x[0]):
                self.valx += x[0] * factorx

                # if ylast != None:
                
                # if (x[0] - xlast) != 0:
                    # diff = (y[0] - ylast) / (x[0] - xlast)
                # else:
                    # diff = float('nan')
                # else:
                    # diff = float('nan')

                self.xlast = x[-1]
                
        # return values according to 'variables' and 'units' defined at the beginning of this file
        return self.valx
        
