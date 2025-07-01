# author:
# created at:
# company/institute:

import ctypes


# 0 -> Ok (1)
# 1 -> Ok (1), Cancel (2)
# 2 -> Cancel (3), Retry (4), Ignore (5)
# 3 -> Yes (6), No (7), Cancel (2)
# 4 -> Yes (6), No (7)
# 5 -> Retry(4), Cancel(2)
# 6 -> Cancel(2), Retry (10), Continue(11)

message_types = {
            "Ok (1)" : 0,
            "Ok (1), Cancel (2)" : 1,
            "Cancel (3), Retry (4), Ignore (5)" : 2,
            "Yes (6), No (7), Cancel (2)" :  3,
            "Yes (6), No (7)" : 4,
            "Retry(4), Cancel(2)" : 5,
            "Cancel(2), Retry (10), Continue(11)" : 6, 
        }
        
        
return_values = {
                1 : "Ok",
                2 : "Cancel",
                3 : "Cancel",
                4 : "Retry",
                5 : "Ignore",
                6 : "Yes",
                7 : "No",
                10: "Retry",
                11: "Continue"
                }

class Main():

    # please define variables and units as returned by the function 'main'
    variables = ["Return value", "Button text"]
    units = ["", ""]


    # the function 'main' will be loaded as the function that can be seen inside the module
    # the arguments of the function tell SweepMe! which kind of data you expect and what are the default values
    # SweepMe! will generate the input of the graphical user interface accordingly
    def main(   
            self, # must the first argument and should not be removed
            Type = list(message_types.keys()),
            Title = "Demo",
            Text = "I am the text of the message box. Please change me!",
        ): # angry? If you find a bug or need support for another data type, please write to support@sweep-me.net
            
             
        # just at the start of your function, you can set a help text which will be displayed as description in the GUI.
        ''' 
        <h4>Description</h4>
        <p>This function makes use of Windows User32 library to create different message boxes. There are different types and depending on the clicked button different values are returned. Please find a list of possible types and their return values in brackets below. All message boxes are blocking and the user has to press one of the buttons to continue. To customize the message box, you can change title and text that are supporting unicode characters as well.<br /><br /><br /><strong>Type and return values:</strong></p>
        <ul>
        <li>Ok (1)</li>
        <li>Ok (1), Cancel (2)</li>
        <li>Cancel (3), Retry (4), Ignore (5)</li>
        <li>Yes (6), No (7), Cancel (2)</li>
        <li>Yes (6), No (7)</li>
        <li>Retry(4), Cancel(2)</li>
        <li>Cancel(2), Retry (10), Continue(11)</li>
        </ul>
        '''

        message_type = message_types[Type]

        msgbox = ctypes.windll.user32.MessageBoxW
        ret = msgbox(None, Text, Title, message_type)
        
        # 0 -> Ok (1)
        # 1 -> Ok (1), Cancel (2)
        # 2 -> Cancel (3), Retry (4), Ignore (5)
        # 3 -> Yes (6), No (7), Cancel (2)
        # 4 -> Yes (6), No (7)
        # 5 -> Retry(4), Cancel(2)
        # 6 -> Cancel(2), Retry (10), Continue(11)
        
        # print(ret, return_values[ret])

        return ret, return_values[ret]
    
