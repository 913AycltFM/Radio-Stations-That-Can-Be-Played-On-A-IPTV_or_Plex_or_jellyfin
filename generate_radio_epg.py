import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

# 1. STATION ENDPOINT MAPPINGS
STATION_CONFIGS = {
    "913AycltFM": {
        "url": "https://radio.913aycltfm.com/api/nowplaying/91.3_ayclt_fm",
        "name": "91.3 Ayclt FM",
        "desc": "Dickinson's Texas #1 Hit Music Station"
    },
    "913AycltFMHD2": {
        "url": "https://radio.913aycltfm.com/api/nowplaying/91.3_ayclt_fm_hd2",
        "name": "91.3 Ayclt FM HD2",
        "desc": "Now Playing on 91.3 Ayclt FM HD2"
    },
    "913AycltFMHD3": {
        "url": "https://radio.913aycltfm.com/api/nowplaying/91.3_ayclt_fm_hd3",
        "name": "91.3 Ayclt FM HD3",
        "desc": "Now Playing on 91.3 Ayclt FM HD3"
    }
}

# Output directly into the root directory of your GitHub repository
OUTPUT_XML_FILE = "epg.xml"  

def get_xmltv_timestamp(dt_obj):
    """Formats Python datetime to canonical XMLTV specification (-0500 Central Time)"""
    return dt_obj.strftime("%Y%m%d%H%M%S -0500")

def run_epg_generation():
    # Initialize Core XML Frame
    root = ET.Element("tv", {"generator-info-name": "RadioEPG"})
    
    # 2. GENERATE ALL INDEPENDENT CHANNEL HEADERS
    for ch_id, config in STATION_CONFIGS.items():
        ch_elem = ET.SubElement(root, "channel", {"id": ch_id})
        # Assign channel number markers (1, 2, or 3)
        num = "1" if ch_id == "913AycltFM" else ("2" if "HD2" in ch_id else "3")
        ET.SubElement(ch_elem, "display-name").text = num
        ET.SubElement(ch_elem, "display-name").text = config["name"]

    # 3. QUERY API ENDPOINTS SEQUENTIALLY
    for ch_id, config in STATION_CONFIGS.items():
        # Establish default localized live values for connection drops or talk blocks
        title = f"{config['name']} Live Stream"
        artist = "Dickinson, Texas"
        art_url = ""
        duration = 240  # Default 4-minute time block fallback
        start_epoch = int(datetime.now().timestamp())
        
        try:
            req = urllib.request.Request(config["url"], headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=8) as response:
                data = json.loads(response.read().decode())
                
                # Directly extract from the base root (Single-Station API layout)
                now_playing = data.get("now_playing", {})
                song = now_playing.get("song", {})
                
                if song:
                    title = song.get("title", title)
                    artist = song.get("artist", artist)
                    art_url = song.get("art", "")
                    
                duration = now_playing.get("duration", 240)
                start_epoch = now_playing.get("played_at", start_epoch)
        except Exception as e:
            print(f"Skipping or error fetching endpoint for {ch_id}: {e}")

        # Compute accurate program slot bounds
        start_time = datetime.fromtimestamp(start_epoch)
        stop_time = start_time + timedelta(seconds=duration)
        
        # Buffer safety window if system time pushes ahead of calculated track limits
        if datetime.now() > stop_time:
            stop_time = datetime.now() + timedelta(minutes=3)

        # 4. APPEND METADATA BLOCK TO THE ELEMENT TREE
        prog = ET.SubElement(root, "programme", {
            "start": get_xmltv_timestamp(start_time),
            "stop": get_xmltv_timestamp(stop_time),
            "channel": ch_id
        })
        
        ET.SubElement(prog, "title", {"lang": "en"}).text = title
        ET.SubElement(prog, "sub-title", {"lang": "en"}).text = artist
        ET.SubElement(prog, "desc", {"lang": "en"}).text = config["desc"]
        
        if art_url:
            ET.SubElement(prog, "icon", {"src": art_url})

    # Save compiled EPG straight to output file
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ", level=0)
    
    with open(OUTPUT_XML_FILE, "wb") as xml_out:
        xml_out.write(b'<?xml version="1.0" encoding="utf-8"?>\n')
        xml_out.write(b'<!DOCTYPE tv SYSTEM "xmltv.dtd">\n')
        tree.write(xml_out, encoding="utf-8", xml_declaration=False)
        print("EPG successfully generated for all channels.")

if __name__ == "__main__":
    run_epg_generation()
