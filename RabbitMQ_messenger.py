import os
import json
import logging
from consumer import Consumer
from config_handler import Config


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger()


"""This messenger class is made to build and send messages based on the arguments: data_folder, which is the directory of the folder path with
the data and the queue. The queue is based on the name of the next rabbbitmq name, make sure that the queue name als equals the name of that
part of the config file"""

class messenger:
    
    def __init__(self):
        self.message_folder = "messages/radiomics_messages"
        self.output_file = "message.json"
    
    def create_message_next_queue(self, queue, data_folder):
        # Create the folder for the next message

        output_file_path = os.path.join(self.message_folder, self.output_file)
        os.makedirs(os.path.dirname(output_file_path), exist_ok=True)

        # Create the message
        config = {
            "folder_path": data_folder,
            "action": queue
        }

        with open(output_file_path, 'w') as file:
            json.dump(config, file, indent=2)

        logging.info(f"RabbitMQ message created at: {output_file_path}")
        
        # Send the message
        rabbitMQ_config_radiomics = Config(queue)
        radiomics = Consumer(rmq_config=rabbitMQ_config_radiomics)
        radiomics.open_connection_rmq()
        radiomics.send_message(self.message_folder)
        
        logging.info(f"Send the data: {data_folder} to: {queue} ")