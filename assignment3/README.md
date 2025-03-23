**config.txt:** Set attributes
**local_server.py:** The main script which runs tasks and handles migration and creation of GCP VM
**gcp_tasks.py:** The script which is run on GCP VM, ie, the script which is sent to GCP VM using SCP.

* Note that in **local_server.py**, PROJECT_ID attribute is catered to my machine only. For any other machine, firsly gcloud CLI has to be set up and then the respective project ID needs to be entered.
