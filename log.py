import logging
import config

def make_logger(name):
	formatter = logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

	shandler = logging.StreamHandler()
	shandler.setFormatter(formatter)
	
	fhandler = logging.FileHandler("mirror.log", encoding='utf-8')
	fhandler.setFormatter(formatter)

	logger = logging.getLogger(name)
	logger.setLevel(config.log_level)
	logger.addHandler(shandler)
	logger.addHandler(fhandler)
	return logger