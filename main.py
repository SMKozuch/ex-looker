"__author__ = 'Samuel Kozuch'"
"__credits__ = 'Keboola 2018'"
"__project__ = 'ex-looker'"

"""
Python 3 environment 
"""

#import pip
#pip.main(['install', '--disable-pip-version-check', '--no-cache-dir', 'logging_gelf'])

import sys
import os
import logging
import json
import pandas as pd
import requests
import re
import logging_gelf.handlers
import logging_gelf.formatters
from keboola import docker



### Environment setup
abspath = os.path.abspath(__file__)
script_path = os.path.dirname(abspath)
os.chdir(script_path)
sys.tracebacklimit = 0

### Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)-8s : [line:%(lineno)3s] %(message)s',
    datefmt="%Y-%m-%d %H:%M:%S")

"""
logger = logging.getLogger()
logging_gelf_handler = logging_gelf.handlers.GELFTCPSocketHandler(
    host=os.getenv('KBC_LOGGER_ADDR'),
    port=int(os.getenv('KBC_LOGGER_PORT'))
    )
logging_gelf_handler.setFormatter(logging_gelf.formatters.GELFFormatter(null_character=True))
logger.addHandler(logging_gelf_handler)

# removes the initial stdout logging
logger.removeHandler(logger.handlers[0])
"""

### Access the supplied rules
cfg = docker.Config('/data/')
params = cfg.get_parameters()
client_id = params['client_id']
client_secret = params['#client_secret']
api_endpoint = params['api_endpoint']
looker_objects = params['looker_objects']

logging.info("Successfully fetched all parameters.")

#logging.debug("Fetched parameters are :" + str(params))

### Get proper list of tables
cfg = docker.Config('/data/')
in_tables = cfg.get_input_tables()
out_tables = cfg.get_expected_output_tables()
logging.info("IN tables mapped: "+str(in_tables))
logging.info("OUT tables mapped: "+str(out_tables))

### destination to fetch and output files
DEFAULT_FILE_INPUT = "/data/in/tables/"
DEFAULT_FILE_DESTINATION = "/data/out/tables/"


def fetch_data(endpoint, id, secret, object_id, limit):
    """
    Function fetching the data from query or looker via API.
    """

    logging.info("Attempting to access API endpoint %s." % endpoint)

    params = {'client_id': id, 
              'client_secret': secret}

    logging.info("Logging in...")
    login = requests.post(api_endpoint + 'login', params=params)

    if login.status_code == 200:
        logging.info("Login to Looker was successful.")
        token = login.json()['access_token']
    else:
        msg1 = "Could not login to Looker. Please check, whether correct"
        msg2 = "credentials and/or endpoint were inputted. Server response: %s" % login.reason
        logging.critical(" ".join([msg1, msg2]))
        sys.exit(1)
    
    head = {'Authorization': 'token %s' % token}
    look_url = endpoint + 'looks/%s/run/json?limit=%s' % (object_id, str(limit))

    logging.info("Attempting to download data for look %s." % object_id)
    data = requests.get(look_url, headers=head)

    if data.status_code == 200:
        logging.info("Data was downloaded successfully.")
        return pd.io.json.json_normalize(data.json())
    else: 
        msg1 = "Data could not be downloaded. Request returned: Error %s %s." % (data.status_code, data.reason)
        msg2 = "For more information, see: %s" % data.json()['documentation_url']
        logging.critical(" ".join([msg1, msg2]))
        sys.exit(1)

def create_manifest(file_name, destination, primary_key, incremental):
    """
    Function for manifest creation.
    """

    file = '/data/out/tables/' + str(file_name) + '.manifest'

    manifest_template = {
                         "destination": str(destination),
                         "incremental": incremental,
                         "primary_key": primary_key
                        }

    manifest = manifest_template

    try:
        with open(file, 'w') as file_out:
            json.dump(manifest, file_out)
            logging.info("Output %s manifest file produced." % file_name)
    except Exception as e:
        logging.warn("Could not produce %s output file manifest." % file_name)
        logging.warn(e)

def fullmatch_re(pattern, string):
    match = re.fullmatch(pattern, string)

    if match:
        return True
    else:
        return False

def main():
    for obj in looker_objects:
        id = obj['id']
        output = obj['output']
        inc = obj['incremental']
        primary_key = obj['primary_key']
        limit = obj['limit']

        pk = [col.strip() for col in primary_key.split(',')]


        bool = fullmatch_re(r'^(in|out)\.(c-)\w*\.[\w\-]*', output)
        
        if bool:
            destination = output
            logging.debug("The table with id {0} will be saved to {1}.".format(id, destination))
        elif bool == False and len(output) == 0:
            destination = "in.c-looker.looker_data_%s" % id
            logging.debug("The table with id {0} will be saved to {1}.".format(id, destination))
        else:
            msg1 = "The name of the table %s contains unsupported chatacters." % output
            msg2 = "Please provide a valid name with bucket and table name."
            logging.critical(" ".join([msg1, msg2]))
            sys.exit(1)

        file_name = 'looker_data_%s.csv' % id
        output_path = DEFAULT_FILE_DESTINATION + file_name

        look_data = fetch_data(api_endpoint, client_id, client_secret, id, limit)
        
        for key in pk:
            if (str(key) in list(look_data) and \
            key != ''):
                logging.info("%s will be used as primary key." % key)
                pk[pk.index(key)] = key.replace('.', '_')
            elif key == '':
                pk.remove(key)
            else:
                msg1 = "%s column is not in table columns. The column will be ommited as primary key." % key
                msg2 = "Available columns to be used as primary key are %s." % str(list(look_data))
                logging.warn(" ".join([msg1, msg2]))
                pk.remove(key)
                
        """
        for col in list(look_data):
            if len(col) > 64:
                logging.critical("%s exceeds 64 character length. Please change the name of the column or alter the look %s." % (col, id))
                sys.exit(1)
        """

        look_data.to_csv(output_path, index=False)
        create_manifest(file_name, destination, pk, inc)

if __name__ == "__main__":
    main()

    logging.info("Script finished.")