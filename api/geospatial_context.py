import pandas as pd
import re
from pathlib import Path
from typing import Dict, Optional, List
import requests
import math
import datetime
from collections import defaultdict
import json
import os

_geocoding_data = None


def get_mapbox_coordinates(location_name: str) -> Optional[Dict]:
    """
    MAPBOX INTEGRATION PLACEHOLDER

    Returns:
        {"lat": 42.12345, "lon": -71.12345} or None

    """
    MAPBOX_ACCESS_TOKEN = os.getenv("MAPBOX_TOKEN")
    tnt_bbox = "-71.081784,42.284182,-71.071601,42.293255"

    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{location_name}.json"
    params = {"bbox": tnt_bbox, "access_token": MAPBOX_ACCESS_TOKEN, "limit": 1}

    try:
        response = requests.get(url, params=params)
        data = response.json()

        if "features" in data and len(data["features"]) > 0:
            coordinates = data["features"][0]["geometry"]["coordinates"]
            return coordinates  # Returns as [longitude, latitude]
        return None

    except Exception as e:
        print(f"Error geocoding location with mapbox: {e}")
        return None


_geocoding_data = None


def _load_geocoding_data(datastore_path: Path) -> pd.DataFrame:
    global _geocoding_data

    if _geocoding_data is None:
        try:
            csv_path = datastore_path / "geocoding-community-assets.csv"
            if csv_path.exists():
                _geocoding_data = pd.read_csv(csv_path)
            else:
                _geocoding_data = pd.DataFrame()
        except Exception as e:
            _geocoding_data = pd.DataFrame()

    return _geocoding_data


def get_location_from_llm(
    message: str, api_base_url: str, api_key: str
) -> Optional[Dict]:

    try:
        headers = {"RethinkAI-API-Key": api_key, "Content-Type": "application/json"}

        response = requests.post(
            f"{api_base_url}/chat/identify_places",
            json={"message": message},
            headers=headers,
        )

        if response.status_code == 200:
            llm_result = response.json()

            if isinstance(llm_result, str):
                if llm_result.strip() == "No locations found.":
                    return None
                try:
                    llm_result = json.loads(llm_result)
                except:
                    return None

            if isinstance(llm_result, dict):
                if "locations" in llm_result:
                    return llm_result
                else:

                    return {
                        "locations": llm_result if isinstance(llm_result, list) else []
                    }

            return None
        else:
            print(f"LLM endpoint error: {response.status_code}")
            return None

    except Exception as e:
        print(f"Error calling LLM endpoint: {e}")
        return None


def _normalize_text(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\bavenue\b", "ave", text)
    text = re.sub(r"\bstreet\b", "st", text)
    text = re.sub(r"\broad\b", "rd", text)
    text = re.sub(r"\bboulevard\b", "blvd", text)
    return text


def _get_all_location_names(geocoding_data: pd.DataFrame) -> list:
    all_locations = []

    for _, row in geocoding_data.iterrows():
        primary_name = str(row["Name"]).strip()
        if primary_name and primary_name != "nan":
            all_locations.append(
                {"name": primary_name, "lat": row["Latitude"], "lon": row["Longitude"]}
            )

        alt_names = str(row["Alternate Names"]).strip()
        if alt_names and alt_names != "nan":
            for alt_name in alt_names.split(","):
                alt_name = alt_name.strip()
                if alt_name:
                    all_locations.append(
                        {
                            "name": alt_name,
                            "lat": row["Latitude"],
                            "lon": row["Longitude"],
                        }
                    )

    all_locations.sort(key=lambda x: len(x["name"]), reverse=True)
    return all_locations


def match_llm_location_to_assets(
    llm_location_name: str, datastore_path: Path
) -> Optional[Dict]:
    try:
        geocoding_data = _load_geocoding_data(datastore_path)
        if geocoding_data.empty:
            return None

        all_locations = _get_all_location_names(geocoding_data)
        location_normalized = _normalize_text(llm_location_name)

        best_match = None
        best_score = 0

        for loc in all_locations:
            raw_name = loc["name"]
            loc_norm = _normalize_text(raw_name)
            tokens = loc_norm.split()

            # Exact match first
            if location_normalized == loc_norm:
                return {"name": raw_name, "lat": loc["lat"], "lon": loc["lon"]}

            # Partial match
            for n in range(len(tokens), 0, -1):
                prefix = " ".join(tokens[:n])
                if prefix in location_normalized or location_normalized in prefix:
                    score = len(prefix) / len(loc_norm)
                    if score > best_score:
                        best_score = score
                        best_match = {
                            "name": raw_name,
                            "lat": loc["lat"],
                            "lon": loc["lon"],
                        }
                    break

        return best_match

    except Exception as e:
        print(f"Error in location matching: {e}")
        return None


def extract_location_and_intent_enhanced(
    message: str, api_base_url: str, api_key: str, datastore_path: Path
) -> Optional[Dict]:

    # Try LLM for location detection and intent
    llm_result = get_location_from_llm(message, api_base_url, api_key)

    if not llm_result:
        return None

    # Extract LLM results
    if isinstance(llm_result, dict):
        locations_list = llm_result.get("locations", [])
        llm_intent = llm_result.get("intent", "general")
    else:
        locations_list = llm_result if isinstance(llm_result, list) else []
        llm_intent = "general"

    if not locations_list:
        return None

    first_location = locations_list[0]
    location_name = first_location.get("name", "")

    matched_location = match_llm_location_to_assets(location_name, datastore_path)

    if not matched_location:
        print(f"No coordinates found in community assets for: {location_name}")

        # MAPBOX INTEGRATION (placeholder)
        mapbox_coords = get_mapbox_coordinates(location_name)
        if mapbox_coords:
            print(f"Got coordinates: {mapbox_coords}")
            matched_location = {
                "name": location_name,
                "lat": mapbox_coords["lat"],
                "lon": mapbox_coords["lon"],
            }
        else:
            return None

    message_normalized = _normalize_text(message)
    proximity_triggers = ["near", "around", "nearby", "by", "close to", "within"]
    is_near_query = any(tok in message_normalized for tok in proximity_triggers)

    intent = llm_intent

    location_info = {
        "location": matched_location["name"],
        "intent": intent,
        "is_near_query": is_near_query,
        "showMap": True,
        "location_coords": {
            "lat": matched_location["lat"],
            "lon": matched_location["lon"],
        },
    }

    return location_info


def build_local_context(
    location: str,
    intent: str,
    location_coords: Dict,
    is_near_query: bool,
    api_base_url: str,
    api_key: str,
    datastore_path: Path,
    message: str = "",
) -> List[str]:

    context = []

    radius = None
    if message:
        pattern = re.compile(
            r"\bwithin\s*([\d\.]+)\s*"
            r"(kilometers?|km|meters?|m|yards?|yd|feet|foot|ft)\b",
            re.IGNORECASE,
        )

        m = pattern.search(message)
        if m:
            val = float(m.group(1))
            unit = m.group(2).lower()
            if unit.startswith("km") or "kilometer" in unit:
                radius = val * 1000
            elif unit.startswith("m") and unit != "mi":
                radius = val
            elif "yd" in unit or "yard" in unit or "yards" in unit:
                radius = val * 0.9144
            elif unit in ("ft", "foot", "feet"):
                radius = val * 0.3048

    if radius is None:
        lower = location.lower()
        if any(w in lower for w in ["ave", "avenue", "st", "street"]):
            radius = 300 if is_near_query else 100
        elif any(w in lower for w in ["square", "plaza"]):
            radius = 200 if is_near_query else 50
        else:
            radius = 100 if is_near_query else 30

    radius = int(radius)
    print("Radius:", radius)
    lat = location_coords["lat"]
    lon = location_coords["lon"]

    context.append(
        f"EXACT DATA for {location} within {radius} meters - this is the complete dataset for your query. IMPORTANT: Mention the community transcripts in your response if there are any in local context:"
    )

    try:
        headers = {"RethinkAI-API-Key": api_key}

        response_911 = requests.get(
            f"{api_base_url}/data/query",
            params={
                "request": "911_shots_fired",
                "output_type": "json",
                "is_spatial": "true",
            },
            headers=headers,
        )

        if response_911.status_code == 200:
            shots_data = response_911.json()
            local_shots = []
            for shot in shots_data:
                if "latitude" in shot and "longitude" in shot:
                    shot_lat, shot_lon = float(shot["latitude"]), float(
                        shot["longitude"]
                    )
                    lat1, lon1, lat2, lon2 = map(
                        math.radians, [lat, lon, shot_lat, shot_lon]
                    )
                    dlat, dlon = lat2 - lat1, lon2 - lon1
                    a = (
                        math.sin(dlat / 2) ** 2
                        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
                    )
                    distance = 6371000 * 2 * math.asin(math.sqrt(a))

                    if distance <= radius:
                        local_shots.append(shot)

            if local_shots:
                shots_by_year = defaultdict(lambda: {"total": 0, "confirmed": 0})
                for s in local_shots:
                    date_str = s.get("date", "")
                    try:
                        dt = datetime.datetime.fromisoformat(date_str)
                    except ValueError:
                        try:
                            dt = datetime.datetime.strptime(
                                date_str, "%a, %d %b %Y %H:%M:%S GMT"
                            )
                        except ValueError:
                            continue
                    yr = dt.year
                    shots_by_year[yr]["total"] += 1
                    if s.get("ballistics_evidence") == 1:
                        shots_by_year[yr]["confirmed"] += 1

                context.append("Shots fired breakdown by year:")
                for yr in sorted(shots_by_year):
                    data = shots_by_year[yr]
                    context.append(
                        f"- {yr}: {data['total']} incidents, {data['confirmed']} confirmed"
                    )
            else:
                context.append(
                    f"No shots fired incidents found within {radius}m of {location}."
                )

        response_hom = requests.get(
            f"{api_base_url}/data/query",
            params={
                "request": "911_homicides_and_shots_fired",
                "output_type": "json",
                "is_spatial": "true",
            },
            headers=headers,
        )
        if response_hom.status_code == 200:
            hom_data = response_hom.json()
            local_homs = []
            for ev in hom_data:
                if "latitude" in ev and "longitude" in ev and "date" in ev:
                    lat2, lon2 = float(ev["latitude"]), float(ev["longitude"])
                    # haversine calculation
                    φ1, λ1, φ2, λ2 = map(math.radians, [lat, lon, lat2, lon2])
                    dφ, dλ = φ2 - φ1, λ2 - λ1
                    a = (
                        math.sin(dφ / 2) ** 2
                        + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
                    )
                    dist = 6371000 * 2 * math.asin(math.sqrt(a))
                    if dist <= radius:
                        local_homs.append(ev)

            if local_homs:
                homs_by_year = defaultdict(int)
                for h in local_homs:
                    dt = None
                    try:
                        dt = datetime.datetime.fromisoformat(h["date"])
                    except ValueError:
                        try:
                            dt = datetime.datetime.strptime(
                                h["date"], "%a, %d %b %Y %H:%M:%S GMT"
                            )
                        except:
                            continue
                    homs_by_year[dt.year] += 1

                context.append("Homicides breakdown by year:")
                for yr in sorted(homs_by_year):
                    context.append(f"- {yr}: {homs_by_year[yr]} homicides")
            else:
                context.append(
                    f"No homicide incidents found within {radius}m of {location}."
                )

        response_311 = requests.get(
            f"{api_base_url}/data/query",
            params={
                "request": "311_by_geo",
                "category": "all",
                "output_type": "json",
                "is_spatial": "true",
            },
            headers=headers,
        )

        if response_311.status_code == 200:
            data_311 = response_311.json()
            local_311 = []
            for incident in data_311:
                if "latitude" in incident and "longitude" in incident:
                    inc_lat, inc_lon = float(incident["latitude"]), float(
                        incident["longitude"]
                    )
                    lat1, lon1, lat2, lon2 = map(
                        math.radians, [lat, lon, inc_lat, inc_lon]
                    )
                    dlat, dlon = lat2 - lat1, lon2 - lon1
                    a = (
                        math.sin(dlat / 2) ** 2
                        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
                    )
                    distance = 6371000 * 2 * math.asin(math.sqrt(a))  # meters

                    if distance <= radius:
                        local_311.append(incident)

            if local_311:
                intent_lower = intent.lower()
                intent_related = []

                for incident in local_311:
                    incident_type = incident.get("type", "").lower()
                    if intent_lower in incident_type:
                        intent_related.append(incident)

                if intent_related:
                    type_counts = {}
                    for incident in intent_related:
                        incident_type = incident.get("type", "Unknown")
                        type_counts[incident_type] = (
                            type_counts.get(incident_type, 0) + 1
                        )

                    context.append(f"311 complaints about {intent} within {radius}m:")
                    for incident_type, count in sorted(
                        type_counts.items(), key=lambda x: x[1], reverse=True
                    )[:3]:
                        context.append(f"- {count} reports of {incident_type}")
                else:
                    type_counts = {}
                    for incident in local_311:
                        incident_type = incident.get("type", "Unknown")
                        type_counts[incident_type] = (
                            type_counts.get(incident_type, 0) + 1
                        )

                    context.append(f"Other 311 complaints within {radius}m:")
                    for incident_type, count in sorted(
                        type_counts.items(), key=lambda x: x[1], reverse=True
                    )[:3]:
                        context.append(f"- {count} reports of {incident_type}")
            else:
                context.append(
                    f"No 311 complaints found within {radius}m of {location}."
                )

        if datastore_path.exists():
            txt_files = [
                f
                for f in datastore_path.iterdir()
                if f.suffix.lower() == ".txt" and not f.name.startswith(".")
            ]

            location_lower = location.lower()
            intent_lower = intent.lower()
            relevant_quotes = []

            for txt_file in txt_files:
                try:
                    content = txt_file.read_text(encoding="utf-8")
                    lines = [
                        line.strip() for line in content.split("\n") if line.strip()
                    ]

                    for line in lines:
                        line_lower = line.lower()
                        if location_lower in line_lower and intent_lower in line_lower:
                            relevant_quotes.append(line)
                        elif location_lower in line_lower:
                            relevant_quotes.append(line)

                except Exception as e:
                    print(f"Error reading {txt_file}: {e}")

            if relevant_quotes:
                context.append("Community Transcripts:")
                priority_quotes = [
                    q
                    for q in relevant_quotes
                    if location_lower in q.lower() and intent_lower in q.lower()
                ]
                if priority_quotes:
                    context.extend([f"- {q}" for q in priority_quotes[:2]])
                else:
                    context.extend([f"- {q}" for q in relevant_quotes[:2]])

        if len(context) <= 1:
            context.append(
                f"No local incident data found within {radius}m of {location}."
            )
            context.append(
                f"This location appears to have no recorded incidents in the immediate vicinity."
            )

    except Exception as e:
        print(f"Error building local context: {e}")
        context.append(f"Error retrieving data for {location}")

    return context


def get_map_preview_data(
    location_coords: Dict, is_near_query: bool, location_name: str = ""
) -> Dict:
    lat = location_coords["lat"]
    lon = location_coords["lon"]

    zoom = 17 if is_near_query else 18

    lat_offset = 0.002
    lon_offset = 0.002 / abs(lat / 90)

    return {
        "center": {"lat": lat, "lon": lon},
        "zoom": zoom,
        "bounds": {
            "north": lat + lat_offset,
            "south": lat - lat_offset,
            "east": lon + lon_offset,
            "west": lon - lon_offset,
        },
        "marker": {"lat": lat, "lon": lon, "title": location_name or "Location"},
    }


def construct_prompt(question: str, context: List[str]) -> str:
    """Keep this function as is"""
    if not context or len(context) <= 1:
        return question

    prompt_parts = []
    prompt_parts.append("Location-specific data (use this to answer the question):")
    for item in context[1:]:
        prompt_parts.append(item)

    prompt_parts.append("")
    prompt_parts.append("Question:")
    prompt_parts.append(question)

    return "\n".join(prompt_parts)


def process_geospatial_message(
    message: str, datastore_path: Path, api_base_url: str, api_key: str
) -> Dict:
    """
    Enhanced main function using LLM endpoint
    """
    try:
        location_info = extract_location_and_intent_enhanced(
            message, api_base_url, api_key, datastore_path
        )

        if not location_info:
            return {"enhanced_prompt": message, "map_data": None}

        map_data = None
        if location_info.get("showMap"):
            map_data = get_map_preview_data(
                location_coords=location_info["location_coords"],
                is_near_query=location_info["is_near_query"],
                location_name=location_info["location"],
            )

        local_context = build_local_context(
            location=location_info["location"],
            intent=location_info["intent"],
            location_coords=location_info["location_coords"],
            is_near_query=location_info["is_near_query"],
            api_base_url=api_base_url,
            api_key=api_key,
            datastore_path=datastore_path,
            message=message,
        )
        print("Local Context: ", local_context)
        enhanced_prompt = construct_prompt(message, local_context)

        return {"enhanced_prompt": enhanced_prompt, "map_data": map_data}

    except Exception as e:
        print(f"Error in geospatial pipeline: {e}")
        return {"enhanced_prompt": message, "map_data": None}
