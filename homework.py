import logging
import os
import sys
import telegram
import time
import requests

from dotenv import load_dotenv
from http import HTTPStatus


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


class ApiError(Exception):
    """ApiError exception."""

    pass


formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] - %(message)s")
formatter.datefmt = "%Y-%m-%d %H:%M:%S"

handler = logging.StreamHandler(stream=sys.stdout)
handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)


def send_message(bot: telegram.Bot, message: str) -> None:
    """Отправить сообщение в Telegram."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.info(f"Send message to chat {TELEGRAM_CHAT_ID}: {message}")
    except Exception as error:
        logger.error(f"Failed to send message: {error}")


def get_api_answer(current_timestamp: float) -> dict:
    """Запросить статус проверки проектных работ Яндекс.Практикума."""
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}

    try:
        response = requests.get(
            url=ENDPOINT,
            headers=HEADERS,
            params=params)
    except Exception as error:
        message = f"Failed to make a request: {error}"
        logger.error(message)
        raise ApiError(message)

    if response.status_code != HTTPStatus.OK:
        message = (
            f"API service is unavailable: "
            f"{response.status_code}")
        logger.error(message)
        raise ApiError(message)

    return response.json()


def check_response(response: dict) -> list:
    """Проверить ответ API на корректность."""
    if not isinstance(response, dict):
        raise TypeError(
            f"Ответ от API не является словарем: response = {response}"
        )

    homeworks = response.get('homeworks')
    if homeworks is None:
        message = (
            f"В ответе API отсутствуют необходимый ключ 'homeworks', "
            f"response = {response}")
        logger.error(message)
        raise KeyError(message)
    if not isinstance(homeworks, list):
        raise TypeError(
            f"Ответ от API поле 'homeworks' не является списком: "
            f"response = {homeworks}")

    return homeworks


def parse_status(homework: dict) -> str:
    """Извлечь статус проектной работы."""
    name = homework.get('homework_name')
    status = homework.get('status')
    if name is None:
        message = (
            f'В ответе API отсутствуют необходимый ключ "homework_name", '
            f'response = {homework}')
        logger.error(message)
        raise KeyError(message)
    if status is None:
        message = (
            f'В ответе API отсутствуют необходимый ключ "status", '
            f'response = {homework}')
        logger.error(message)
        raise KeyError(message)

    verdict = HOMEWORK_STATUSES.get(status)
    if verdict is None:
        message = f"Unknown homework status: {status}"
        logger.error(message)
        raise TypeError(message)

    return f'Изменился статус проверки работы "{name}". {verdict}'


def check_tokens() -> bool:
    """Проверить доступность переменных окружения."""
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def main() -> None:
    """Основная логика работы бота."""
    if not check_tokens():
        logger.critical("Environment variables are not set")
        sys.exit()

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())

    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)

            if not homeworks:
                logger.debug("Empty statuses list")

            for hw in homeworks:
                send_message(bot, parse_status(hw))

            current_timestamp = int(time.time())
            time.sleep(RETRY_TIME)
        except Exception as error:
            send_message(bot, f'Сбой в работе программы: {error}')
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
