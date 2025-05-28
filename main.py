import sys
import log
import config
import os
import subprocess
import tools
from mirror import Mirror
from datetime import datetime, timezone
from github import Github

logger = log.make_logger("log")
logger.info("Запуск.")

mirror = Mirror()
mirror.initialize()

while True:
	mirror.initialize()
	for i in range(60):
		mirror.run()

