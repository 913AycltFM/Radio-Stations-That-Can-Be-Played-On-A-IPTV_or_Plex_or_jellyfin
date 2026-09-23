import json
import html
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo


# ============================================================
# 91.3 AYCLT FM - AUTOMATIC XMLTV EPG GENERATOR
# ============================================================

AZURACAST_BASE_URL = "https://radio.913aycltfm.com"

TIMEZONE = ZoneInfo("America/Chicago")

# How many days into the future to generate
DAYS_AHEAD = 30

# Files generated in the GitHub repository
XML_OUTPUT = "91.3_Ayclt_ FM_radio_guide.xml"
JSON_OUTPUT = "epg.json"


# ============================================================
# CHANNEL CONFIGURATION
# ============================================================

CHANNELS = [
    {
        "id": "913AycltFM",
        "display": "1",
        "name": "91.3 Ayclt FM",
        "description": "Dickinson's Texas #1 Hit Music Station",
        "icon": "https://radio.913aycltfm.com/static/uploads/91.3_ayclt_fm/background.1779890712.png",
        "station": "91.3_ayclt_fm",
    },
    {
        "id": "913AycltFMHD2",
        "display": "1.2",
        "name": "91.3 Ayclt FM HD2",
        "description": "Dickinson's Texas #1 Hit Music Station",
        "icon": "https://radio.913aycltfm.com/static/uploads/91.3_ayclt_fm_hd2/background.1779890739.png",
        "station": "91.3_ayclt_fm_hd2",
    },
    {
        "id": "913AycltFMHD3",
        "display": "1.3",
        "name": "91.3 Ayclt FM HD3",
        "description": "Dickinson's Texas #1 Hit Music Station",
        "icon": "https://radio.913aycltfm.com/static/uploads/91.3_ayclt_fm_hd3/background.1779890763.png",
        "station": "91.3_ayclt_fm_hd3",
    },
    {
        "id": "913AycltFMLiveStudioCam",
        "display": "1.4",
        "name": "91.3 Ayclt FM Live Studio Cam",
        "description": "91.3 Ayclt FM Live Studio Cam",
        "icon": "https://radio.913aycltfm.com/static/uploads/91.3_ayclt_fm/background.1779890712.png",
        "station": None,
    },
    {
        "id": "TheMidWestPlainsman",
        "display": "1.6",
        "name": "The Mid West Plainsman",
        "description": (
            "The Mid West Plainsman Is A Media Broadcast Content Creator "
            "In Waterloo, Iowa Covering Everything In The Cedar Valley "
            "Corridor and Central Iowa"
        ),
        "icon": "https://mp3tourl.com/images/1790116455920-0030dd1a-85d7-401a-bb1b-8cdb4160da9a.png",
        "station": None,
    },
]


# ============================================================
# HTTP HELPERS
# ============================================================

def fetch_json(url):
    """
    Download JSON from a URL.
    """
    print(f"Fetching: {url}")

    request = Request(
        url,
        headers={
            "User-Agent": "91.3-Ayclt-FM-EPG/1.0",
            "Accept": "application/json, text/plain, */*",
        },
    )

    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8-sig")
            return json.loads(raw)

    except HTTPError as exc:
        print(f"HTTP error {exc.code}: {url}")
        return None

    except URLError as exc:
        print(f"URL error: {exc.reason}")
        return None

    except Exception as exc:
        print(f"Request failed: {exc}")
        return None


# ============================================================
# DATE/TIME HELPERS
# ============================================================

def parse_datetime(value):
    """
    Convert many common AzuraCast date formats into
    timezone-aware datetime values.
    """

    if value is None:
        return None

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(
                value,
                tz=ZoneInfo("UTC")
            ).astimezone(TIMEZONE)
        except Exception:
            return None

    value = str(value).strip()

    if not value:
        return None

    # Unix timestamp stored as text
    if value.isdigit():
        try:
            number = int(value)

            # Milliseconds
            if number > 100000000000:
                number = number / 1000

            return datetime.fromtimestamp(
                number,
                tz=ZoneInfo("UTC")
            ).astimezone(TIMEZONE)

        except Exception:
            pass

    # ISO-8601 formats
    try:
        iso_value = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_value)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TIMEZONE)

        return dt.astimezone(TIMEZONE)

    except Exception:
        pass

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=TIMEZONE)
        except Exception:
            continue

    return None


def xmltv_datetime(dt):
    """
    XMLTV format:
    YYYYMMDDHHMMSS -0500
    or
    YYYYMMDDHHMMSS -0600
    depending on daylight saving time.
    """

    dt = dt.astimezone(TIMEZONE)

    offset = dt.utcoffset()

    if offset is None:
        offset = timedelta(0)

    total_minutes = int(offset.total_seconds() // 60)

    sign = "+" if total_minutes >= 0 else "-"

    total_minutes = abs(total_minutes)

    hours = total_minutes // 60
    minutes = total_minutes % 60

    return (
        f"{dt:%Y%m%d%H%M%S} "
        f"{sign}{hours:02d}{minutes:02d}"
    )


# ============================================================
# FIND SCHEDULE ARRAY
# ============================================================

def find_schedule_items(data):
    """
    AzuraCast/public schedule responses can have slightly
    different JSON structures depending on version.

    This function searches common structures for schedule items.
    """

    if data is None:
        return []

    if isinstance(data, list):
        return data

    if isinstance(data, dict):

        for key in [
            "schedule",
            "schedules",
            "data",
            "items",
            "results",
        ]:
            value = data.get(key)

            if isinstance(value, list):
                return value

            if isinstance(value, dict):

                for nested_key in [
                    "schedule",
                    "schedules",
                    "data",
                    "items",
                    "results",
                ]:
                    nested = value.get(nested_key)

                    if isinstance(nested, list):
                        return nested

    return []


# ============================================================
# FIND VALUES INSIDE SCHEDULE RECORDS
# ============================================================

def get_value(item, possible_keys):
    """
    Find the first useful value from a dictionary.
    """

    if not isinstance(item, dict):
        return None

    for key in possible_keys:
        if key in item and item[key] is not None:
            return item[key]

    return None


def get_schedule_title(item, fallback):
    """
    Try to identify the scheduled program/show name.
    """

    value = get_value(
        item,
        [
            "name",
            "title",
            "program_name",
            "show_name",
            "playlist_name",
            "streamer_name",
            "dj_name",
            "description",
        ],
    )

    if isinstance(value, dict):

        value = get_value(
            value,
            [
                "name",
                "title",
                "text",
            ],
        )

    if value:
        return str(value).strip()

    return fallback


def get_schedule_description(item, fallback):
    value = get_value(
        item,
        [
            "description",
            "desc",
            "details",
        ],
    )

    if value:
        return str(value).strip()

    return fallback


# ============================================================
# FETCH STATION SCHEDULE
# ============================================================

def fetch_station_schedule(station_slug):
    """
    Try the public AzuraCast schedule endpoint first.

    This matches the public schedule URLs used by the station.
    """

    url = (
        f"{AZURACAST_BASE_URL.rstrip('/')}"
        f"/public/{station_slug}/schedule"
    )

    data = fetch_json(url)

    if data is None:
        return []

    items = find_schedule_items(data)

    print(
        f"Found {len(items)} schedule records "
        f"for {station_slug}"
    )

    return items


# ============================================================
# CONVERT SCHEDULE RECORDS
# ============================================================

def convert_schedule_items(channel, raw_items):
    events = []

    for item in raw_items:

        if not isinstance(item, dict):
            continue

        start_value = get_value(
            item,
            [
                "start",
                "start_time",
                "start_datetime",
                "startDateTime",
                "starts_at",
                "start_at",
            ],
        )

        end_value = get_value(
            item,
            [
                "end",
                "end_time",
                "end_datetime",
                "endDateTime",
                "ends_at",
                "end_at",
            ],
        )

        start = parse_datetime(start_value)
        end = parse_datetime(end_value)

        if start is None or end is None:
            continue

        if end <= start:
            continue

        title = get_schedule_title(
            item,
            channel["name"]
        )

        description = get_schedule_description(
            item,
            channel["description"]
        )

        events.append(
            {
                "channel_id": channel["id"],
                "channel_name": channel["name"],
                "title": title,
                "description": description,
                "start": start,
                "end": end,
                "icon": channel["icon"],
            }
        )

    return events


# ============================================================
# FALLBACK PROGRAM
# ============================================================

def create_fallback_event(channel, start, end):
    """
    Used only when a station has no readable schedule data.

    This prevents Jellyfin from receiving an empty channel.
    """

    return {
        "channel_id": channel["id"],
        "channel_name": channel["name"],
        "title": channel["name"],
        "description": channel["description"],
        "start": start,
        "end": end,
        "icon": channel["icon"],
    }


# ============================================================
# BUILD NON-AZURACAST CHANNELS
# ============================================================

def build_continuous_channel(channel, start, end):
    """
    Live Studio Cam and The Mid West Plainsman do not have
    AzuraCast station schedule IDs in this configuration.

    Create daily guide blocks for them.
    """

    events = []

    current = start.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )

    while current < end:

        block_end = current + timedelta(days=1)

        if block_end > end:
            block_end = end

        events.append(
            create_fallback_event(
                channel,
                current,
                block_end
            )
        )

        current = block_end

    return events


# ============================================================
# REMOVE OVERLAPS / SORT EVENTS
# ============================================================

def clean_events(events):
    events.sort(
        key=lambda event: (
            event["channel_id"],
            event["start"],
            event["end"],
        )
    )

    cleaned = []
    last_by_channel = {}

    for event in events:

        channel_id = event["channel_id"]

        previous = last_by_channel.get(channel_id)

        if previous is not None:

            # Skip duplicate/overlapping records
            if event["start"] < previous["end"]:

                if event["end"] <= previous["end"]:
                    continue

                event["start"] = previous["end"]

        if event["end"] <= event["start"]:
            continue

        cleaned.append(event)
        last_by_channel[channel_id] = event

    return cleaned


# ============================================================
# XML ESCAPING
# ============================================================

def safe_text(value):
    if value is None:
        return ""

    return html.escape(
        str(value),
        quote=False
    )


# ============================================================
# GENERATE XMLTV
# ============================================================

def generate_xml(events):
    root = ET.Element(
        "tv",
        {
            "generator-info-name": "RadioEPG"
        }
    )

    # --------------------------------------------------------
    # CHANNELS
    # --------------------------------------------------------

    for channel in CHANNELS:

        channel_element = ET.SubElement(
            root,
            "channel",
            {
                "id": channel["id"]
            }
        )

        ET.SubElement(
            channel_element,
            "display-name"
        ).text = channel["display"]

        ET.SubElement(
            channel_element,
            "display-name"
        ).text = channel["name"]

    # --------------------------------------------------------
    # PROGRAMMES
    # --------------------------------------------------------

    for event in events:

        programme = ET.SubElement(
            root,
            "programme",
            {
                "start": xmltv_datetime(event["start"]),
                "stop": xmltv_datetime(event["end"]),
                "channel": event["channel_id"],
            }
        )

        title = ET.SubElement(
            programme,
            "title",
            {
                "lang": "en"
            }
        )

        title.text = safe_text(
            event["title"]
        )

        desc = ET.SubElement(
            programme,
            "desc",
            {
                "lang": "en"
            }
        )

        desc.text = safe_text(
            event["description"]
        )

        if event.get("icon"):

            ET.SubElement(
                programme,
                "icon",
                {
                    "src": event["icon"]
                }
            )

    # Pretty formatting
    try:
        ET.indent(root, space="  ")
    except AttributeError:
        pass

    tree = ET.ElementTree(root)

    output_path = Path(XML_OUTPUT)

    tree.write(
        output_path,
        encoding="utf-8",
        xml_declaration=True
    )

    # Fix XML declaration / DOCTYPE
    xml_text = output_path.read_text(
        encoding="utf-8"
    )

    if xml_text.startswith(
        '<?xml version=\'1.0\' encoding=\'utf-8\'?>'
    ):
        xml_text = xml_text.replace(
            '<?xml version=\'1.0\' encoding=\'utf-8\'?>',
            '<?xml version="1.0" encoding="utf-8"?>',
            1
        )

    xml_text = xml_text.replace(
        '<?xml version="1.0" encoding="utf-8"?>',
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE tv SYSTEM "xmltv.dtd">',
        1
    )

    output_path.write_text(
        xml_text,
        encoding="utf-8"
    )

    print(
        f"XMLTV written to: {output_path}"
    )


# ============================================================
# GENERATE JSON
# ============================================================

def generate_json(events):
    output = []

    for event in events:

        output.append(
            {
                "channel_id": event["channel_id"],
                "station_name": event["channel_name"],
                "title": event["title"],
                "description": event["description"],
                "start": event["start"].isoformat(),
                "end": event["end"].isoformat(),
                "icon": event["icon"],
            }
        )

    Path(JSON_OUTPUT).write_text(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print(
        f"JSON written to: {JSON_OUTPUT}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("91.3 AYCLT FM EPG GENERATOR")
    print("=" * 60)

    now = datetime.now(TIMEZONE)

    start = now - timedelta(
        minutes=5
    )

    end = now + timedelta(
        days=DAYS_AHEAD
    )

    all_events = []

    # --------------------------------------------------------
    # AZURACAST STATIONS
    # --------------------------------------------------------

    for channel in CHANNELS:

        station_slug = channel.get(
            "station"
        )

        if not station_slug:
            continue

        print()
        print(
            f"Processing: {channel['name']}"
        )

        raw_items = fetch_station_schedule(
            station_slug
        )

        converted = convert_schedule_items(
            channel,
            raw_items
        )

        if converted:

            all_events.extend(
                converted
            )

        else:

            print(
                f"No readable schedule found for "
                f"{channel['name']}."
            )

            # Create daily fallback blocks.
            current = start.replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0
            )

            while current < end:

                block_end = current + timedelta(
                    days=1
                )

                if block_end > end:
                    block_end = end

                all_events.append(
                    create_fallback_event(
                        channel,
                        current,
                        block_end
                    )
                )

                current = block_end

    # --------------------------------------------------------
    # NON-AZURACAST CHANNELS
    # --------------------------------------------------------

    for channel in CHANNELS:

        if channel.get("station"):
            continue

        print()
        print(
            f"Creating continuous guide for: "
            f"{channel['name']}"
        )

        all_events.extend(
            build_continuous_channel(
                channel,
                start,
                end
            )
        )

    # --------------------------------------------------------
    # CLEAN
    # --------------------------------------------------------

    all_events = clean_events(
        all_events
    )

    print()
    print(
        f"Total EPG programmes: "
        f"{len(all_events)}"
    )

    # --------------------------------------------------------
    # WRITE FILES
    # --------------------------------------------------------

    generate_xml(
        all_events
    )

    generate_json(
        all_events
    )

    print()
    print("=" * 60)
    print("EPG GENERATION COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
