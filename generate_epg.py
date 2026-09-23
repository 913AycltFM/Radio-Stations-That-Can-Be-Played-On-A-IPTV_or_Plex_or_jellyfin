import json
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo


# ============================================================
# 91.3 AYCLT FM - AZURACAST XMLTV EPG GENERATOR
# ============================================================

AZURACAST_BASE_URL = "https://radio.913aycltfm.com"

TIMEZONE = ZoneInfo("America/Chicago")

# Number of days of schedule information to keep
DAYS_AHEAD = 30

# Output files
XML_OUTPUT = "91.3_Ayclt_ FM_radio_guide.xml"
JSON_OUTPUT = "epg.json"


# ============================================================
# AZURACAST SCHEDULE API ENDPOINTS
# ============================================================

STATIONS = {
    "913AycltFM": "91.3_ayclt_fm",
    "913AycltFMHD2": "91.3_ayclt_fm_hd2",
    "913AycltFMHD3": "91.3_ayclt_fm_hd3",
}


# ============================================================
# FIVE JELLYFIN / IPTV CHANNELS
# ============================================================

CHANNELS = [
    {
        "id": "913AycltFM",
        "display": "1",
        "name": "91.3 Ayclt FM",
        "description": "Dickinson's Texas #1 Hit Music Station",
        "icon": "https://radio.913aycltfm.com/static/uploads/91.3_ayclt_fm/background.1779890712.png",
    },

    {
        "id": "913AycltFMHD2",
        "display": "1.2",
        "name": "91.3 Ayclt FM HD2",
        "description": "Dickinson's Texas #1 Hit Music Station",
        "icon": "https://radio.913aycltfm.com/static/uploads/91.3_ayclt_fm_hd2/background.1779890739.png",
    },

    {
        "id": "913AycltFMHD3",
        "display": "1.3",
        "name": "91.3 Ayclt FM HD3",
        "description": "Dickinson's Texas #1 Hit Music Station",
        "icon": "https://radio.913aycltfm.com/static/uploads/91.3_ayclt_fm_hd3/background.1779890763.png",
    },

    {
        "id": "913AycltFMLiveStudioCam",
        "display": "1.4",
        "name": "91.3 Ayclt FM Live Studio Cam",
        "description": "91.3 Ayclt FM Live Studio Cam",
        "icon": "https://radio.913aycltfm.com/static/uploads/91.3_ayclt_fm/background.1779890712.png",
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
    },
]


# ============================================================
# FETCH JSON FROM AZURACAST
# ============================================================

def fetch_json(url):
    print(f"Fetching API: {url}")

    request = Request(
        url,
        headers={
            "User-Agent": "91.3-Ayclt-FM-EPG/1.0",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=30) as response:
            data = response.read().decode("utf-8-sig")
            return json.loads(data)

    except HTTPError as error:
        print(f"HTTP ERROR {error.code}: {url}")
        return None

    except URLError as error:
        print(f"URL ERROR: {error.reason}")
        return None

    except json.JSONDecodeError as error:
        print(f"JSON ERROR: {error}")
        return None

    except Exception as error:
        print(f"ERROR: {error}")
        return None


# ============================================================
# PARSE AZURACAST DATE
# ============================================================

def parse_datetime(value):
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

    # Unix timestamp
    if value.isdigit():
        try:
            timestamp = int(value)

            if timestamp > 100000000000:
                timestamp = timestamp / 1000

            return datetime.fromtimestamp(
                timestamp,
                tz=ZoneInfo("UTC")
            ).astimezone(TIMEZONE)

        except Exception:
            pass

    # ISO 8601
    try:
        converted = value.replace("Z", "+00:00")

        dt = datetime.fromisoformat(converted)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TIMEZONE)

        return dt.astimezone(TIMEZONE)

    except Exception:
        pass

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=TIMEZONE)
        except Exception:
            continue

    return None


# ============================================================
# XMLTV DATE FORMAT
# ============================================================

def xmltv_datetime(dt):
    dt = dt.astimezone(TIMEZONE)

    offset = dt.utcoffset()

    if offset is None:
        offset = timedelta(0)

    total_minutes = int(
        offset.total_seconds() / 60
    )

    sign = "+" if total_minutes >= 0 else "-"

    total_minutes = abs(total_minutes)

    hours = total_minutes // 60
    minutes = total_minutes % 60

    return (
        f"{dt:%Y%m%d%H%M%S} "
        f"{sign}{hours:02d}{minutes:02d}"
    )


# ============================================================
# FIND SCHEDULE LIST
# ============================================================

def find_schedule_list(data):

    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    possible_keys = [
        "schedule",
        "schedules",
        "data",
        "items",
        "results",
    ]

    for key in possible_keys:

        value = data.get(key)

        if isinstance(value, list):
            return value

        if isinstance(value, dict):

            for nested_key in possible_keys:

                nested_value = value.get(nested_key)

                if isinstance(nested_value, list):
                    return nested_value

    return []


# ============================================================
# GET FIELD FROM SCHEDULE OBJECT
# ============================================================

def get_field(item, names):

    if not isinstance(item, dict):
        return None

    for name in names:

        if name in item and item[name] is not None:
            return item[name]

    return None


# ============================================================
# GET PROGRAM NAME
# ============================================================

def get_program_title(item, channel_name):

    value = get_field(
        item,
        [
            "name",
            "title",
            "program_name",
            "show_name",
            "playlist_name",
            "streamer_name",
            "dj_name",
        ]
    )

    if isinstance(value, dict):

        value = get_field(
            value,
            [
                "name",
                "title",
            ]
        )

    if value:
        return str(value).strip()

    return channel_name


# ============================================================
# GET DESCRIPTION
# ============================================================

def get_description(item, channel_description):

    value = get_field(
        item,
        [
            "description",
            "desc",
        ]
    )

    if value:
        return str(value).strip()

    return channel_description


# ============================================================
# GET START TIME
# ============================================================

def get_start(item):

    return get_field(
        item,
        [
            "start",
            "start_time",
            "start_datetime",
            "startDateTime",
            "starts_at",
            "start_at",
        ]
    )


# ============================================================
# GET END TIME
# ============================================================

def get_end(item):

    return get_field(
        item,
        [
            "end",
            "end_time",
            "end_datetime",
            "endDateTime",
            "ends_at",
            "end_at",
        ]
    )


# ============================================================
# FETCH ONE STATION'S SCHEDULE
# ============================================================

def fetch_station_schedule(station_slug):

    url = (
        f"{AZURACAST_BASE_URL}"
        f"/api/station/"
        f"{station_slug}"
        f"/schedule"
    )

    response = fetch_json(url)

    if response is None:
        return []

    schedules = find_schedule_list(response)

    print(
        f"Schedule records received: "
        f"{len(schedules)}"
    )

    return schedules


# ============================================================
# CONVERT AZURACAST SCHEDULE TO EPG EVENTS
# ============================================================

def convert_schedule(channel, schedules):

    events = []

    now = datetime.now(TIMEZONE)

    minimum_time = now - timedelta(minutes=10)

    maximum_time = now + timedelta(days=DAYS_AHEAD)

    for item in schedules:

        if not isinstance(item, dict):
            continue

        start_value = get_start(item)
        end_value = get_end(item)

        start = parse_datetime(start_value)
        end = parse_datetime(end_value)

        if start is None or end is None:
            continue

        if end <= start:
            continue

        # Ignore schedules completely outside our EPG window
        if end < minimum_time:
            continue

        if start > maximum_time:
            continue

        # Keep inside requested EPG window
        if start < minimum_time:
            start = minimum_time

        if end > maximum_time:
            end = maximum_time

        title = get_program_title(
            item,
            channel["name"]
        )

        description = get_description(
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
# SORT AND REMOVE DUPLICATES
# ============================================================

def clean_events(events):

    events.sort(
        key=lambda event: (
            event["channel_id"],
            event["start"],
            event["end"],
            event["title"],
        )
    )

    cleaned = []

    seen = set()

    for event in events:

        key = (
            event["channel_id"],
            event["start"].isoformat(),
            event["end"].isoformat(),
            event["title"],
        )

        if key in seen:
            continue

        seen.add(key)

        cleaned.append(event)

    return cleaned


# ============================================================
# XMLTV GENERATION
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
                "start": xmltv_datetime(
                    event["start"]
                ),
                "stop": xmltv_datetime(
                    event["end"]
                ),
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

        title.text = event["title"]

        description = ET.SubElement(
            programme,
            "desc",
            {
                "lang": "en"
            }
        )

        description.text = event["description"]

        if event.get("icon"):

            ET.SubElement(
                programme,
                "icon",
                {
                    "src": event["icon"]
                }
            )

    # Pretty XML
    try:
        ET.indent(
            root,
            space="  "
        )
    except AttributeError:
        pass

    tree = ET.ElementTree(root)

    output_path = Path(
        XML_OUTPUT
    )

    tree.write(
        output_path,
        encoding="utf-8",
        xml_declaration=True
    )

    # Add XMLTV DOCTYPE
    xml = output_path.read_text(
        encoding="utf-8"
    )

    xml = xml.replace(
        '<?xml version=\'1.0\' encoding=\'utf-8\'?>',
        '<?xml version="1.0" encoding="utf-8"?>',
        1
    )

    if "<!DOCTYPE tv SYSTEM" not in xml:

        xml = xml.replace(
            '<?xml version="1.0" encoding="utf-8"?>',
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<!DOCTYPE tv SYSTEM "xmltv.dtd">',
            1
        )

    output_path.write_text(
        xml,
        encoding="utf-8"
    )

    print(
        f"XMLTV created: {XML_OUTPUT}"
    )


# ============================================================
# JSON GENERATION
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

    Path(
        JSON_OUTPUT
    ).write_text(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print(
        f"JSON created: {JSON_OUTPUT}"
    )


# ============================================================
# VALIDATE XML
# ============================================================

def validate_xml():

    try:

        ET.parse(
            XML_OUTPUT
        )

        print(
            f"XML validation successful: "
            f"{XML_OUTPUT}"
        )

        return True

    except Exception as error:

        print(
            f"XML validation FAILED: {error}"
        )

        return False


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("91.3 AYCLT FM - AZURACAST XMLTV EPG")
    print("=" * 70)

    all_events = []

    # --------------------------------------------------------
    # PROCESS THE THREE AZURACAST STATIONS
    # --------------------------------------------------------

    for channel in CHANNELS:

        channel_id = channel["id"]

        if channel_id not in STATIONS:
            continue

        station_slug = STATIONS[
            channel_id
        ]

        print()
        print("-" * 70)
        print(
            f"Channel: {channel['name']}"
        )
        print(
            f"Station: {station_slug}"
        )

        schedules = fetch_station_schedule(
            station_slug
        )

        events = convert_schedule(
            channel,
            schedules
        )

        print(
            f"Usable EPG programmes: "
            f"{len(events)}"
        )

        all_events.extend(
            events
        )

    # --------------------------------------------------------
    # LIVE STUDIO CAM
    # --------------------------------------------------------
    #
    # No AzuraCast schedule API is configured for this channel.
    #
    # We intentionally DO NOT create fake programmes.
    #
    # --------------------------------------------------------

    print()
    print(
        "Live Studio Cam: no AzuraCast schedule configured."
    )

    # --------------------------------------------------------
    # THE MID WEST PLAINSMAN
    # --------------------------------------------------------
    #
    # No AzuraCast schedule API is configured for this channel.
    #
    # We intentionally DO NOT create fake programmes.
    #
    # --------------------------------------------------------

    print(
        "The Mid West Plainsman: "
        "no AzuraCast schedule configured."
    )

    # --------------------------------------------------------
    # CLEAN EVENTS
    # --------------------------------------------------------

    all_events = clean_events(
        all_events
    )

    print()
    print(
        f"TOTAL PROGRAMMES: "
        f"{len(all_events)}"
    )

    # --------------------------------------------------------
    # WRITE XML
    # --------------------------------------------------------

    generate_xml(
        all_events
    )

    # --------------------------------------------------------
    # WRITE JSON
    # --------------------------------------------------------

    generate_json(
        all_events
    )

    # --------------------------------------------------------
    # VALIDATE
    # --------------------------------------------------------

    if not validate_xml():

        raise SystemExit(
            "EPG generation failed XML validation."
        )

    print()
    print("=" * 70)
    print("EPG GENERATION COMPLETE")
    print("=" * 70)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
