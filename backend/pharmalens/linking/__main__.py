import logging
import sys

from . import ITEMS, run

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
for r in run(sys.argv[1:] or ITEMS):
    print(r)
