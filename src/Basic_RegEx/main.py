# author: Axel Fischer
# created at: 27.04.2019
# company/institute: sweep-me.net

import re

class Main():

    # please define variables and units as returned by the function 'main'
    variables = ["Match"]
    units = [""]

    # the function 'main' will be loaded as the function that can be seen inside the module
    # the arguments of the function tell SweepMe! which kind of data you expect and what are the default values
    # SweepMe! will generate the input of the graphical user interface accordingly
    def main(   
            self,           
            # must the first argument and should not be removed
            
            String_to_evaluate = (), 
            # a tuple let you choose from all available SweepMe! values from a ComboBox
            
            Search_pattern = "", 
            # an integer let you insert an integer
                        
            #Return_type = ["String", "Integer", "Float"], 
            # A list of strings let you choose one of the items in a ComboBox
                           
            ): # angry? If you find a bug or need support, please write to support@sweep-me.net
            
            
        ''' 
        <h2>Regular expression</h2>
        Search for a sequence of characters in a string using regular expressions<br>
        
        <h4>Usage:</h4>
        Use as 'String_to_evaluate' a variable that contains a string.<br>
        Use as 'Search_pattern' a regular expression pattern.<br>
        The function returns the first match, otherwise not-a-number (nan).<br>
        If possible the result is automatically converted to an integer or a float.<br>
        The function is based on the re module of python.
        <br>
        <h4>Examples:</h4>
        The pattern 'W=([-+]?\d+.d+)nm_' finds a positive or negative float in the string "...W=340.12nm_..." and will return '340.0' as float.<br>
        The pattern 'W=([-+]?\[0-9]+.[0-9]+)nm_' does the same than the previous example.<br>
        The pattern 'W=(\d+)nm_' finds a positive integer in the string "...W=340nm_..." and will return '340' as int.<br>
        The pattern '([A-Z])=' finds a capital letter in the string "...W=340nm_..." and will return 'W' as string.<br>
        <br>
        Further help about regular expressions can be found here:<br>
        <a href="https://docs.python.org/3.6/library/re.html">https://docs.python.org/3.6/library/re.html</a>
        '''       
        
        match = re.search(Search_pattern, str(String_to_evaluate[0]))
        
        try:
            result = match.group(1)
            
            try:
                result = int(result)
            except:
                try:
                    result = float(result)
                except:
                    pass
                    
        except:
            result = float('nan')

        
        # ... and return your result according to 'variables' and 'units' defined at the beginning of this file
        return result
    
