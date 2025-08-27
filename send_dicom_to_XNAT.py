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
from RabbitMQ_messenger import messenger

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

    def checking_connectivity(self):
        """Ckecks the connection to xnat"""
        logging.info("Checking connectivity")
        connectivity = requests.get(self.xnat_url, auth=self.auth)
        logging.info(connectivity.status_code)
        return connectivity.status_code
    
    def is_session_ready(self, url):
        """Checks if the project url is ready"""
        response = requests.get(url, auth=self.auth)
        return response.status_code == 200

    def check_data_types(self, data_folder):
        """Check what type of files a are in the folder"""
        file_types = set()

        for file in os.listdir(data_folder):
            if os.path.isfile(os.path.join(data_folder, file)):
                _, ext = os.path.splitext(file)
                if ext:
                    file_types.add(ext.lower())

        return sorted(file_types)
        
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
    
    def dicom_to_xnat(self, ports, data_folder):
        """Send the DICOM in a folder to XNAT"""
        first_iteration = True
        files = os.listdir(data_folder)
        os.makedirs("zip_folder", exist_ok=True)
        zip_path = os.path.join("zip_folder", "dicoms.zip")
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in files:
                file_path = os.path.join(data_folder, file)
                
                # Get the radiomics csv file from the folder which will be used in upload_csv_to_xnat to upload it
                if file.lower().endswith('.dcm'):
                    # add file to zip with just filename (no folder)
                    zipf.write(file_path, arcname=file)
                else:
                    continue
            
                if first_iteration:
                    ds = dcmread(os.path.join(data_folder, files[0]))
                    treatment_site = ds.BodyPartExamined
        
                    project = ports[treatment_site]["project"]    
                    first_iteration = False  
                else:
                    ds = pydicom.dcmread(file_path, stop_before_pixels=True)                   
                            
        upload_url = f"{self.xnat_url}/data/services/import?PROJECT_ID={project}&overwrite=append&prearchive=true&inbody=true"            
        with open(zip_path, "rb") as f:
            response =requests.post(
                upload_url,
                data=f,
                headers={"Content-Type": "application/zip"},
                auth=self.auth
            )
            
            if response.status_code not in (200,201):
                logging.error(f"Upload failed: {response.status_code} {response.text}")
            else: 
                logging.info("All dicom files send to XNAT")
        
        os.remove(zip_path)
    
    def get_JSON_metadata(self, JSON_path):
        """Open the json metadata to be able to send the radiomics csv to the correct project"""
        with open(JSON_path, "r") as f:
            info_dict = json.load(f)
    
        patient_info = [
            info_dict["BodyPartExamined"],
            info_dict["PatientName"],
            info_dict["PatientID"]
        ]
             
        return patient_info  
    
    def upload_csv_to_xnat(self, data_folder):
        """send the radiomics csv to the correct project after the patient dicom data has been send."""
        
        files = os.listdir(data_folder)
        
        for file in files:
            if file.endswith(".csv"):
                file_path = os.path.join(data_folder, file)
                csv_radiomics = file_path
                logging.info(f"radiomics file found: {file}")
            elif file.endswith(".json"):
                file_path = os.path.join(data_folder, file)
                json_metadata = self.get_JSON_metadata(file_path)
                logging.info(f"Metata file found: {file}")
        
        try:                    
            project, subject, experiment = json_metadata
            check_url = f"{self.xnat_url}/data/projects/{project}/subjects/{subject}/experiments/{experiment}"

            # Check if the dicom files have been archived, only then the CSV files can be send
            while not self.is_session_ready(check_url):
                logging.info("DICOM data is not yet archived, can not send radiomics CSV yet...")
                time.sleep(5)    
                
            filename = os.path.basename(csv_radiomics)
            upload_url = f"{check_url}/resources/csv/files/{filename}"
            logging.info(f"Dicom data archived for session {experiment}, uploading CSV.")
            
            # Upload the the csv files to XNAT
            with open(csv_radiomics, 'rb') as f:
                response = requests.put(
                    upload_url,
                    data=f,
                    auth=self.auth,
                    headers={'Content-Type': 'text/csv'}
                )
                
                if response.status_code in [200, 201]:
                    logging.info(f"Uploaded {csv_radiomics} successfully.")
                else:
                    logging.info(f"Failed to upload {csv_radiomics}. Status: {response.status_code}, Error: {response.text}")
                        
        except Exception as e:
            logging.error(f"An error occurred sending CSV files to XNAT: {e}", exc_info=True)
            
    def send_next_queue(self, queue, data_folder):
        message_creator = messenger()
        message_creator.create_message_next_queue(queue, data_folder)
    
    
    def run(self, ch, method, properties, body, executor):
        treatment_sites = {"Tom": "LUNG", "Tim": "LUNG"}
        ports = {
            "LUNG": {"project": "LUNG", "Port": 80},
            "KIDNEY": {"project": "KIDNEY", "Port": 80}
        }
        
        ch.basic_ack(delivery_tag=method.delivery_tag)
        
        # Check if connection to xnat works
        connection = self.checking_connectivity()
        while connection != 200:
            logging.info(f"Connectivition check failed with status code: {connection}.")
            time.sleep(10)
            connection = self.checking_connectivity()

        logging.info("Connecting to XNAT works")         
        
        message_data = json.loads(body.decode("utf-8"))
        data_folder = message_data.get('folder_path')
        
        try:
            data_types = self.check_data_types(data_folder)
            if ".dcm" in data_types:
                self.adding_treatment_site(treatment_sites, data_folder)        
                self.dicom_to_xnat(ports, data_folder)
                logging.info(f"Send dicom file from: {data_folder} to XNAT")
            elif ".csv" in data_types:
                self.upload_csv_to_xnat(data_folder)
                logging.info(f"Send csv file from: {data_folder} to XNAT")
            
        except Exception as e:
            logging.error(f"An error occurred in the run method: {e}", exc_info=True)

        # Send a message to the next queue.
        if Config("xnat")["send_queue"] != None:
            self.send_next_queue(Config("xnat")["send_queue"], data_folder)
        
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