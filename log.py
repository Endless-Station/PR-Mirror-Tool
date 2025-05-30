import logging
import config

def make_logger(name):
    formatter = logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

    shandler = logging.StreamHandler()
    shandler.setFormatter(formatter)

    # Попытка создать файловый обработчик
    try:
        if config.log_file:
            fhandler = logging.FileHandler(config.log_file, encoding='utf-8')
        else:
            fhandler = logging.FileHandler("mirror.log", encoding='utf-8')
    except Exception as e:
        # Если не удалось создать файловый обработчик, логируем ошибку через консоль и используем альтернативный обработчик
        shandler.emit(logging.makeLogRecord({
            'msg': f'Не удалось создать файловый обработчик. Используем консоль для логирования. Ошибка: {e}',
            'levelno': logging.ERROR,
            'levelname': 'ERROR'
        }))
        fhandler = logging.StreamHandler()
    
    fhandler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(config.log_level)
    logger.addHandler(shandler)
    logger.addHandler(fhandler)
    
    return logger