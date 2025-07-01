# author: Axel Fischer (sweep-me.net)
# started: 22.07.18

import scipy.signal
import numpy as np

class Main():

    variables = ["Numbers", "Input data", "Smoothed signal"]
    units = ["", "", ""]

    def main(self, x=(), window_length = 5, polyorder = 1, deriv=0, delta=1.0, mode=['mirror', 'constant', 'nearest', 'wrap', 'interp'], cval=0.0):
        ''' 
            Savitzky-Golay Filter<br>
            Please find all details here:<br>
            <a href="https://docs.scipy.org/doc/scipy-0.16.1/reference/generated/scipy.signal.savgol_filter.html">https://docs.scipy.org/doc/scipy-0.16.1/reference/generated/scipy.signal.savgol_filter.html</a>
        '''
        axis = -1
        smoothed_list = scipy.signal.savgol_filter(x, window_length, polyorder, deriv, delta, axis, mode, cval)
        
        return np.arange(len(x)), x, smoothed_list
    
