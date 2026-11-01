"""Listing sites the bot can read. Each module provides NAME, list_entries() and fetch_listing()."""
from . import anybusiness, bsale, business2sell, businessforsale, commercialrealestate

SOURCES = {
    bsale.NAME: bsale,
    business2sell.NAME: business2sell,
    anybusiness.NAME: anybusiness,
    businessforsale.NAME: businessforsale,
    commercialrealestate.NAME: commercialrealestate,
}
