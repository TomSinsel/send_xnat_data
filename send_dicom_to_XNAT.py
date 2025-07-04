import os
import pydicom
from pydicom import dcmread
from pynetdicom import AE, StoragePresentationContexts
import requests
from requests.auth import HTTPBasicAuth
import logging
import time
from consumer import Consumer
from config_handler import Config
import json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger()

"""This class is made to send dicom data to a XNAT server. Important thing to note XNAT filters data on Patient ID and Patient's name, 
which means that if the data received has the same patient name and the same patient id then it sorts it into the same data package."""

class sendDICOM:
    def __init__(self):
        self.xnat_url = "http://localhost:80"
        self.username = "admin"
        self.password = "admin"
        self.csv_radiomics = None
        
        
    def adding_treatment_site(self, treatment_sites, data_folder):
        """Hardcode the treatment sides where we want filter on in the XNAT projects"""
        try:
            logging.info("Adding a fake treatment site to the dicom files to filter the projects.")
                   
            for file in os.listdir(data_folder):
                if file.endswith(".dcm"):
                    file_path = os.path.join(data_folder, file)
                    ds = dcmread(file_path)
                    treatment_site = treatment_sites[ds.PatientID]
                    ds.BodyPartExamined  = treatment_site
                    ds.save_as(file_path)
            
            logging.info("added the treatment site")
        except Exception as e:
            logging.error(f"An error occurred adding the fake treatment site: {e}", exc_info=True)
            
    def dicom_to_XNAT(self, ports, data_folder):
        """Send dicom data to the XNAT server"""
        try: 
            ae = AE()
            ae.requested_contexts = StoragePresentationContexts
            self.patient_info = []
                
            first_iteration = True
            
            for file in os.listdir(data_folder):
                
                file_path = os.path.join(data_folder, file)
                
                # Get the radiomics csv file from the folder which will be used in upload_csv_to_xnat to upload it
                if file.endswith(".csv"):
                    self.csv_radiomics = file_path
                    logging.info(f"radiomics file found: {file}")    
                    continue
            
                if first_iteration:
                    ds = dcmread(os.path.join(data_folder, os.listdir(data_folder)[0]))
                    treatment_site = ds.BodyPartExamined
                    
                    port = ports[treatment_site]["Port"]
                    Title = ports[treatment_site]["Title"]
                    
                    first_iteration = False
                else:
                    # Get the BodyPartExamined, PatientName, PatientID from the rtstruct, this will be used in upload_csv_to_xnat.
                    ds = pydicom.dcmread(file_path, stop_before_pixels=True)                   
                
                
                assoc = ae.associate('xnat-web-1', port, ae_title = Title)
            
                if ds.Modality == "RTSTRUCT":
                    self.patient_info = [ds.BodyPartExamined, ds.PatientName, ds.PatientID]
                
                # Send the files to XNAT
                if assoc.is_established:
                    ds = dcmread(file_path)
                    assoc.send_c_store(ds)
                    assoc.release()
                else:
                    logging.warning("Association failes")
                    
            logging.info("All dicom files send to XNAT")
        
        except Exception as e:
            logging.error(f"An error occurred sending dicom files to XNAT: {e}", exc_info=True)
    
    
    def is_session_ready(self, url):
        """Checks if the url is ready"""
        response = requests.get(url, auth=HTTPBasicAuth(self.username, self.password))
        return response.status_code == 200
       
    def upload_csv_to_xnat(self, data_folder):
        """send the radiomics csv to the correct project after the patient dicom data has been send."""
        
        # Get the radiomics csv file from the folder if dicom_to_XNAT method has not been used yet
        if not self.csv_radiomics:
            for file in os.listdir(data_folder): 
                file_path = os.path.join(data_folder, file)
                
                if file.endswith(".csv"):
                    self.csv_radiomics = file_path
                    logging.info(f"radiomics file found: {file}")    
                    break
        
        try:                    
            project, subject, experiment = self.patient_info
            check_url = f"{self.xnat_url}/data/projects/{project}/subjects/{subject}/experiments/{experiment}"

            # Check if the dicom files have been archived, only then the CSV files can be send
            while not self.is_session_ready(check_url):
                logging.info("DICOM data is not yet archived, can not send csv")
                time.sleep(5)    
                
            upload_url = f"{self.xnat_url}/data/projects/{project}/subjects/{subject}/experiments/{experiment}/resources/csv/files/{self.csv_radiomics}"
            logging.info(f"Dicom data archived for session {experiment}, uploading CSV.")
            
            # Upload the the csv files to XNAT
            with open(self.csv_radiomics, 'rb') as f:
                response = requests.put(
                    upload_url,
                    data=f,
                    auth=HTTPBasicAuth(self.username, self.password),
                    headers={'Content-Type': 'text/csv'}
                )
                
                if response.status_code in [200, 201]:
                    logging.info(f"Uploaded {self.csv_radiomics} successfully.")
                else:
                    logging.info(f"Failed to upload {self.csv_radiomics}. Status: {response.status_code}, Error: {response.text}")
                        
        except Exception as e:
            logging.error(f"An error occurred sending CSV files to XNAT: {e}", exc_info=True)
    
    def run(self, ch, method, properties, body, executor):
        treatment_sites = {"Tom": "LUNG", "Tim": "KIDNEY"}
        ports = {
            "LUNG": {"Title": "LUNG", "Port": 8104},
            "KIDNEY": {"Title": "KIDNEY", "Port": 8104}
        }
        
        try:
            message_data = json.loads(body.decode("utf-8"))
            data_folder = message_data.get('folder_path')

            self.adding_treatment_site(treatment_sites, data_folder)
            self.dicom_to_XNAT(ports, data_folder)
            self.upload_csv_to_xnat(data_folder)
            logging.info(f"Send data from: {data_folder}")

        except Exception as e:
            logging.error(f"An error occurred in the run method: {e}", exc_info=True)
        
if __name__ == "__main__":
    # treatment_sites = {"Tom": "LUNG", "Tim": "KIDNEY"}
    # ports = {
    #         "LUNG": {"Title": "LUNG", "Port": 8104},
    #         "KIDNEY": {"Title": "KIDNEY", "Port": 8104}
    # }
    
    # data_folder = "anonimised_data"
    
    # xnat_pipeline = sendDICOM()
    # xnat_pipeline.adding_treatment_site(treatment_sites, data_folder)
    # xnat_pipeline.dicom_to_XNAT(ports, data_folder)
    # xnat_pipeline.upload_csv_to_xnat(data_folder)
    
    rabbitMQ_config = Config("xnat")
    cons = Consumer(rmq_config=rabbitMQ_config)
    cons.open_connection_rmq()
    engine = sendDICOM()
    cons.start_consumer(callback=engine.run)