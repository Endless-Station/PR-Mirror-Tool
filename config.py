import logging
import os
from datetime import datetime

username = ""
password = ""
# or
api_key = ""

upstream_owner = ""
upstream_repo = ""

downstream_owner = ""
downstream_repo = ""

local_repo_directory = "local_downstream_clone"
mirror_pr_title_prefix = "[Mirroring test. Please ignore] "
mirror_branch_prefix = "upstream-merge-"

# Подразумивается какое колличество последних PR мы хотим получить, чтобы проверить
# пропущеные PR за время простоя программы
depth_pr_check = 300

log_file = "mirror.log"
work_log_file = "work_log.json"

log_level = logging.INFO
event_stream_wait = 60
