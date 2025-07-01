# author:
# created at:
# company/institute:

class Main():

    """
    This example shows how to define arguments using the static attribute 'arguments'.
    This way the number of arguments can be changed.
    To receive an unknown number of arguments, take Option4 that uses **kwargs.
    Then kwargs is nothing else than an ordinary dictionary where you find for each argument key
    the corresponding value.
    """

    arguments = {"Number argument": 1, "String argument": "2", "Boolean argument": True}
    variables = ["Variable1", "Variable 2"]
    units = ["unit1", "unit2"]

    # The following options are just for comparison between the old style
    # and the new style to define arguments
    # Please use Option4 and remove the other ones.
   
    # Option1: the old style of defining arguments
    # def main(self, first=1, second="2", third=True):  
        # print(first, second, third)
        # return first, second, third
   
    # Option2: the old style but without defaults here 
    # def main(self, first, second, third):  
        # print(first, second, third)
        # return first, second, third
        
    # Option3: DOES NOT WORK, receiving an arbitrary number of arguments via args 
    # def main(self, *args):  
        # print(args)
        # return args
        
    # Option4: receiving an arbitrary number of arguments via kwargs
    def main(self, **kwargs):
        print("Arguments:", kwargs)

        # Just an example how to process the arguments and return it
        var1 = kwargs["Number argument"] * 2.0
        var2 = kwargs["String argument"] + "_returned"
        return var1, var2


if __name__ == "__main__":

    # This part of the code only runs if this file is directly run with python
    # You need to install pysweepme to make the import section work, 
    # use command line with "pip install pysweepme"
    
    script = Main()

    arguments = {
        "first": 2, 
        "second": "3", 
        "third": False,
        }

    # handing over the dictionary 'arguments' to be used like keyword arguments
    values = script.main(**arguments)  
    
    print("Returned values:", values)

    print("CustomFunction script 'Example_keyword_arguments' finished.")