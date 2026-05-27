import re
import requests
import xml.etree.ElementTree as ET
from typing import Optional

ITUNES_NS = 'http://www.itunes.com/dtds/podcast-1.0.dtd'


def extract_email(rss_url: str) -> Optional[str]:
    try:
        response = requests.get(rss_url, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        channel = root.find('channel')
        if channel is None:
            return None

        itunes_email = channel.find(f'{{{ITUNES_NS}}}email')
        if itunes_email is not None and itunes_email.text:
            return itunes_email.text.strip()

        managing_editor = channel.find('managingEditor')
        if managing_editor is not None and managing_editor.text:
            match = re.match(r'([^\s(]+)', managing_editor.text.strip())
            return match.group(1) if match else None

        return None
    except Exception:
        return None
