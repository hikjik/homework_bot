import json
import logging
import os
import sys
import telegram
import time
import requests

from dotenv import load_dotenv
from http import HTTPStatus

from exceptions import (
    TelegramError,
    APIStatusCodeError,
    APIResponseError,
)


load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def send_message(bot: telegram.Bot, message: str) -> None:
    """Отправить сообщение в Telegram."""
    try:
        logging.debug('Старт отправки сообщения в Telegram: {message}')
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except telegram.error.TelegramError as error:
        raise TelegramError(
            f"Ошибка при отправке сообщения {message} "
            f"в чат {TELEGRAM_CHAT_ID} Telegram") from error
    else:
        logging.info(
            f"Сообщение '{message}' успешно отправлено "
            f"в чат Telegram {TELEGRAM_CHAT_ID}")


def get_api_answer(current_timestamp: int) -> dict:
    """Запросить статус проверки проектных работ Яндекс.Практикума."""
    timestamp = current_timestamp or int(time.time())
    request_params = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {
            'from_date': timestamp,
        },
    }

    try:
        logging.debug(
            "Отправка запроса к API сервиса Практикум.Домашка"
            f"Параметры запроса: {request_params}.")
        response = requests.get(**request_params)

        if response.status_code != HTTPStatus.OK:
            raise APIStatusCodeError(
                'Неверный ответ сервера: '
                f'http code = {response.status_code}; '
                f'reason = {response.reason}; '
                f'content = {response.text}')

        response = response.json()
    except requests.exceptions.RequestException as error:
        raise APIResponseError(
            f"Ошибка подключения к API сервиса Практикум.Домашка: {error}. "
            f"Параметры запроса: {request_params}.") from error
    except json.JSONDecodeError as error:
        raise APIResponseError(
            f"Ошибка при декодировании ответа API сервиса: {error}. "
            f"Параметры запроса: {request_params}.") from error
    else:
        logging.debug("Получен ответ от API сервиса Практикум.Домашка")

    return response


def check_response(response: dict) -> list:
    """Проверить ответ API на корректность."""
    if not isinstance(response, dict):
        raise TypeError(
            f"Ответ от API не является словарем: "
            f"response = {response}")

    homeworks = response.get('homeworks')
    if homeworks is None:
        raise KeyError(
            f"В ответе API отсутствуют необходимый ключ 'homeworks', "
            f"response = {response}")
    if not isinstance(homeworks, list):
        raise TypeError(
            f"В ответе от API поле 'homeworks' не является списком: "
            f"homeworks = {homeworks}")

    return homeworks


def parse_status(homework: dict) -> str:
    """Извлечь статус проектной работы."""
    name = homework.get('homework_name')
    if name is None:
        message = (
            f'В ответе API отсутствуют необходимый ключ "homework_name", '
            f'homework = {homework}')
        raise KeyError(message)

    status = homework.get('status')
    if status is None:
        message = (
            f'В ответе API отсутствуют необходимый ключ "status", '
            f'homework = {homework}')
        raise KeyError(message)

    verdict = HOMEWORK_STATUSES.get(status)
    if verdict is None:
        raise TypeError(
            f"Неизвестный статус домашней работы: {status}")

    return f'Изменился статус проверки работы "{name}". {verdict}'


def check_tokens() -> bool:
    """Проверить доступность переменных окружения."""
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def main() -> None:
    """Основная логика работы бота."""
    if not check_tokens():
        error_message = (
            'Не заданы необходимые переменные окружения: '
            'PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID. '
            'Программа принудительно остановлена.'
        )
        logging.critical(error_message)
        sys.exit(error_message)

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())

    while True:
        error_message = ""
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)

            if not homeworks:
                logging.debug("В ответе API отсутствуют новые статусы.")

            for homework in homeworks:
                verdict = parse_status(homework)
                send_message(bot, verdict)

            current_timestamp = int(time.time())
        except TelegramError as error:
            error_message = f"Ошибка в работе телеграм-бота: {error}"
        except (APIResponseError, APIStatusCodeError) as error:
            error_message = f'Ошибка в работе API сервиса: {error}'
        except (KeyError, TypeError) as error:
            error_message = f'Некорректный формат ответа API сервиса: {error}'
        except Exception as error:
            error_message = f'Непредвиденный сбой в работе программы: {error}'
        finally:
            if error_message:
                logging.error(error_message)
                try:
                    send_message(bot, error_message)
                except TelegramError as error:
                    logging.error(f"Ошибка в работе телеграм-бота: {error}")

            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    log_format = (
        '%(asctime)s [%(levelname)s] - '
        '(%(filename)s).%(funcName)s:%(lineno)d - %(message)s'
    )
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    main()
