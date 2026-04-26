class ParserException(Exception):
    pass


class ParserTooManySkips(ParserException):
    pass


__all__ = [
    'ParserException',
    'ParserTooManySkips',
]
