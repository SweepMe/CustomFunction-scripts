# author: Axel Fischer
# created at: 07.05.2019
# company/institute: sweep-me.net

import os

class Main():

    # please define variables and units as returned by the function 'main'
    variables = ["Folder", "File name", "File extension", "File exists"]
    units = ["", "", "", ""]

    # the function 'main' will be loaded as the function that can be seen inside the module
    # the arguments of the function tell SweepMe! which kind of data you expect and what are the default values
    # SweepMe! will generate the input of the graphical user interface accordingly
    def main(   
            self,           
            # must the first argument and should not be removed
            
            Path_to_evaluate = (), 
            # a tuple let you choose from all available SweepMe! values from a ComboBox
            
                           
            ): # angry? If you find a bug or need support, please write to support@sweep-me.net
            
            
        ''' 
        <h2>Path evaluation</h2>
        returns folder, file name, file extension and whether files exists<br>
        ''' 

        existing = os.path.exists(Path_to_evaluate[0])        
        
        if existing:
        
            file_name, ext =  os.path.splitext(Path_to_evaluate[0])
            
            file_name = os.path.basename(file_name)
            
            folder = os.path.dirname(Path_to_evaluate[0])
            

        else:
            
            folder, file_name, ext = False, False, False
            
        
        # ... and return your result according to 'variables' and 'units' defined at the beginning of this file
        return folder, file_name, ext, existing
    
