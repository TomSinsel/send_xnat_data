from config_handler import Config
from consumer import Consumer


rabbitMQ_config = Config("xnat")
cons = Consumer(rmq_config=rabbitMQ_config)
cons.open_connection_rmq()
cons.send_message("messages")