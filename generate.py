#!/usr/bin/env python3
"""
Quick Action script to generate a podcast RSS feed (feed.xml) for a directory of MP3 files.
"""
import sys
import os
import logging
from urllib.parse import quote
from mutagen.id3 import ID3, APIC, error
from mutagen.easyid3 import EasyID3
from datetime import datetime
import subprocess
import xml.etree.ElementTree as ET

# Configuration
PODCAST_TITLE = "Nash Spence Music"
PODCAST_LINK = "https://0819870.xyz/music/nash-spence/"
PODCAST_ART = "logo.jpg"
PODCAST_DESCRIPTION = "A collection of songs by Nash Spence"
PODCAST_CATEGORY = "Music"
PODCAST_LANGUAGE = "en"
PODCAST_EXPLICIT = "true"
EPISODE_ART_DIR = "covers"
LOG_PATH = os.path.expanduser('/Users/nashspence/Desktop/rss_feed_log.txt')

# Setup logging
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s'
)


def clean_apostrophes(text):
    """Replace curly apostrophes with straight ones."""
    return text.replace('’', "'")


def ensure_cover(mp3_path, cover_dir):
    """
    Ensure that a cover image exists in cover_dir for given mp3.
    If not, extract from ID3 APIC and resize via ffmpeg.
    Returns cover filename or None.
    """
    try:
        tags = ID3(mp3_path)
    except error as e:
        logging.error(f"ID3 error for {mp3_path}: {e}")
        return None

    base = os.path.splitext(os.path.basename(mp3_path))[0]
    cover_name = f"{base}.jpg"
    cover_path = os.path.join(cover_dir, cover_name)

    if os.path.exists(cover_path):
        return cover_name

    for tag in tags.values():
        if isinstance(tag, APIC) and tag.type == 3:  # front cover
            img_data = tag.data
            os.makedirs(cover_dir, exist_ok=True)
            temp_path = os.path.join(cover_dir, f"{base}_tmp")
            with open(temp_path, 'wb') as img:
                img.write(img_data)
            final_path = cover_path
            cmd = [
                'ffmpeg', '-y',
                '-i', temp_path,
                '-vf', "scale='if(gt(iw,ih),min(3000,iw),-2)':'if(gt(ih,iw),min(3000,ih),-2)',pad=1400:1400:(ow-iw)/2:(oh-ih)/2'",
                '-dpi', '72',
                final_path
            ]
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                os.remove(temp_path)
                logging.info(f"Extracted and resized cover for {mp3_path}")
                return cover_name
            except subprocess.CalledProcessError as e:
                logging.error(f"ffmpeg error for {mp3_path}: {e.stderr.decode()}")
                return None

    logging.warning(f"No APIC cover found in {mp3_path}")
    return None


def get_episode_info(mp3_path, base_url, cover_dir):
    """Extract episode metadata and return as dict."""
    filename = os.path.basename(mp3_path)
    clean_name = clean_apostrophes(filename)
    if filename != clean_name:
        new_path = os.path.join(os.path.dirname(mp3_path), clean_name)
        os.rename(mp3_path, new_path)
        mp3_path = new_path
        logging.info(f"Renamed file {filename} -> {clean_name}")

    audio = EasyID3(mp3_path)
    tags = ID3(mp3_path)

    title = clean_apostrophes(audio.get('title', [os.path.splitext(clean_name)[0]])[0])
    # Use encoded filename for link
    url = base_url + quote(clean_name)

    date_tag = audio.get('date', [None])[0]
    if date_tag:
        try:
            pub_dt = datetime.strptime(date_tag, '%Y-%m-%d')
        except ValueError:
            pub_dt = datetime.now()
            logging.warning(f"Invalid date tag in {clean_name}, using now.")
    else:
        pub_dt = datetime.now()
        logging.warning(f"Missing date tag in {clean_name}, using now.")
    pub_date = pub_dt.strftime('%a, %d %b %Y %H:%M:%S %z')

    comment = audio.get('comment', [''])[0]
    cover_file = ensure_cover(mp3_path, cover_dir)

    return {
        'title': title,
        'filename': clean_name,
        'link': url,
        'pubDate': pub_date,
        'description': comment,
        'cover': cover_file,
        'file_path': mp3_path
    }


def build_feed(directory):
    """Build the RSS feed XML and write to feed.xml in directory."""
    rss = ET.Element('rss', version='2.0', attrib={
        'xmlns:itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd'
    })
    channel = ET.SubElement(rss, 'channel')
    ET.SubElement(channel, 'title').text = PODCAST_TITLE
    ET.SubElement(channel, 'link').text = PODCAST_LINK
    ET.SubElement(channel, 'language').text = PODCAST_LANGUAGE
    ET.SubElement(channel, 'itunes:explicit').text = PODCAST_EXPLICIT
    ET.SubElement(channel, 'itunes:category', text=PODCAST_CATEGORY)
    ET.SubElement(channel, 'itunes:image', href=PODCAST_LINK + PODCAST_ART)
    ET.SubElement(channel, 'description').text = PODCAST_DESCRIPTION

    mp3s = [f for f in os.listdir(directory) if f.lower().endswith('.mp3')]
    episodes = []
    cover_dir = os.path.join(directory, EPISODE_ART_DIR)
    for f in mp3s:
        path = os.path.join(directory, f)
        info = get_episode_info(path, PODCAST_LINK, cover_dir)
        episodes.append((info['pubDate'], info))

    episodes.sort(key=lambda x: x[0])

    for _, info in episodes:
        item = ET.SubElement(channel, 'item')
        ET.SubElement(item, 'title').text = info['title']
        ET.SubElement(item, 'itunes:author').text = 'Nash Spence'
        ET.SubElement(item, 'link').text = info['link']

        # Enclosure tag with properly encoded URL
        try:
            file_size = os.path.getsize(info['file_path'])
        except OSError:
            file_size = 0
            logging.warning(f"Could not get file size for {info['file_path']}")
        enclosure_url = PODCAST_LINK + quote(info['filename'])
        enclosure = ET.SubElement(item, 'enclosure')
        enclosure.set('url', enclosure_url)
        enclosure.set('length', str(file_size))
        enclosure.set('type', 'audio/mpeg')

        # Use enclosure URL for GUID
        ET.SubElement(item, 'guid').text = enclosure_url

        ET.SubElement(item, 'pubDate').text = info['pubDate']
        ET.SubElement(item, 'description').text = info['description']

        if info['cover']:
            cover_url = PODCAST_LINK + f"{EPISODE_ART_DIR}/{info['cover']}"
            ET.SubElement(item, 'itunes:image', href=cover_url)

    tree = ET.ElementTree(rss)
    out_path = os.path.join(directory, 'feed.xml')
    tree.write(out_path, encoding='utf-8', xml_declaration=True)
    logging.info(f"Wrote feed to {out_path}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: script.py <directory>')
        sys.exit(1)
    target_dir = sys.argv[1]
    try:
        build_feed(target_dir)
    except Exception as e:
        logging.exception(f"Failed to build feed: {e}")
        sys.exit(1)
