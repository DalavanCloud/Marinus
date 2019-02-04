#!/usr/bin/python3

# Copyright 2018 Adobe. All rights reserved.
# This file is licensed to you under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License. You may obtain a copy
# of the License at http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under
# the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR REPRESENTATIONS
# OF ANY KIND, either express or implied. See the License for the specific language
# governing permissions and limitations under the License.

"""
This script queries Infoblox for all its DNS Zone records.

This verify=False is set because the Infoblox SSL configuration is lower than what Python accepts.
This script tries to re-issue failed requests because Infoblox is consistently flaky.
This script sleeps a lot to reduce the flakiness.
The search is based on an alphabet because Infoblox limits the number of values it can return.

This script should be the first Infoblox script executed and only takes about two minutes.

This script is only useful to Infoblox customers.
"""


import re
from datetime import datetime
import requests
import string
import backoff
from requests.auth import HTTPBasicAuth
from libs3 import MongoConnector, ZoneIngestor, InfobloxHelper, APIHelper


class InfobloxZone(object):
    alphabets = list(string.ascii_lowercase + string.digits)
    alphabet_queried = None
    APIH = APIHelper.APIHelper()
    IH = InfobloxHelper.InfobloxHelper()

    # Connect to the database
    MC = MongoConnector.MongoConnector()
    jobs_collection = MC.get_jobs_connection()
    zone_collection = MC.get_zone_connection()
    ip_collection = MC.get_ipzone_connection()

    ZI = ZoneIngestor.ZoneIngestor()

    next_page_id = None
    source = 'Infoblox'

    def __get_base_url(self):
        """
        Returns the Infoblox zone API URL
        :return: Infoblox zone API URL
        """
        return 'https://' + self.IH.IBLOX_HOST + '/wapi/v' + self.IH.IBLOX_VERSION + '/zone_auth'

    def __get_previous_zones(self):
        """
        Fetches the currently present zones/sub-zones in the zone collection with source 'Infoblox'.
        The result is a dictionary with the zones as keys. The value of the key is True if the zone
        is sub_zone.
        """
        zones = self.zone_collection.find({'$or': [{'reporting_sources.source': self.source},
                                                   {'sub_zones.source': self.source}]},
                                          {'reporting_sources': 1,
                                           'zone': 1,
                                           'sub_zones': 1
                                           })
        self.previous_zones = {}
        for zone in zones:
            for reporting_source in zone['reporting_sources']:
                if reporting_source['source'] == self.source:
                    self.previous_zones[zone['zone']] = False
            for sub_zone in zone['sub_zones']:
                if sub_zone['source'] == self.source:
                    self.previous_zones[sub_zone['sub_zone']] = True

    def __clean_collection(self):
        """
        Cleans the zone collection of the zones which were earlier seen in the Infoblox API
        but are not seen now. Such zones/sub-zones are marked with source 'Infoblox-Retired'.
        """
        parent_zones = []
        sub_zones = []
        for zone_name, is_sub_zone in self.previous_zones.items():
            if is_sub_zone:
                sub_zones.append(zone_name)
            else:
                parent_zones.append(zone_name)

        # Update the sub_zones from 'Infoblox' to 'Infoblox-Retired'
        self.zone_collection.update_many(
            {'sub_zones': {'$elemMatch': {
                'sub_zone': {'$in': sub_zones},
                'source': self.source
            }}},
            {'$set': {'sub_zones.$.source': 'Infoblox-Retired'}}
        )

        self.zone_collection.update_many(
            {'zone': {'$in': parent_zones},
             'reporting_sources.source': self.source
             },
            {'$set': {'reporting_sources.$.source': 'Infoblox-Retired'}}
        )

    def __insert_zone(self, zone):
        """
        Inserts the zone into the zone collection or into ip_zones collection in case
        it is an IP.
        :param zone: Zone value to be inserted into collections. This is a dictionary
                     with keys 'fqdn' and 'parent'.
        """
        # Some zones are actually IP addresses.
        # If the IP address is new, add it.
        # Change the update date if it already exists
        utf8_zone = zone['fqdn'].encode('utf-8').decode('utf8')
        if re.match(r"^([0-9]{1,3}\.){3}[0-9]{1,3}\/\d\d$", utf8_zone) is not None:
            cursor = self.ip_collection.find({"zone": zone['fqdn']})
            if cursor.count() == 0:
                insert_text = dict()
                insert_text['zone'] = utf8_zone
                insert_text['source'] = 'Infoblox'
                insert_text['status'] = 'unconfirmed'
                insert_text['created'] = datetime.now()
                insert_text['updated'] = datetime.now()
                self.ip_collection.insert_one(insert_text)
                print("Added IP: " + utf8_zone)
            else:
                for doc in cursor:
                    self.ip_collection.update_one({'zone': zone['fqdn']},
                                                  {'$currentDate': {"updated": True}})
                    print("Updated IP: " + utf8_zone)
        else:
            # cleaning the values from the previous zones found. The resultant set
            # will need to be cleared of the source value 'Infoblox'.
            if zone['fqdn'] in self.previous_zones:
                del self.previous_zones[zone['fqdn']]
            self.ZI.add_zone(zone['fqdn'], self.source, zone['parent'])

    def __infoblox_response_handler(self, response):
        """
        Handles the API response. Incorrect JSON parsing is allowed upto 20 times post which the
        script exits. If the 'next_page_id' is received in the response, then that is set as an
        identification for the next page of the API to be queried.
        :param response: Response object
        """
        try:
            response_data = response.json()
            response_result = response_data['result']
        except (ValueError, AttributeError) as err:
            if self.incorrect_response_json_allowed > 0:
                print('Unable to parse response JSON for alphabet ' + self.alphabet_queried)
                self.incorrect_response_json_allowed -= 1
            else:
                self.APIH.handle_api_error(
                    'Unable to parse response JSON for 20 alphabets: ' + repr(err),
                    'get_iblox_alpha_zones',
                )
        else:
            for entry in response_result:
                zone = dict()
                zone['fqdn'] = entry['fqdn']
                zone['parent'] = entry['parent']
                self.__insert_zone(zone)

            if 'next_page_id' in response_data:
                self.next_page_id = response_data['next_page_id']

    @backoff.on_exception(backoff.expo,
                          requests.exceptions.ConnectionError,
                          max_tries=4,
                          factor=10,
                          on_backoff=APIH.connection_error_retry)
    def __backoff_api_retry(self):
        """
        Makes API calls to Infoblox with exponential retry capabilities using 'backoff'. The API is
        retried 3 times in case of ConnectionError exception before the script exists.
        """
        url = self.__get_base_url()
        params = {
            'view': 'External',
            'fqdn~': '.*' + self.alphabet_queried + '$',
            '_return_fields': 'parent,fqdn',
        }
        if not self.next_page_id:
            params.update({
                '_paging': '1',
                '_return_as_object': '1',
                '_max_results': '1500'
            })
        else:
            params.update({'_page_id': self.next_page_id})

        return requests.get(
            url,
            params,
            auth=HTTPBasicAuth(self.IH.IBLOX_UNAME, self.IH.IBLOX_PASSWD), verify=False
        )

    def __infoblox_paginated_request(self):
        """
        Makes paginated API calls to Infoblox. The API is retried 3 times in case of ConnectionError
        exception before the script exists. The script exists on encountering HTTPError or any other
        RequestException.
        """
        try:
            response = self.__backoff_api_retry()
            response.raise_for_status()
        except requests.exceptions.HTTPError as herr:
            self.APIH.handle_api_error(herr, 'get_iblox_alpha_zones')
        except requests.exceptions.RequestException as err:
            self.APIH.handle_api_error(err, 'get_iblox_alpha_zones')
        else:
            self.next_page_id = None
            self.__infoblox_response_handler(response)

    def get_infoblox_zones(self):
        """
        Extracts the Infoblox zones using paginated requests.
        """
        print("Starting: " + str(datetime.now()))

        self.__get_previous_zones()
        for alphabet in self.alphabets:
            self.alphabet_queried = alphabet
            self.next_page_id = None
            self.__infoblox_paginated_request()
            while self.next_page_id:
                self.__infoblox_paginated_request()

        self.__clean_collection()

        # Record status
        self.jobs_collection.update_one({'job_name': 'get_iblox_alpha_zones'},
                                        {'$currentDate': {"updated": True},
                                        "$set": {'status': 'COMPLETE'}})

        print("Ending: " + str(datetime.now()))

    def __init__(self):
        self.incorrect_response_json_allowed = self.APIH.INCORRECT_RESPONSE_JSON_ALLOWED
        self.get_infoblox_zones()


if __name__ == '__main__':
    IZ = InfobloxZone()