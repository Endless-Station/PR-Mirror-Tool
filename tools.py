import subprocess
import sys
import config
import os
import json
from datetime import datetime
import logging


def is_gh_installed():
    try:
        # Попытка вызвать gh --version
        subprocess.run(['gh', '--version'], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def is_gh_logged():
    try:
        completed = subprocess.run(
            ["gh", "auth", "status", "--hostname",
                "github.com"],  # hostname опционален
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return completed.returncode == 0
    except subprocess.CalledProcessError:
        return False


def initialize_work_log(last_activation_day):
    if not os.path.exists(config.work_log_file):
        data = {
            "last_activation_day": last_activation_day,
            "processed_prs": [],
            "processing_prs": []
        }
        with open(config.work_log_file, 'w') as f:
            json.dump(data, f, indent=4)


def read_work_log():
    """
    Читает и возвращает содержимое файла конфигурации.
    """
    with open(config.work_log_file, 'r') as f:
        return json.load(f)


def write_work_log(data):
    """
    Записывает данные в файл конфигурации.
    """
    with open(config.work_log_file, 'w') as f:
        json.dump(data, f, indent=4)


def get_last_activation_day():
    """
    Читает дату последней активации из файла и возвращает объект datetime.
    Если дата отсутствует или файл не существует, возвращает None.
    """
    try:
        data = read_work_log()
        date_str = data.get('last_activation_day')
        if date_str:
            return date_str
        else:
            return None
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def update_activation_day(last_activation_day):
    """
    Обновляет дату последней активации на текущую дату.
    """
    data = read_work_log()
    data['last_activation_day'] = last_activation_day
    write_work_log(data)


def add_processed_pr(pr_number):
    """
    Добавляет номер PR в список обработанных PR.
    """
    data = read_work_log()
    if pr_number not in data['processed_prs']:
        data['processed_prs'].append(pr_number)
    if pr_number in data['processing_prs']:
        data['processing_prs'].remove(pr_number)
    write_work_log(data)


def add_processing_prs(processing_prs):
    data = read_work_log()
    for pr_number in processing_prs:
        if pr_number not in data['processing_prs']:
            data['processing_prs'].append(pr_number)
    write_work_log(data)
    


def get_processing_prs():
    """
    Возвращает список обработанных PR.
    """
    data = read_work_log()
    return data['processing_prs']


def get_processed_prs():
    """
    Возвращает список обработанных PR.
    """
    data = read_work_log()
    return data['processed_prs']


def get_last_merged_prs(repo, last_activation_day, limit=10):
    try:
        # Формируем команду
        command = [
            "gh", "pr", "list",
            "--repo", repo,
            "--state", "merged",
            "--limit", str(limit),
            "--json", "mergedAt,number"
        ]

        print(f"Выполнение команды: {' '.join(command)}")
        # Выполняем команду и захватываем вывод
        result = subprocess.run(
            command,
            capture_output=True,  # Захватить stdout и stderr
            text=True,            # Работать с текстом (не байтами)
            check=True,           # Выбросить исключение при ошибке
            encoding='utf-8'      # Указать кодировку
        )

        prs_data = json.loads(result.stdout)
        # print(f"Получено PR: {len(prs_data)}")
        # pr_numbers = [pr["number"] for pr in prs_data]
        # print(f"Входной список PR: {pr_numbers}")

        # 1. Фильтр по mergedAt
        filtered_prs = [
            pr for pr in prs_data
            if (merged_at := pr.get("mergedAt")) and datetime.fromisoformat(merged_at) >= datetime.fromisoformat(last_activation_day)
        ]
        # print(f"После фильтрации по дате осталось {len(filtered_prs)} PR")

        # 2. Исключаем уже обработанные
        processed_prs = set(get_processed_prs())  # set для быстрого поиска
        filtered_prs = [pr for pr in filtered_prs if pr.get(
            "number") not in processed_prs]
        # print(f"После исключения обработанных осталось {len(filtered_prs)} PR")

        # 3. Оставляем только те, что сейчас в процессе
        processing_prs = set(get_processing_prs())
        filtered_prs = [pr for pr in filtered_prs if pr.get(
            "number") not in processing_prs]
        # print(f"После фильтрации по 'в обработке' осталось {len(filtered_prs)} PR")

        # 4. Оставляем только номера PR
        pr_numbers = [pr["number"] for pr in filtered_prs]

        # print(f"Итоговый список PR: {pr_numbers}")
        return pr_numbers

    except subprocess.CalledProcessError as e:
        logger.critical(f"Ошибка при выполнении команды `gh`:")
        logger.critical(f"Команда: {' '.join(e.cmd)}")
        logger.critical(f"Код возврата: {e.returncode}")
        logger.critical(f"Stderr: {e.stderr.strip()}")
        sys.exit()
    except json.JSONDecodeError:
        logger.critical("Ошибка: Не удалось распарсить JSON-ответ от `gh`.")
        sys.exit()
    except Exception as e:
        logger.critical(f"Произошла непредвиденная ошибка: {e}")
        sys.exit()

    except subprocess.CalledProcessError as e:
        logger.critical(f"Ошибка выполнения команды: {e.stderr}")
        sys.exit()
