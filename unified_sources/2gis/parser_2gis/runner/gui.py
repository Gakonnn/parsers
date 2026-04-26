from __future__ import annotations

import os
import threading
import time
from typing import TYPE_CHECKING

from ..exceptions import (ChromeRuntimeException, ChromeUserAbortException,
                          ParserTooManySkips)
from ..logger import logger
from ..parser import get_parser
from ..writer import get_writer
from .runner import AbstractRunner

if TYPE_CHECKING:
    from ..config import Configuration


class GUIRunner(AbstractRunner, threading.Thread):
    """GUI thread runner.

    Args:
        urls: 2GIS URLs with items to be collected.
        output_path: Path to the result file.
        format: `csv`, `xlsx` or `json` format.
        config: Configuration.
    """
    def __init__(self, urls: list[str], output_path: str, format: str,
                 config: Configuration) -> None:
        AbstractRunner.__init__(self, urls, output_path, format, config)
        threading.Thread.__init__(self)

        self._parser = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start thread."""
        self._cancelled = False
        logger.info('Парсинг запущен.')
        threading.Thread.start(self)

    def stop(self) -> None:
        """Stop thread."""
        if not self._started.is_set():  # type: ignore
            raise RuntimeError('start() is not called')

        if self._cancelled:
            return  # We can stop the thread only once

        self._cancelled = True
        self._stop_parser()

    def _stop_parser(self) -> None:
        """Close parser if it's been opened."""
        with self._lock:
            if self._parser:
                self._parser.close()
                self._parser = None

    @staticmethod
    def _written_count(writer: object) -> int:
        return int(getattr(writer, '_wrote_count', 0))

    def _parser_options_for_remaining(self, remaining: int):
        remaining = max(1, remaining)
        parser_options = self._config.parser
        if hasattr(parser_options, 'model_copy'):
            return parser_options.model_copy(update={'max_records': remaining})
        return parser_options.copy(update={'max_records': remaining})  # pragma: no cover

    def run(self) -> None:
        """Thread's activity."""
        max_attempts = max(1, int(os.environ.get('PARSER2GIS_URL_RETRIES', '3')))
        retry_backoff = max(0.1, float(os.environ.get('PARSER2GIS_RETRY_BACKOFF_SEC', '1.2')))

        with get_writer(self._output_path, self._format, self._config.writer) as writer:
            for url in self._urls:
                logger.info(f'Парсинг ссылки {url}')
                target_records = int(self._config.parser.max_records)
                url_start_count = self._written_count(writer)

                for attempt in range(1, max_attempts + 1):
                    if self._cancelled:
                        break
                    current_count = self._written_count(writer)
                    collected_for_url = current_count - url_start_count
                    remaining = target_records - collected_for_url
                    if remaining <= 0:
                        break

                    retryable_failure = False
                    try:
                        if attempt > 1:
                            logger.warning(
                                'Перезапуск парсинга URL (%s/%s), уже собрано: %s.',
                                attempt, max_attempts, collected_for_url
                            )
                        parser_options = self._parser_options_for_remaining(remaining)
                        self._parser = get_parser(
                            url,
                            chrome_options=self._config.chrome,
                            parser_options=parser_options,
                        )
                        assert self._parser

                        if not self._cancelled:
                            self._parser.parse(writer)
                    except Exception as e:
                        if not self._cancelled:  # Don't catch intended exceptions caused by stopping parser
                            if isinstance(e, ParserTooManySkips):
                                retryable_failure = True
                                logger.warning(
                                    'Слишком много пропусков подряд, будет перезапуск браузерной сессии.'
                                )
                            elif isinstance(e, ChromeRuntimeException) and str(e) == 'Tab has been stopped':
                                retryable_failure = True
                                logger.warning('Вкладка браузера была закрыта, запускаю повторную попытку.')
                            elif isinstance(e, ChromeUserAbortException):
                                logger.error('Работа парсера прервана пользователем.')
                            else:
                                logger.error('Ошибка во время работы парсера.', exc_info=True)
                    finally:
                        self._stop_parser()

                    if self._cancelled:
                        break
                    if not retryable_failure:
                        break
                    if attempt >= max_attempts:
                        logger.error('Не удалось стабилизировать парсер для URL после %s попыток.', max_attempts)
                        break
                    time.sleep(min(5.0, retry_backoff * attempt))

                logger.info('Парсинг ссылки завершён.')
                if self._cancelled:
                    break

        logger.info('Парсинг завершён.')
