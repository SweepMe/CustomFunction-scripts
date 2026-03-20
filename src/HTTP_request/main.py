# author: Shayan Miri, Axel Fischer
# created at: December 2022 - January 2023
# company/institute: SweepMe! GmbH

import requests

# can be used to disable warnings such as missing SSL certificate
# requests.packages.urllib3.disable_warnings() 

# comes with SweepMe! and simplifies finding the correct path to the certificate
from WebRequestCerts import CERTFILE


class Main():

    """
    This Custom Function script returns two entities: Success (bool) and Status Code (int). If positive response (200)
     is received, the Success will be set to True.
    The Status code on the other hand is the response of the HTTP request, which indicates the status of
    communication, e.g. 200 and 404, which are indicating "Ok" and "Not found", respectively.
    """

    variables = ["Success", "Status code"] 
    units = ["", ""]

    arguments = {
        "Data": (),
        "URL": "https://httpbin.org/post",
        "Content type": ["application/json"],
        "HTTP method": ["POST"],
        "Retries": 5,
        "Timeout": .2,
        "Stop on error": False,   
    }

    def main(self, **kwargs):
        
        i = 0
        data = str(kwargs["Data"][-1]) if kwargs["Data"] else ""
        retries = kwargs["Retries"]
        timeout = kwargs["Timeout"]
        url = kwargs["URL"]
        content_type = kwargs["Content type"]
        http_method = kwargs["HTTP method"]
        stop_on_error = kwargs["Stop on error"]
        status_code = None
        success = False
        error_message = ""
        response_text = ""
        
        if http_method == "POST":
            while True:
                i += 1
                try:
                    headers = {'Content-type': content_type}
                    # response = requests.post(url, data=data, timeout=timeout, headers=headers, verify=False)  # needed if SSL certificates fail
                    response = requests.post(url, data=data, timeout=timeout, headers=headers, verify=CERTFILE)
                    response_text = response.text
                    response.raise_for_status()
                    if response.status_code == 200:
                        status_code = 200
                        success = True
                        break
        
                except requests.exceptions.RequestException as err:
                    error_message = err
                    
                if i == retries:
                    break

        if not success:

            if error_message != "":
                print(f'HTTP request error: {error_message}')
                
            if response_text != "":    
                print("Last HTTP response:", response_text)
                
            if stop_on_error:
                raise Exception(f'HTTP request error: see response above')
         
            print("HTTP request:", success, status_code)
            print("Sent data:", data)
           
        return success, status_code
