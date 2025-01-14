# CHANGELOG

## March 11, 2019
* The WebUI has been simplified to be completely based on Boostrap, jQuery, and Octicons.


## March 7, 2019
* Splunk libraries and a script template have been added. Some organizations store useful information in Splunk that could be correlated with Marinus. Unfortunately, the way that the data is stored and indexed would vary between organizations. As a compromise, Marinus provides libraries for accessing Splunk. However, unlike other Marinus code, the get_splunk_data.py script would need code contributed by the user in order to be run. The file is only a template containing sample code for using the Splunk libraries.
* The API for fetching internal domain references within TLS certificates has been updated to allow for retrieving the count.
* Send_remote_server now has flags to allow uploading of individual collections.
* The Sonar scripts will not automatically create the directories that are needed.
* A reference to the most recent Common Crawl graph has been added to to common_crawl_graph.py
* The CA path in the Infoblox libraries have been updated to reflect more recent paths.
* The nginx configuration files have been updated to reflect more recent options.
* Several bugs have been found and fixed. 


## February 19, 2019
* The original ZGrab utility has been deprecated by the project owners. Therefore, Marinus has been updated to support the new ZGrab 2.0 version. The schemas between the two versions are not compatible and support for the new schemas has been added. Marinus will now support both versions but it defaults to version 2.0. The version can be specified in the env.js file on the web server. New command line parameters will inform the relevant Python scripts.
* Many WHOIS records now redact the owner details for privacy. This makes it difficult to determine the owner of a domain name based on the organizational value. To address part of this problem, support has been added to validate that the name server values within the WHOIS record belong to your organization. The setup.py script can be used to add the DNS addresses for your organization's name servers. These values can then be used by the mark_expired script to ensure that your organization still controls the domain.
* There have been important bug fixes added to the new certificate code and whois_lookups code.


## February 7, 2019
* Modified the get_original_ct_logs, get_crt_sh, and download_facebook_certs scripts to start recording the zones associated with the certificate. This will make it easier to search the ct_certs collection for root domains.


## February 6, 2019
* The get_owasp_amass script adds support to import DNS data from the OWASP Amass tool. Amass is similar to Marinus and supports a few more data sources than Marinus. Rather than duplicating existing Amass functionality, Marinus now supports running and importing the results from Amass searches. The OWASP Amass GitHub page provides information on how to install the tool: https://github.com/OWASP/Amass/
* In order to decrease the chances of script failures due to database connection issues, support was added to handle pymongo AutoReconnect exceptions for the find queries in a few selected libraries. As Marinus progresses, this will expand to a more complete implementation.


## February 5, 2019
* PTR records are now added to the all_dns collection when RDNS records are identified in Sonar.
* A few bug fixes and touch ups.


## February 4, 2019
* The Python 2 versions of hash_based_upload and download_* were removed.
* A Python 3 X509 certificate parser was added to separate the certificate parsing from the hash_based_upload script.
* The get_original_ct_logs Python 3 script was added as a replacement for the Python 2 download_* and hash_based_upload scripts. It is more performant over time than the Python 2 scripts because it only queries new certs since the last run. The script does not require the Google Certificate Transparency project, it works with any Version 1 CT Log, and performs more thorough searching of zones. Saving of certificates to disk is now optional.
* A get_crt_sh script was created to allow for querying the crt.sh service for additional certificates. Saving certificates to disk is optional.
* A Python 3 Jobs Manager library was created to standardize job tracking.
