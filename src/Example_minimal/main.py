# author:
# created at:
# company/institute:

class Main():

    """
    <h2>Minimal working example</h2>
    
    No returned variables, and no arguments are defined.
    
    Use this example as the base for a new CustomFunction script
    defined from scratch
    
    """

    # please define variables and units as returned by the function 'main'
    variables = []
    units = []
    # add your arguments by defining keys and default values in the dictionary below
    arguments = {}

    def main(self, **kwargs):
        print("Arguments:", kwargs)
            
    
if __name__ == "__main__":

    script = Main()

    arguments = {}

    # handing over the dictionary 'arguments' to be used like keyword arguments
    values = script.main(**arguments)
    print("Returned values:", values)

    print("CustomFunction script 'Example_minimal' finished.")
