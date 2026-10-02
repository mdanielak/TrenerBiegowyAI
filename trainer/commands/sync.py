# -*- coding: utf-8 -*-
"""
Usage:
  python -m trainer sync         - sync latest + export all data to local/data_latest.json
  python -m trainer sync --fresh - full sync (first time / rebuild)
"""
import argparse
import logging
import sys
from ..logging_config import setup_logging
from services.data_extract import print_summary, synchronize_and_save
from services.locking import LockBusyError, acquire_lock

logger = logging.getLogger(__name__)

def main(fresh=False):
    """Synchronize first; write a snapshot only after GarminDB succeeds."""
    setup_logging()
    try:
        # Jedna blokada obejmuje pobranie, odczyt baz i zapis snapshotu.
        with acquire_lock(name="sync"):
            if fresh:
                logger.info("Starting full sync")
            else:
                logger.info("Starting incremental sync")

            data = synchronize_and_save(fresh=fresh)
            logger.info("Sync complete: %d activities, %d health records",
                        len(data.get('activities', [])),
                        len(data.get('daily_health', [])))
            print_summary(data)
    except LockBusyError:
        print("Operacja już trwa. Spróbuj ponownie za chwilę.", file=sys.stderr)
        return 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Synchronizuje dane Garmin")
    parser.add_argument('--fresh', action='store_true', help='wykonaj pełną synchronizację')
    args = parser.parse_args()
    main(fresh=args.fresh)
