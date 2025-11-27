"""
Boston Open Data Portal → MySQL Automated Sync

This package provides tools to automatically sync data from data.boston.gov
to your local MySQL server.
"""

from .boston_data_sync import BostonDataSyncer

__all__ = ['BostonDataSyncer']

