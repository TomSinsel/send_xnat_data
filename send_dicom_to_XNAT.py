import os
import pydicom
from pydicom import dcmread
import requests
from requests.auth import HTTPBasicAuth
import logging
import time
from consumer import Consumer
from config_handler import Config
import json
import zipfile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger()

"""This class is made to send dicom data to a XNAT server. Important thing to note XNAT filters data on Patient ID and Patient's name, 
which means that if the data received has the same patient name and the same patient id then it sorts it into the same data package."""

class SendDICOM:
    def __init__(self):
        self.xnat_url = "http://digione-infrastructure-xnat-nginx-1:80"
        username = "admin"
        password = "admin"
        self.auth = HTTPBasicAuth(username, password)
        self.csv_radiomics = None
              
    def adding_treatment_site(self, treatment_sites, data_folder):
        """Hardcode the treatment sides where we want filter on in the XNAT projects"""
        try:
            logging.info("Adding a fake treatment site to the dicom files to filter the projects.")
                   
            files = os.listdir(data_folder)
            for file in files:
                if file.endswith(".dcm"):
                    file_path = os.path.join(data_folder, file)
                    ds = dcmread(file_path)
                    treatment_site = treatment_sites[ds.PatientID]
                    ds.BodyPartExamined  = treatment_site
                    ds.save_as(file_path)
            
            logging.info("Added the treatment site")
        except Exception as e:
            logging.error(f"An error occurred adding the fake treatment site: {e}", exc_info=True)
     
    def checking_connectivity(self):
        logging.info("Checking connectivity")
        connectivity = requests.get(self.xnat_url, auth=self.auth)
        logging.info(connectivity.status_code)
        return connectivity.status_code
    
    def dicom_to_xnat(self, ports, data_folder):
        first_iteration = True
        files = os.listdir(data_folder)
        os.makedirs("zip_folder", exist_ok=True)
        zip_path = os.path.join("zip_folder", "dicoms.zip")
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in files:
                file_path = os.path.join(data_folder, file)
                
                # Get the radiomics csv file from the folder which will be used in upload_csv_to_xnat to upload it
                if file.endswith(".csv"):
                    self.csv_radiomics = file_path
                    logging.info(f"radiomics file found: {file}")    
                    continue
                elif file.lower().endswith('.dcm'):
                    # add file to zip with just filename (no folder)
                    zipf.write(file_path, arcname=file)
            
                if first_iteration:
                    ds = dcmread(os.path.join(data_folder, files[0]))
                    treatment_site = ds.BodyPartExamined
        
                    project = ports[treatment_site]["project"]    
                    first_iteration = False
                    
                else:
                    ds = pydicom.dcmread(file_path, stop_before_pixels=True)                   
            
                if ds.Modality == "RTSTRUCT":
                    # Get the BodyPartExamined, PatientName, PatientID from the rtstruct, this will be used in upload_csv_to_xnat.
                    self.patient_info = [ds.BodyPartExamined, ds.PatientName, ds.PatientID]
                
        upload_url = f"{self.xnat_url}/data/services/import?PROJECT_ID={project}&overwrite=append&prearchive=true&inbody=true"            
        with open(zip_path, "rb") as f:
            response = requests.post(
                upload_url,
                data=f,
                headers={"Content-Type": "application/zip"},
                auth=self.auth
            )
        
        os.remove(zip_path)
        logging.info("All dicom files send to XNAT")
  
    def is_session_ready(self, url):
        """Checks if the url is ready"""
        response = requests.get(url, auth=self.auth)
        return response.status_code == 200
       
    def upload_csv_to_xnat(self, data_folder):
        """send the radiomics csv to the correct project after the patient dicom data has been send."""
        
        # Get the radiomics csv file from the folder if dicom_to_XNAT method has not been used yet
        if not self.csv_radiomics:
            files = os.listdir(data_folder)
            for file in files:
                file_path = os.path.join(data_folder, file)
                
                if file.endswith(".csv"):
                    self.csv_radiomics = file_path
                    logging.info(f"radiomics file found: {file}")    
                    break
                
            # If no CSV was found in the loop stop the whole method
            if not self.csv_radiomics:
                logging.info("No CSV file found")
                return
        
        try:                    
            project, subject, experiment = self.patient_info
            check_url = f"{self.xnat_url}/data/projects/{project}/subjects/{subject}/experiments/{experiment}"

            # Check if the dicom files have been archived, only then the CSV files can be send
            while not self.is_session_ready(check_url):
                logging.info("DICOM data is not yet archived, can not send radiomics CSV yet...")
                time.sleep(5)    
                
            filename = os.path.basename(self.csv_radiomics)
            upload_url = f"{self.xnat_url}/data/projects/{project}/subjects/{subject}/experiments/{experiment}/resources/csv/files/{filename}"
            logging.info(f"Dicom data archived for session {experiment}, uploading CSV.")
            
            # Upload the the csv files to XNAT
            with open(self.csv_radiomics, 'rb') as f:
                response = requests.put(
                    upload_url,
                    data=f,
                    auth=self.auth,
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
            "LUNG": {"project": "LUNG", "Port": 80},
            "KIDNEY": {"project": "KIDNEY", "Port": 80}
        }
        
        try:
            message_data = json.loads(body.decode("utf-8"))
            data_folder = message_data.get('folder_path')

            self.adding_treatment_site(treatment_sites, data_folder)
            
            connectivity = self.checking_connectivity()     
            if connectivity != 200:
                raise SystemExit(f"Connectivity check failed with status code {connectivity}.")
            else:
                logging.info("Connecting to XNAT works")         
            
            self.dicom_to_xnat(ports, data_folder)
            self.upload_csv_to_xnat(data_folder)
            logging.info(f"Send data from: {data_folder}")
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            logging.error(f"An error occurred in the run method: {e}", exc_info=True)
        
if __name__ == "__main__":
    # treatment_sites = {"Tom": "LUNG", "Tim": "KIDNEY"}
    # ports = {
    #         "LUNG": {"project": "LUNG", "Port": 8104},
    #         "KIDNEY": {"project": "KIDNEY", "Port": 8104}
    # }
    
    # data_folder = "anonimised_data"
    
    # xnat_pipeline = SendDICOM()
    # xnat_pipeline.adding_treatment_site(treatment_sites, data_folder)
    # xnat_pipeline.dicom_to_xnat(ports, data_folder)
    # xnat_pipeline.upload_csv_to_xnat(data_folder)
    
    rabbitMQ_config = Config("xnat")
    cons = Consumer(rmq_config=rabbitMQ_config)
    cons.open_connection_rmq()
    engine = SendDICOM()
    cons.start_consumer(callback=engine.run)