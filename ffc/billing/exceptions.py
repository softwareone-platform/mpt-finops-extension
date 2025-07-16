class JournalStatusError(Exception):
    pass


class ErrorJournalCreation(Exception):
    pass

import logging

class PrefixAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        return f"[{self.extra['prefix']}] {msg}", kwargs

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')