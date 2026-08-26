# utils/logging_setup.py
"""
Logging configuration for Nebulae.

Nebulae historically used print() everywhere. That works, but it has no
levels, which means the noisy DEBUG output cannot be turned off — and some of
that output contains other people's data. For example, federated user
discovery used to dump the full JSON profile payload of every remote user to
stdout, where it sat in the Docker journal indefinitely.

Routing everything through the logging module means:

  * LOG_LEVEL=WARNING on a production node silences the chatter entirely
  * lines carry a timestamp, level and source module
  * an admin can raise the level temporarily to diagnose something, then
    lower it again, without redeploying

The docs already advertise a LOG_LEVEL environment variable. This is what
finally makes it real.
"""

import logging
import os
import sys

VALID_LEVELS = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')

DEFAULT_FORMAT = '%(asctime)s %(levelname)-8s %(name)s: %(message)s'
DEFAULT_DATEFMT = '%Y-%m-%d %H:%M:%S'


def configure_logging(app=None):
    """
    Set up root logging from the LOG_LEVEL environment variable.

    Call once, early in app.py, before anything else logs.
    Returns the level name actually applied.
    """
    requested = os.environ.get('LOG_LEVEL', 'INFO').upper().strip()
    if requested not in VALID_LEVELS:
        fallback = 'INFO'
        level = logging.INFO
        invalid = requested
    else:
        fallback = None
        level = getattr(logging, requested)
        invalid = None

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(DEFAULT_FORMAT, datefmt=DEFAULT_DATEFMT))

    root = logging.getLogger()
    # Gunicorn installs its own handlers; replace them so we don't double-log.
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # These libraries are chatty at INFO and have nothing useful to say here.
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('PIL').setLevel(logging.WARNING)

    if app is not None:
        app.logger.handlers.clear()
        app.logger.propagate = True
        app.logger.setLevel(level)

    log = logging.getLogger(__name__)
    if invalid:
        log.warning("LOG_LEVEL=%r is not valid; using %s. Valid values: %s",
                    invalid, fallback, ', '.join(VALID_LEVELS))
    log.info("Logging configured at %s", requested if not invalid else fallback)

    return requested if not invalid else fallback
