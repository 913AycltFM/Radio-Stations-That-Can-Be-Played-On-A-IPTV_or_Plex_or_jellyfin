import json
from datetime import datetime, timedelta
from pathlib import Path
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
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
DAYS_AHEAD = 7

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

    max_attempts = 3
    retry_delays = (2, 5)

    for attempt in range(1, max_attempts + 1):
        try:
            with urlopen(request, timeout=30) as response:
                data = response.read().decode("utf-8-sig")
                return json.loads(data)

        except HTTPError as error:
            if error.code not in (429,) and not 500 <= error.code <= 599:
                raise RuntimeError(
                    f"AzuraCast API HTTP error {error.code}: {url}"
                ) from error

            if attempt == max_attempts:
                raise RuntimeError(
                    f"AzuraCast API HTTP error {error.code} after "
                    f"{max_attempts} attempts: {url}"
                ) from error

            delay = retry_delays[attempt - 1]
            print(
                f"Transient HTTP error {error.code}; retrying in {delay}s "
                f"({attempt + 1}/{max_attempts})..."
            )
            time.sleep(delay)

        except URLError as error:
            if attempt == max_attempts:
                raise RuntimeError(
                    f"AzuraCast API connection error after "
                    f"{max_attempts} attempts: {error.reason}"
                ) from error

            delay = retry_delays[attempt - 1]
            print(
                f"Transient connection error; retrying in {delay}s "
                f"({attempt + 1}/{max_attempts})..."
            )
            time.sleep(delay)

        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"AzuraCast API returned invalid JSON: {url}"
            ) from error

        except Exception as error:
            raise RuntimeError(
                f"AzuraCast API request failed: {error}"
            ) from error


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

    title = str(value).strip() if value else channel_name

    # Keep the programme title clean. The live state is stored
    # separately so a guide interface can render a dedicated
    # LIVE badge/box next to the programme title.
    return title


# ============================================================
# DETERMINE WHETHER AN AZURACAST ENTRY IS A LIVE DJ/STREAMER
# ============================================================

def is_live_program(item):
    streamer = get_field(
        item,
        [
            "streamer_name",
            "streamer",
            "dj_name",
        ],
    )

    if isinstance(streamer, dict):
        streamer = get_field(
            streamer,
            [
                "name",
                "title",
            ],
        )

    return bool(str(streamer).strip()) if streamer else False


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

def fetch_station_schedule(
    station_slug,
    start_date,
    end_date,
):
    """
    Fetch the full scheduled lineup for a date range.

    The plain /schedule endpoint is primarily an "upcoming schedule"
    feed and may return only a small number of near-term entries.
    Supplying start/end makes AzuraCast return the scheduled lineup
    for the requested dates, including recurring DJ/playlist blocks.

    We use 7-day chunks so the EPG request stays within a manageable
    date range.
    """
    schedules = []

    current_date = start_date

    while current_date <= end_date:
        chunk_end = min(
            current_date + timedelta(days=6),
            end_date,
        )

        query = urlencode(
            {
                "start": current_date.isoformat(),
                "end": chunk_end.isoformat(),
            }
        )

        url = (
            f"{AZURACAST_BASE_URL}"
            f"/api/station/"
            f"{station_slug}"
            f"/schedule?{query}"
        )

        data = fetch_json(url)

        # A failed API request must stop generation. Publishing a
        # filler-only EPG after an API outage could hide a real
        # schedule and replace the last known-good guide.
        chunk = find_schedule_list(data)
        schedules.extend(chunk)

        print(
            f"Schedule records received for "
            f"{current_date.isoformat()} through "
            f"{chunk_end.isoformat()}: "
            f"{len(chunk)}"
        )

        current_date = chunk_end + timedelta(days=1)

    print(
        f"Total schedule records received for "
        f"{station_slug}: {len(schedules)}"
    )

    return schedules


# ============================================================
# CONVERT AZURACAST SCHEDULE TO EPG EVENTS
# ============================================================

def convert_schedule(channel, schedules, minimum, maximum):
    events = []

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
                "live_program": is_live_program(item),
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
    Add filler in 60-minute blocks.

    XMLTV/Jellyfin receives regular, fixed-length hourly filler
    programmes whenever the channel has an unscheduled gap.
    """
    current = start_time
    block_size = timedelta(hours=1)
    utc = ZoneInfo("UTC")

    while current < end_time:
        # Advance in absolute time so the repeated hour at the
        # Central Time DST fallback is represented correctly.
        current_utc = current.astimezone(utc)
        block_end_utc = min(
            current_utc + block_size,
            end_time.astimezone(utc),
        )
        block_end = block_end_utc.astimezone(TIMEZONE)

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
    Build one authoritative, non-overlapping timeline for a channel.

    AzuraCast can return duplicate or overlapping schedule records.
    Real scheduled programmes are authoritative.  Filler is created
    only after those real programmes have been normalized, so a filler
    entry can never occupy the same time as a real programme.
    """
    result = []

    # --------------------------------------------------------
    # NORMALIZE REAL AZURACAST PROGRAMMES FIRST
    # --------------------------------------------------------
    scheduled = []

    for event in events:
        event_start = max(event["start"], start_time)
        event_end = min(event["end"], end_time)

        if event_end <= event_start:
            continue

        normalized = dict(event)
        normalized["start"] = event_start
        normalized["end"] = event_end
        normalized["fallback"] = False
        scheduled.append(normalized)

    # Sort by start time. For identical starts, keep the longer
    # programme first; this commonly collapses duplicate AzuraCast
    # records representing the same scheduled block.
    scheduled.sort(
        key=lambda x: (
            x["start"],
            -(x["end"] - x["start"]).total_seconds(),
            x["title"],
        )
    )

    real_events = []

    for event in scheduled:
        event_start = event["start"]
        event_end = event["end"]

        # An earlier real programme already covers this event.
        if real_events and event_start < real_events[-1]["end"]:
            previous = real_events[-1]

            # If both records start together, prefer the longer record.
            if event_start == previous["start"]:
                if event_end > previous["end"]:
                    real_events[-1] = event
                continue

            # Otherwise trim the overlapping portion from the later
            # programme. This prevents any real/real overlap.
            event_start = previous["end"]

            if event_end <= event_start:
                continue

            event = dict(event)
            event["start"] = event_start

        real_events.append(event)

    # --------------------------------------------------------
    # BUILD THE FINAL TIMELINE
    # --------------------------------------------------------
    current = start_time

    for event in real_events:
        event_start = event["start"]
        event_end = event["end"]

        # Fill only the genuine gap before the real programme.
        if event_start > current:
            add_filler_blocks(
                result,
                channel,
                current,
                event_start,
            )

        # Never allow a programme to move backwards.
        if event_end <= current:
            continue

        if event_start < current:
            event_start = current

        actual_event = dict(event)
        actual_event["start"] = event_start
        actual_event["end"] = event_end
        actual_event["fallback"] = False

        result.append(actual_event)
        current = event_end

    # Fill the remaining unscheduled time.
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
# VALIDATE TIMELINES
# ============================================================

def validate_timelines(events):
    """
    Verify that every channel has one non-overlapping timeline.

    XMLTV clients such as Jellyfin and Plex should never receive two
    programmes occupying the same channel/time range.
    """
    grouped = {}

    for event in events:
        grouped.setdefault(
            event["channel_id"],
            []
        ).append(event)

    errors = []

    for channel_id, channel_events in grouped.items():
        channel_events.sort(
            key=lambda event: (
                event["start"],
                event["end"],
            )
        )

        previous = None

        for event in channel_events:
            if event["end"] <= event["start"]:
                errors.append(
                    f"{channel_id}: invalid interval "
                    f"{event['start']} -> {event['end']}"
                )

            if previous is not None and event["start"] < previous["end"]:
                errors.append(
                    f"{channel_id}: overlap between "
                    f"'{previous['title']}' "
                    f"({previous['start']} -> {previous['end']}) "
                    f"and '{event['title']}' "
                    f"({event['start']} -> {event['end']})"
                )

            previous = event

    if errors:
        print("TIMELINE VALIDATION FAILED:")

        for error in errors:
            print(f"  - {error}")

        return False

    print(
        f"Timeline validation successful: "
        f"{len(grouped)} channels checked; "
        f"no overlapping programmes."
    )

    return True


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

        # XMLTV has no universal visual "LIVE box" element.
        # The standard category element is used as machine-readable
        # live metadata without polluting the programme title.
        if event.get("live"):
            ET.SubElement(
                programme,
                "category",
                {
                    "lang": "en"
                },
            ).text = "LIVE"

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
                # DJ/live entries get the explicit LIVE badge.
                # Regular programmes and filler have no badge.
                "fallback": event["fallback"],
                "live": event.get("live", False),
                "live_badge": "LIVE" if event.get("live", False) else "",
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

    # Align the rolling EPG to the start of the current hour.
    # This prevents the XML/JSON timestamps from changing every
    # time the 5-minute GitHub Actions job runs.
    start_time = now.replace(
        minute=0,
        second=0,
        microsecond=0,
    )

    end_time = (
        start_time +
        timedelta(days=DAYS_AHEAD)
    )

    # Fetch the previous calendar day too so overnight programmes
    # that cross midnight are not lost from the EPG.
    schedule_start_date = (
        start_time.date() -
        timedelta(days=1)
    )

    all_events = []
    schedule_cache = {}

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

        if station_slug not in schedule_cache:
            schedule_cache[station_slug] = fetch_station_schedule(
                station_slug,
                schedule_start_date,
                end_time.date(),
            )

        schedules = schedule_cache[station_slug]

        actual_events = convert_schedule(
            channel,
            schedules,
            start_time,
            end_time,
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
    # the main 91.3 Ayclt FM channel. Its LIVE metadata therefore
    # follows the corresponding FM programme.
    fm_channel = next(
        channel
        for channel in CHANNELS
        if channel["id"] == "913AycltFM"
    )

    fm_schedules = schedule_cache[STATIONS["913AycltFM"]]

    fm_events = convert_schedule(
        fm_channel,
        fm_schedules,
        start_time,
        end_time,
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
    # CALCULATE LIVE BADGE STATE
    # ========================================================
    #
    # LIVE rules:
    # - Current live DJ: LIVE
    # - Future live DJ: LIVE
    # - Past live DJ: LIVE
    # - Regular scheduled programme: no LIVE
    # - Filler: no LIVE
    #
    # Main 91.3 Ayclt FM and the Live Studio Cam use the live-DJ
    # schedule, so a scheduled DJ entry keeps LIVE metadata even
    # when it is in the future or past.
    #
    # HD2/HD3 are different: LIVE is only set while an actual
    # live DJ/streamer programme is airing right now.
    #
    # XMLTV cannot draw a visual box itself. The generator exposes
    # LIVE through the category element and JSON live/live_badge
    # fields for clients that support them.
    # ========================================================

    hd_channels = {"913AycltFMHD2", "913AycltFMHD3"}
    fm_channel_id = "913AycltFM"
    studio_channel_id = "913AycltFMLiveStudioCam"

    for event in all_events:
        channel_id = event["channel_id"]

        if channel_id in {fm_channel_id, studio_channel_id}:
            # FM and Studio Cam follow the DJ/streamer schedule.
            # Future and past DJ entries remain LIVE-labelled.
            event["live"] = bool(event.get("live_program", False))
        elif channel_id in hd_channels:
            # HD2/HD3 only show LIVE for the DJ/streamer that is
            # actually airing at the current moment.
            event["live"] = bool(
                event.get("live_program", False)
                and event["start"] <= now < event["end"]
            )
        else:
            # Regular programmes and filler do not get LIVE.
            event["live"] = False

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
    # FINAL TIMELINE VALIDATION
    # ========================================================

    if not validate_timelines(all_events):
        raise SystemExit(
            "EPG generation stopped because overlapping "
            "programmes were detected."
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