# author:
# created at:
# company/institute:



# you can import all packages that come with SweepMe!
import numpy as np
import os
import pathlib
import math

# you can import any module that is shipped with SweepMe!, see credits.html
# Any other module must be put into the folder of your function and loaded by 
# adding the path the python environment using the following two lines:
from pysweepme import FolderManager as FoMa
FoMa.addFolderToPATH()


class Main():

    # just at the start of your class, you can set a help text which will be displayed as description in the GUI.
    ''' 
    <h2>Example function</h2>
    An exemplary function to show the basic possibilities of the CustomFunction module.<br />
    You can see the output of this function in the Debug widget.<br />
    <br /> 
    Learn more here:<br /> 
    <a href="https://wiki.sweep-me.net/wiki/CustomFunction">https://wiki.sweep-me.net/wiki/CustomFunction</a> <br />
    <br /> 
    You can use HTML tags:<br /> 
    <strong>bold</strong><br /> 
    <em>italic</em><br /> 
    We recommend to use an online HTML editor (e.g. <a href="https://html5-editor.net/">https://html5-editor.net/</a>) to create such decriptions easily.
    <p><strong>Possible data types:</strong></p>
    <ul>
    <li>Tuple () -&gt; User can select a measurement value of SweepMe!.</li>
    <li>Float -&gt; User can enter a float value.</li>
    <li>Integer -&gt; User can enter an integer value.</li>
    <li>String -&gt; User can enter a string</li>
    <li>Bool -&gt; User can set True or False using a CheckBox.</li>
    <li>List -&gt; User can select one item of the list in a ComboBox.</li>
    <li>Pathlib path object with directory -&gt; User can select a directory.</li>
    <li>Pathlib path object with file-&gt; User can select a file.</li>
    </ul>
    <p>If further types are needed, please contact us, e.g. write to support@sweep-me.net</p>
    '''

    # please define variables and units as returned by the function 'main'
    variables = ["Data", "Variable 1", "Variable 2"]
    units = ["", "unit1", "unit2"]

    # here we can define the arguments presented in the user interface that are later handed over to function 'main'
    # the keys are the argument names, the values are the default values for the user interface
    arguments = {"Test data": (),  # a tuple let you choose from all available SweepMe! values from a ComboBox
                 # Caution: please note that test_data will be a numpy array of values,
                 # even if the data contains just one value
                "Test integer": 42,  # an integer let you insert an integer
                "Test float": math.pi,  # a float let you insert an float
                "Test boolean": True,  # a bool let you choose between True and False from a ComboBox
                "Test selection": ["Choice1", "Choice2"],  # A list of strings let you choose one of the items in a ComboBox
                "Test string": "A text you can modify",  # a string let you enter a string
                "Test directory path": pathlib.Path("."),  # a pathlib.Path() object with a path to a directory let you
                 # press a button to open a QFileDialog to select another directory
                "Test file path": pathlib.Path("." + os.sep + "debug.log"),  # a pathlib.Path() object with a path to
                 # a file let you press a button to open a QFileDialog to select another file, e.g. to load a certain calibration or setting file
    }
    
    def prepare_run(self):
        """
        This function is called at the beginning before the measurement thread is started.
        Thus, this function runs in the GUI thread of SweepMe!.
        """
        print("prepare_run")
        
    def prepare_stop(self):
        """
        This function is called at the end after the measurement thread is finished.
        Thus, this function runs in the GUI thread of SweepMe!.
        """
        print("prepare_stop")
        
    def connect(self):
        """
        This functions is called at the start of the measurement.
        """
        print("connect")
        
    def disconnect(self):
        """
        This functions is called at the end of the measurement.
        """
        print("disconnect")
        
    def initialize(self):
        """
        This functions is called at the start of the measurement.
        """
        print("initialize")
        
        print("Arguments entered or selected by the user:")
        print(self.main_arguments)  # early access to the arguments
        
    def deinitialize(self):
        """
        This functions is called at the end of the measurement.
        """
        print("deinitialize")
        
    def configure(self):
        """
        This functions is called when the CustomFunction module gets part of an active branch.
        """
        print("configure")
        
    def unconfigure(self):
        """
        This functions is called when the CustomFunction module is no more part of an active branch.
        """
        print("unconfigure")
        
    def signin(self):
        """
        This functions is called when a module above CustomFunction does a further iteration step.
        """
        print("signin")
        
    def signout(self):
        """
        This functions is called when a module above CustomFunction ends with the iteration step.
        """
        print("signout")

    def main(self, **kwargs):
        """
        This function is called in the measurement thread at the 'process' step of the drivers.
        i.e. after measurement data has been returned.
        It gets the arguments as a dictionary as defined by the static attribute 'arguments'
        """

        print("Keyword arguments:\n", kwargs)

        test_data = kwargs["Test data"]
        test_int = kwargs["Test integer"]
        test_float = kwargs["Test float"]
        test_bool = kwargs["Test boolean"]
        test_selection = kwargs["Test selection"]
        test_string = kwargs["Test string"]
        test_directory = kwargs["Test directory path"]
        test_file = kwargs["Test file path"]
             
        # now do whatever you want ...
        # here, the values of the arguments are simply printed to show the user selection
        print()
        print("Output of CustomFunction example function:")
        
        print("data:", test_data) # Caution: Please note that test_data is always an array of values, even if it contains just one element
        print("data type:", type(test_data)) # Caution: Please note that test_data is always an array of values, even if it contains just one element
        print("data, last element:", test_data[-1]) # Caution: Please note that test_data is always an array of values, even if it contains just one element
        
        if test_data[-1] is None:
            print("Please, select a key for 'test_data' to hand it over to this function")
        else:
            print("data, flattened:", test_data.flatten()) # Caution: Please note that test_data is always an array of values, even if it contains just one element
        
        print("int:", test_int)
        print("float:", test_float)
        print("bool:", test_bool)
        print("selection:", test_selection)
        print("string:", test_string)
        print("path directory:", repr(test_directory), str(test_directory))  # It is a Pathlib object that can be easily converted to string
        print("path file:", repr(test_file), str(test_file))  # It is a Pathlib object that can be easily converted to string 
        print()
        
        
        # ... and return your result according to 'variables' and 'units' defined at the beginning of this file
        return test_data[-1], test_int, test_float
    

if __name__ == "__main__":

    # This part of the code only runs if this file is directly run with python
    # You need to install pysweepme to make the import section work, 
    # use command line with "pip install pysweepme"
    
    script = Main()

    arguments = {
        "Test data": np.array([1,3,5]),
        "Test integer": 11,
        "Test float": math.pi/2.0,
        "Test boolean": False,
        "Test selection": "Choice2",
        "Test string": "Some text that is different from the default",
        "Test directory path":  pathlib.Path("C:"),  
        "Test file path": pathlib.Path("." + os.sep + "debug.log"),
        }

    # not really needed, just to show one can call also other functions than main
    script.connect()
    
    # handing over the dictionary 'arguments' to be used like keyword arguments
    values = script.main(**arguments)  
    
    print("Returned values:", values)
    
    # not really needed, just to show one can call also other functions than main
    script.disconnect()
    
    print("CustomFunction script 'Example' finished.")