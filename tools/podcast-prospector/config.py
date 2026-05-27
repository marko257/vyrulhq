import os
from dotenv import load_dotenv

load_dotenv()

LISTEN_NOTES_API_KEY = os.environ['LISTEN_NOTES_API_KEY']
YOUTUBE_API_KEY = os.environ['YOUTUBE_API_KEY']

LISTEN_NOTES_BASE_URL = 'https://listen-api.listennotes.com/api/v2'
YOUTUBE_SHORTS_MAX_SECONDS = 60
LOOKBACK_DAYS = 90
MIN_EPISODES = 50
MAX_PAGES = 20
