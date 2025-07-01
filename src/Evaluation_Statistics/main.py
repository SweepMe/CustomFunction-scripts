# author: Axel Fischer (axel.fischer@sweep-me.net)
# company/institution: SweepMe! GmbH
# started: 04.10.18
# revised: 25.01.23

import numpy as np


class Main():

    """ 
    <h2>Simple statistics</h2>
    
    calculates
    <ul>
    <li>mean</li>
    <li>standard deviation</li>
    <li>median</li>
    <li>minimum</li>
    <li>maximum</li>
    </ul>
    
    of a list of values.
    
    </h3>Parameters</h3>
    <ul>
    <li>Data: a list or array of values, or single values, e.g int or float
    <li>Append: concatenate new values to previous values.</li>
    <li>Last points: Only keep the given number of points. If empty, all points are used.</li>
    </ul>
    """

    variables = ["Mean", "Standard deviation", "Median", "Min", "Max"]
    units = ["", "", "", "", ""]
    arguments = {
        "Data": (),
        "Append": False,
        "Last points": "",
        }
        
    def configure(self):
        self.data_all = np.array([])
    
    def main(self, **kwargs):
    
        # Handing over arguments
        new_data = kwargs["Data"]
        new_data = new_data[np.isfinite(np.array(new_data).flatten())]
        use_append = kwargs["Append"]
        last_points = kwargs["Last points"].strip()
        
        # Preprocessing data
        if last_points == "":
            last_points_index = 0  # all points
        else:
            last_points_index = -int(last_points)
 
        if use_append:    
            self.data_all = np.concatenate((self.data_all, new_data))
            data = self.data_all[last_points_index:]
        else:
            data = new_data[last_points_index:]
            
        # Statistical evaluation
        average = np.mean(data)
        std = np.std(data)
        median = np.median(data)
        minimum = min(data)
        maximum = max(data)
        
        return [average, std, median, minimum, maximum]
        