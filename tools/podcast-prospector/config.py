import os
from dotenv import load_dotenv

load_dotenv()

YOUTUBE_API_KEY = os.environ['YOUTUBE_API_KEY']
APIFY_API_KEY = os.environ['APIFY_API_KEY']

APIFY_ACTOR_ID = 'rmTzLhLPMfop3nYqd'
YOUTUBE_SHORTS_MAX_SECONDS = 60
LOOKBACK_DAYS = 90
MAX_PAGES = 20
