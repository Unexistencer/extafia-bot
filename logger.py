import os
import logging
import re
import string
import random

log_dir = "logs"
log_file_size_limit = 1 * 1024 * 1024

def generate_task_num():
    characters = string.ascii_letters + string.digits
    return ''.join(random.choices(characters, k=6))

def get_next_log_filename():
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # get all files starts with 'log-'
    log_files = [f for f in os.listdir(log_dir) if f.startswith('log-')]
    
    # if none, create 'log-1.log'
    if not log_files:
        return os.path.join(log_dir, 'log-1.log')
    
    # if exist, find the latest one (which is largest num)
    latest_log_num = max([int(re.search(r'log-(\d+)\.log', f).group(1)) for f in log_files])
    latest_log_file = os.path.join(log_dir, f"log-{latest_log_num}.log")

    # check file size, create a new one if the latest file's size is over 1mb
    if os.path.getsize(latest_log_file) >= log_file_size_limit:
        return os.path.join(log_dir, f"log-{latest_log_num + 1}.log")
    else:
        return latest_log_file

def setup_logging():
    # set log file
    log_filename = get_next_log_filename()
    
    # create logger
    logger = logging.getLogger('Extafia')
    logger.setLevel(logging.DEBUG)
    
    # create RotatingFileHandler, with the size limit of 1mb
    try:
        handler = logging.FileHandler(log_filename, encoding="utf-8")
    except Exception as e:
        print(f"[logger] cannot open log file {log_filename}: {e}")
        return logger
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    
    # add handler to logger
    if not logger.handlers:
        logger.addHandler(handler)
    
    return logger



logger = setup_logging()