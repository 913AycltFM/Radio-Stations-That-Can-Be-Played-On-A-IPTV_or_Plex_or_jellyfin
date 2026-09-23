import json
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo


# ============================================================
# 91.3 AYCLT FM - AZURACAST XMLTV EPG GENERATOR
# Automatic DJ Schedule + Gap Filling
# ============================================================

AZURACAST_BASE_URL = "https://radio.913aycltfm.com"

# Central Time
TIMEZONE = ZoneInfo("America/Chicago")

# How far into the future the EPG should be generated
DAYS_AHEAD = 30

# Output files
XML_OUTPUT = "91.3_Ayclt_FM_radio_guide.xml"
JSON_OUTPUT = "epg.json"


# ============================================================
# AZURACAST STATIONS
# ============================================================

STATIONS = {
    "913AycltFM": "91.3_ayclt_fm",
    "913AycltFMHD2": "91.3_ayclt_fm_hd2",
    "913AycltFMHD3": "91.3_ayclt_fm_hd3",
}


# ============================================================
# IPTV / JELLYFIN CHANNELS
# ============================================================

CHANNELS = [
    {
        "id": "913AycltFM",
        "display": "1",
        "name": "91.3 Ayclt FM",
        "description": "Dickinson's Texas #1 Hit Music Station",
        "icon": (
            "https://radio.913aycltfm.com/static/uploads/"
            "91.3_ayclt_fm/background.1779890712.png"
        ),
    },

    {
        "id": "913AycltFMHD2",
        "display": "1.2",
        "name": "91.3 Ayclt FM HD2",
        "description": "Dickinson's Texas #1 Hit Music Station",
        "icon": (
            "https://radio.913aycltfm.com/static/uploads/"
            "91.3_ayclt_fm_hd2/background.1779890739.png"
        ),
    },

    {
        "id": "913AycltFMHD3",
        "display": "1.3",
        "name": "91.3 Ayclt FM HD3",
        "description": "Dickinson's Texas #1 Hit Music Station",
        "icon": (
            "https://radio.913aycltfm.com/static/uploads/"
            "91.3_ayclt_fm_hd3/background.1779890763.png"
        ),
    },

    {
        "id": "913AycltFMLiveStudioCam",
        "display": "1.4",
        "name": "91.3 Ayclt FM Live Studio Cam",
        "description": "91.3 Ayclt FM Live Studio Cam",
        "icon": (
            "https://radio.913aycltfm.com/static/uploads/"
            "91.3_ayclt_fm/background.1779890712.png"
        ),
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
        "icon": (
            "https://mp3tourl.com/images/"
            "1790116455920-0030dd1a-85d7-401a-bb1b-8cdb4160da9a.png"
        ),
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

    except URLError as error:
        print(f"URL ERROR: {error.reason}")

    except Exception as error:
        print(f"ERROR: {error}")

    return None


# ============================================================
# FIND THE SCHEDULE LIST
# ============================================================

def find_schedule_list(data):
    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    keys = [
        "schedule",
        "schedules",
        "data",
        "items",
        "results",
    ]

    for key in keys:
        value = data.get(key)

        if isinstance(value, list):
            return value

        if isinstance(value, dict):
            for nested_key in keys:
                nested = value.get(nested_key)

                if isinstance(nested, list):
                    return nested

    return []


# ============================================================
# GET A FIELD FROM A JSON OBJECT
# ============================================================

def get_field(item, names):
    if not isinstance(item, dict):
        return None

    for name in names:
        if name in item:
            value = item[name]

            if value is not None:
                return value

    return None


# ============================================================
# PARSE DATE / TIME
# ============================================================

def parse_datetime(value):
    if value is None:
        return None

    # Unix timestamp
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

    # Numeric timestamp
    if value.isdigit():
        try:
            timestamp = int(value)

            # Milliseconds
            if timestamp > 100000000000:
                timestamp /= 1000

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

    # Other common formats
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
# XMLTV DATE / TIME FORMAT
# ============================================================

def xmltv_datetime(dt):
    dt = dt.astimezone(TIMEZONE)

    offset = dt.utcoffset()

    if offset is None:
        offset = timedelta(0)

    minutes = int(offset.total_seconds() / 60)

    sign = "+" if minutes >= 0 else "-"

    minutes = abs(minutes)

    hours = minutes // 60
    mins = minutes % 60

    return (
        f"{dt:%Y%m%d%H%M%S} "
        f"{sign}{hours:02d}{mins:02d}"
    )


# ============================================================
# GET PROGRAM TITLE
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
        ],
    )

    if isinstance(value, dict):
        value = get_field(
            value,
            [
                "name",
                "title",
            ],
        )

    if value:
        return str(value).strip()

    return channel_name


# ============================================================
# GET PROGRAM DESCRIPTION
# ============================================================

def get_description(item, channel_description):
    value = get_field(
        item,
        [
            "description",
            "desc",
        ],
    )

    if value:
        return str(value).strip()

    return channel_description


# ============================================================
# FETCH STATION SCHEDULE
# ============================================================

def fetch_station_schedule(station_slug):
    url = (
        f"{AZURACAST_BASE_URL}"
        f"/api/station/"
        f"{station_slug}"
        f"/schedule"
    )

    data = fetch_json(url)

    if data is None:
        return []

    schedules = find_schedule_list(data)

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

    minimum = now - timedelta(minutes=10)

    maximum = (
        now +
        timedelta(days=DAYS_AHEAD)
    )

    for item in schedules:

        if not isinstance(item, dict):
            continue

        # ----------------------------------------------------
        # START TIME
        # ----------------------------------------------------

        start_value = get_field(
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

        # ----------------------------------------------------
        # END TIME
        # ----------------------------------------------------

        end_value = get_field(
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

        if end < minimum:
            continue

        if start > maximum:
            continue

        if start < minimum:
            start = minimum

        if end > maximum:
            end = maximum

        events.append(
            {
                "channel_id": channel["id"],
                "channel_name": channel["name"],
                "title": get_program_title(
                    item,
                    channel["name"],
                ),
                "description": get_description(
                    item,
                    channel["description"],
                ),
                "start": start,
                "end": end,
                "icon": channel["icon"],
                "fallback": False,
            }
        )

    return events


# ============================================================
# FILL ALL UNSCHEDULED GAPS
#
# IMPORTANT:
# The filler uses:
#
# TITLE:
#     Channel name
#
# DESCRIPTION:
#     Normal channel description
#
# No "No scheduled DJ or program" text is added.
# ============================================================

def add_filler_blocks(result, channel, start_time, end_time):
    """
    Add filler in 30-minute blocks.

    XMLTV/Jellyfin handles many regular, fixed-length programmes
    better than one enormous filler programme.
    """
    current = start_time
    block_size = timedelta(minutes=30)

    while current < end_time:
        block_end = min(current + block_size, end_time)

        result.append(
            {
                "channel_id": channel["id"],
                "channel_name": channel["name"],
                "title": channel["name"],
                "description": channel["description"],
                "start": current,
                "end": block_end,
                "icon": channel["icon"],
                "fallback": True,
            }
        )

        current = block_end


def fill_schedule_gaps(
    channel,
    events,
    start_time,
    end_time,
):
    """
    Keep real AzuraCast programmes and fill every unscheduled gap
    with 30-minute filler programmes.

    This guarantees continuous EPG coverage without one-second
    programmes or huge multi-day filler blocks.
    """
    result = []

    events = sorted(
        events,
        key=lambda x: (x["start"], x["end"]),
    )

    current = start_time

    for event in events:
        event_start = max(event["start"], start_time)
        event_end = min(event["end"], end_time)

        if event_end <= start_time:
            continue

        if event_start >= end_time:
            break

        # Ignore an event completely covered by an earlier event.
        if event_end <= current:
            continue

        # If schedules overlap, trim the later event so the XMLTV
        # timeline remains continuous and non-overlapping.
        if event_start < current:
            event_start = current

        # Fill the gap before the real programme in 30-minute blocks.
        if event_start > current:
            add_filler_blocks(
                result,
                channel,
                current,
                event_start,
            )

        if event_end > event_start:
            actual_event = dict(event)
            actual_event["start"] = event_start
            actual_event["end"] = event_end
            actual_event["fallback"] = False
            result.append(actual_event)
            current = event_end

    # Fill everything after the final real programme.
    if current < end_time:
        add_filler_blocks(
            result,
            channel,
            current,
            end_time,
        )

    return result


# ============================================================
# CHANNELS WITHOUT AZURACAST SCHEDULES
# ============================================================

def create_no_schedule_channel(
    channel,
    start_time,
    end_time,
):
    return [
        {
            "channel_id": channel["id"],
            "channel_name": channel["name"],

            # TITLE = CHANNEL NAME
            "title": channel["name"],

            # DESCRIPTION = NORMAL CHANNEL DESCRIPTION
            "description": channel["description"],

            "start": start_time,
            "end": end_time,

            "icon": channel["icon"],

            "fallback": True,
        }
    ]


# ============================================================
# CLEAN DUPLICATE EVENTS
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
# GENERATE XMLTV
# ============================================================

def generate_xml(events):

    root = ET.Element(
        "tv",
        {
            "generator-info-name": "RadioEPG"
        },
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
            },
        )

        ET.SubElement(
            channel_element,
            "display-name",
        ).text = channel["display"]

        ET.SubElement(
            channel_element,
            "display-name",
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
            },
        )

        ET.SubElement(
            programme,
            "title",
            {
                "lang": "en"
            },
        ).text = event["title"]

        ET.SubElement(
            programme,
            "desc",
            {
                "lang": "en"
            },
        ).text = event["description"]

        if event.get("icon"):

            ET.SubElement(
                programme,
                "icon",
                {
                    "src": event["icon"]
                },
            )

    # --------------------------------------------------------
    # FORMAT XML
    # --------------------------------------------------------

    try:
        ET.indent(
            root,
            space="  ",
        )

    except AttributeError:
        pass

    tree = ET.ElementTree(root)

    path = Path(XML_OUTPUT)

    tree.write(
        path,
        encoding="utf-8",
        xml_declaration=True,
    )

    xml = path.read_text(
        encoding="utf-8"
    )

    # Normalize XML declaration
    xml = xml.replace(
        '<?xml version=\'1.0\' encoding=\'utf-8\'?>',
        '<?xml version="1.0" encoding="utf-8"?>',
        1,
    )

    # Add XMLTV DOCTYPE
    if "<!DOCTYPE tv SYSTEM" not in xml:

        xml = xml.replace(
            '<?xml version="1.0" encoding="utf-8"?>',

            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<!DOCTYPE tv SYSTEM "xmltv.dtd">',

            1,
        )

    path.write_text(
        xml,
        encoding="utf-8",
    )

    print(
        f"Created: {XML_OUTPUT}"
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
                "fallback": event["fallback"],
            }
        )

    Path(JSON_OUTPUT).write_text(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(
        f"Created: {JSON_OUTPUT}"
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
            "XML validation successful."
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

    print(
        "91.3 AYCLT FM - AZURACAST XMLTV EPG"
    )

    print(
        "AUTOMATIC DJ SCHEDULE + GAP FILL"
    )

    print("=" * 70)

    now = datetime.now(
        TIMEZONE
    )

    start_time = (
        now -
        timedelta(minutes=10)
    )

    end_time = (
        now +
        timedelta(days=DAYS_AHEAD)
    )

    all_events = []

    # ========================================================
    # PROCESS AZURACAST STATIONS
    # ========================================================

    for channel in CHANNELS:

        channel_id = channel["id"]

        # Only process channels connected to AzuraCast
        if channel_id not in STATIONS:
            continue

        station_slug = STATIONS[
            channel_id
        ]

        print()

        print("-" * 70)

        print(
            f"PROCESSING: "
            f"{channel['name']}"
        )

        schedules = fetch_station_schedule(
            station_slug
        )

        actual_events = convert_schedule(
            channel,
            schedules,
        )

        print(
            f"Actual scheduled programs: "
            f"{len(actual_events)}"
        )

        filled_events = fill_schedule_gaps(
            channel,
            actual_events,
            start_time,
            end_time,
        )

        print(
            f"Programs after gap filling: "
            f"{len(filled_events)}"
        )

        all_events.extend(
            filled_events
        )

    # ========================================================
    # LIVE STUDIO CAM
    # ========================================================

    live_cam = next(
        channel
        for channel in CHANNELS
        if channel["id"]
        == "913AycltFMLiveStudioCam"
    )

    print()

    print(
        "LIVE STUDIO CAM: "
        "Using 91.3 Ayclt FM schedule."
    )

    # The Studio Cam uses the same programming schedule as
    # the main 91.3 Ayclt FM channel.
    fm_channel = next(
        channel
        for channel in CHANNELS
        if channel["id"] == "913AycltFM"
    )

    fm_schedules = fetch_station_schedule(
        STATIONS["913AycltFM"]
    )

    fm_events = convert_schedule(
        fm_channel,
        fm_schedules,
    )

    studio_events = []

    for event in fm_events:
        studio_event = dict(event)
        studio_event["channel_id"] = live_cam["id"]
        studio_event["channel_name"] = live_cam["name"]
        studio_event["icon"] = live_cam["icon"]
        studio_events.append(studio_event)

    studio_events = fill_schedule_gaps(
        live_cam,
        studio_events,
        start_time,
        end_time,
    )

    print(
        f"Studio Cam programs after FM schedule sync: "
        f"{len(studio_events)}"
    )

    all_events.extend(
        studio_events
    )

    # ========================================================
    # THE MID WEST PLAINSMAN
    # ========================================================

    plainsman = next(
        channel
        for channel in CHANNELS
        if channel["id"]
        == "TheMidWestPlainsman"
    )

    print()

    print(
        "THE MID WEST PLAINSMAN: "
        "No AzuraCast schedule configured."
    )

    all_events.extend(
        create_no_schedule_channel(
            plainsman,
            start_time,
            end_time,
        )
    )

    # ========================================================
    # CLEAN EVENTS
    # ========================================================

    all_events = clean_events(
        all_events
    )

    print()

    print(
        f"TOTAL PROGRAMMES: "
        f"{len(all_events)}"
    )

    # ========================================================
    # GENERATE FILES
    # ========================================================

    generate_xml(
        all_events
    )

    generate_json(
        all_events
    )

    # ========================================================
    # VALIDATE
    # ========================================================

    if not validate_xml():

        raise SystemExit(
            "EPG generation failed."
        )

    print()

    print(
        "EPG GENERATION COMPLETE"
    )

    print("=" * 70)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()