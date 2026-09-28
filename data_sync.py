# -*- coding: utf-8 -*-
"""
Usage:
  python data_sync.py         - sync latest + export all data to data_latest.json
  python data_sync.py --fresh - full sync (first time / rebuild)
"""
import sys
import logging
from logging_config import setup_logging
from services.data_extract import sync, sync_full, extract, save_json, print_summary

logger = logging.getLogger(__name__)

def main():
    """Synchronize first; write a snapshot only after GarminDB succeeds."""
    setup_logging()
    fresh = '--fresh' in sys.argv

    if fresh:
        logger.info("Starting full sync")
        sync_full()
    else:
        logger.info("Starting incremental sync")
        sync()

    logger.info("Extracting data from databases")
    data = extract()
    save_json(data)
    logger.info("Sync complete: %d activities, %d health records",
                len(data.get('activities', [])),
                len(data.get('daily_health', [])))
    print_summary(data)


if __name__ == '__main__':
    main()
