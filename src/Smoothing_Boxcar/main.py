# author: Axel Fischer (sweep-me.net)
# started: 14.08.18

import numpy as np


class Main():

    variables = ["index", "Smoothed signal", "Original data"]
    units = ["", "", ""]

    def main(self, data = (), half_box_size = 1):
        ''' 
            <h2>Boxcar smoothing of a list of values</h2>
            <h3> Arguments:</h3>
            data.. any variable  <br>
            half_box_size.. Additional number of points into each direction <br>
        '''
                    
        extended_data = np.concatenate((np.ones(half_box_size)*data[0],data,np.ones(half_box_size)*data[-1]))
        window = np.ones(2*half_box_size+1)
        smoothed = np.convolve( window/window.sum(), extended_data, mode = 'same' )
        
        return np.arange(len(data)), smoothed[half_box_size:-half_box_size], data