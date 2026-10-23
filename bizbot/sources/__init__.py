"""Listing sites the bot can read. Each module provides NAME, list_entries() and fetch_listing()."""
from . import bsale, commercialrealestate

SOURCES = {bsale.NAME: bsale, commercialrealestate.NAME: commercialrealestate}
