import yaml
import logging


def read_config():
    with open('config.yaml', 'r') as file:
        file_red = yaml.safe_load(file)
        return file_red


class Config:
    def __init__(self, section_name):
        file = read_config()
        self.config = None
        self.read_config_section(file, section_name)

    def read_config_section(self, file, sect):
        self.config = file.get(sect, {})
        
    def __getitem__(self, key):
        return self.config[key]

    def __getattr__(self, key):
        try:
            return self.config[key]  # Enables config.key
        except KeyError:
            raise AttributeError(f"'Config' object has no attribute '{key}'")

    def as_dict(self):
        return self.config  # Optional: for full dictionary access
