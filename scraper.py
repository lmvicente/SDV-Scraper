"""
Stardew Valley Villager Scraper
Scrapes villager data from https://stardewvalleywiki.com/Villagers
Extracts: names, images, birthdays, gift preferences, and schedules
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import re
from datetime import datetime
from typing import Optional

# Constants
BASE_URL = "https://stardewvalleywiki.com"
VILLAGERS_URL = f"{BASE_URL}/Villagers"
REQUEST_DELAY = 0.5  # Be respectful to the wiki - wait between requests
HEADERS = {
    "User-Agent": "StardewValleyCompanionApp/1.0 (Educational Project)"
}

# Marriage candidates
BACHELORS = ["Alex", "Elliott", "Harvey", "Sam", "Sebastian", "Shane"]
BACHELORETTES = ["Abigail", "Emily", "Haley", "Leah", "Maru", "Penny"]
MARRIAGE_CANDIDATES = set(BACHELORS + BACHELORETTES)


def make_request(url: str) -> Optional[BeautifulSoup]:
    """Make a request to the wiki with rate limiting and error handling."""
    try:
        time.sleep(REQUEST_DELAY)
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        return BeautifulSoup(response.content, "lxml")
    except requests.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return None


def get_villager_list() -> list[dict]:
    """
    Get the list of all giftable villagers.
    Uses a known list since the wiki's gallery layout is complex to parse.
    """
    # All giftable villagers from the Stardew Valley Wiki
    # Source: https://stardewvalleywiki.com/Villagers
    all_villagers = (
        # Bachelors
        BACHELORS +
        # Bachelorettes  
        BACHELORETTES +
        # Non-marriage candidates (giftable)
        [
            "Caroline", "Clint", "Demetrius", "Dwarf", "Evelyn", "George",
            "Gus", "Jas", "Jodi", "Kent", "Krobus", "Leo", "Lewis", "Linus",
            "Marnie", "Pam", "Pierre", "Robin", "Sandy", "Vincent", "Willy", "Wizard"
        ]
    )
    
    villagers = [
        {"name": name, "url": f"{BASE_URL}/{name}"}
        for name in all_villagers
    ]
    
    print(f"Found {len(villagers)} giftable villagers")
    return villagers


def parse_birthday(soup: BeautifulSoup) -> Optional[dict]:
    """Extract birthday from villager infobox."""
    # The wiki uses id="infoboxtable" for the main infobox
    infobox = soup.find("table", {"id": "infoboxtable"})
    if not infobox:
        return None
    
    # Look for the birthday row
    for row in infobox.find_all("tr"):
        section = row.find("td", {"id": "infoboxsection"})
        if section and "Birthday" in section.get_text():
            detail = row.find("td", {"id": "infoboxdetail"})
            if detail:
                birthday_text = detail.get_text(strip=True)
                
                # Try "Season Day" format first (e.g., "Summer13" or "Summer 13")
                match = re.match(r"(Spring|Summer|Fall|Winter)\s*(\d+)", birthday_text)
                if match:
                    return {
                        "season": match.group(1),
                        "day": int(match.group(2))
                    }
                
                # Try "Day Season" format (e.g., "13Fall" or "13 Fall")
                match = re.match(r"(\d+)\s*(Spring|Summer|Fall|Winter)", birthday_text)
                if match:
                    return {
                        "season": match.group(2),
                        "day": int(match.group(1))
                    }
    return None


def parse_image_url(soup: BeautifulSoup) -> Optional[str]:
    """Extract the main villager portrait image URL."""
    infobox = soup.find("table", {"id": "infoboxtable"})
    if not infobox:
        return None
    
    # The portrait is usually the first image in the infobox
    img = infobox.find("img")
    if img and img.get("src"):
        src = img.get("src")
        # Make sure it's an absolute URL
        if src.startswith("//"):
            return f"https:{src}"
        elif src.startswith("/"):
            return f"{BASE_URL}{src}"
        return src
    return None


def parse_gift_preferences(soup: BeautifulSoup) -> dict:
    """Extract all gift preferences (loved, liked, neutral, disliked, hated)."""
    gifts = {
        "loved": [],
        "liked": [],
        "neutral": [],
        "disliked": [],
        "hated": []
    }
    
    # First, try to get loved gifts from the infobox (always present there)
    infobox = soup.find("table", {"id": "infoboxtable"})
    if infobox:
        for row in infobox.find_all("tr"):
            section = row.find("td", {"id": "infoboxsection"})
            if section and "Loved" in section.get_text():
                detail = row.find("td", {"id": "infoboxdetail"})
                if detail:
                    # Items are in nametemplate spans with links
                    for link in detail.find_all("a"):
                        title = link.get("title")
                        if title and not title.startswith("File:"):
                            item = title.strip()
                            if item and item not in gifts["loved"]:
                                gifts["loved"].append(item)
    
    # Now parse the Gifts section for all categories
    content = soup.find("div", {"id": "mw-content-text"})
    if not content:
        return gifts
    
    # Find gift category headings (h3 level: Love, Like, Neutral, Dislike, Hate)
    category_map = {
        "love": "loved",
        "like": "liked",
        "neutral": "neutral",
        "dislike": "disliked",
        "hate": "hated"
    }
    
    for heading in content.find_all("h3"):
        span = heading.find("span", {"class": "mw-headline"})
        if not span:
            continue
            
        heading_text = span.get_text(strip=True).lower()
        current_category = None
        
        for key, value in category_map.items():
            if key == heading_text:
                current_category = value
                break
        
        if not current_category:
            continue
        
        # Look for the items after this heading (usually in a div or table)
        sibling = heading.find_next_sibling()
        while sibling and sibling.name not in ["h2", "h3"]:
            # Parse items from nametemplate spans or links
            for link in sibling.find_all("a"):
                title = link.get("title")
                if title and not title.startswith("File:"):
                    item = title.strip()
                    if item and item not in gifts[current_category]:
                        # Filter out section links and categories
                        if not any(x in item.lower() for x in ["universal", "category", "gift", "villager"]):
                            gifts[current_category].append(item)
            sibling = sibling.find_next_sibling()
    
    return gifts


def parse_schedule(soup: BeautifulSoup) -> dict:
    """Extract the full detailed schedule."""
    schedule = {}
    
    content = soup.find("div", {"id": "mw-content-text"})
    if not content:
        return schedule
    
    # Find the "Schedule" section
    schedule_section = None
    for heading in content.find_all("h2"):
        span = heading.find("span", {"class": "mw-headline"})
        if span and "Schedule" in span.get_text():
            schedule_section = heading
            break
    
    if not schedule_section:
        return schedule
    
    # Look for collapsible tables (one per season)
    # These tables have class "mw-collapsible"
    sibling = schedule_section.find_next_sibling()
    
    while sibling and sibling.name != "h2":
        # Check for collapsible season tables
        if sibling.name == "table" and "mw-collapsible" in sibling.get("class", []):
            # Get the season name from the header
            header = sibling.find("th")
            if header:
                season_link = header.find("a")
                season_name = season_link.get_text(strip=True) if season_link else header.get_text(strip=True)
                
                # Parse all schedule variants within this season
                schedule[season_name] = parse_season_schedules(sibling)
        
        sibling = sibling.find_next_sibling()
    
    return schedule


def parse_season_schedules(season_table: BeautifulSoup) -> list:
    """Parse all schedule variants within a season's collapsible table."""
    schedules = []
    
    # Find all wikitables within the season table (each is a schedule variant)
    # Also find the <b> tags that label each schedule
    content_cell = season_table.find("td")
    if not content_cell:
        return schedules
    
    current_label = "Regular"
    
    # Iterate through the content
    for element in content_cell.children:
        if element.name == "p":
            # Check for bold text indicating schedule name
            bold = element.find("b")
            if bold:
                current_label = bold.get_text(strip=True)
        
        elif element.name == "table" and "wikitable" in element.get("class", []):
            # Parse this schedule table
            schedule_data = {
                "name": current_label,
                "entries": []
            }
            
            rows = element.find_all("tr")
            for row in rows:
                # Skip header row
                if row.find("th"):
                    continue
                
                tds = row.find_all("td")
                if len(tds) >= 2:
                    time = tds[0].get_text(strip=True)
                    location = tds[1].get_text(" ", strip=True)
                    schedule_data["entries"].append({
                        "time": time,
                        "location": location
                    })
            
            if schedule_data["entries"]:
                schedules.append(schedule_data)
    
    return schedules


def scrape_villager_details(name: str, url: str) -> Optional[dict]:
    """Scrape all details for a single villager."""
    print(f"  Scraping {name}...")
    soup = make_request(url)
    if not soup:
        return None
    
    villager = {
        "name": name,
        "url": url,
        "image_url": parse_image_url(soup),
        "birthday": parse_birthday(soup),
        "marriageable": name in MARRIAGE_CANDIDATES,
        "gifts": parse_gift_preferences(soup),
        "schedule": parse_schedule(soup)
    }
    
    return villager


def build_birthday_index(villagers: dict) -> dict:
    """Create a lookup index for birthdays by season and day."""
    birthdays = {
        "Spring": {},
        "Summer": {},
        "Fall": {},
        "Winter": {}
    }
    
    for name, data in villagers.items():
        if data.get("birthday"):
            season = data["birthday"]["season"]
            day = str(data["birthday"]["day"])
            if season in birthdays:
                birthdays[season][day] = name
    
    return birthdays


def scrape_all_villagers() -> dict:
    """Main function to scrape all villager data."""
    print("=" * 50)
    print("Stardew Valley Villager Scraper")
    print("=" * 50)
    
    # Get list of all villagers
    villager_list = get_villager_list()
    
    if not villager_list:
        print("No villagers found!")
        return {}
    
    print(f"Scraping {len(villager_list)} villagers...")
    
    # Scrape each villager's details
    villagers = {}
    for i, v in enumerate(villager_list, 1):
        print(f"[{i}/{len(villager_list)}]", end="")
        details = scrape_villager_details(v["name"], v["url"])
        if details:
            villagers[v["name"]] = details
    
    # Build the final output structure
    output = {
        "metadata": {
            "scraped_at": datetime.now().isoformat(),
            "source": VILLAGERS_URL,
            "total_villagers": len(villagers),
            "marriage_candidates": len([v for v in villagers.values() if v.get("marriageable")])
        },
        "villagers": villagers,
        "birthdays_by_date": build_birthday_index(villagers)
    }
    
    return output


def save_to_json(data: dict, filename: str = "villagers.json"):
    """Save the scraped data to a JSON file."""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\nData saved to {filename}")


def main():
    """Main entry point."""
    data = scrape_all_villagers()
    
    if data and data.get("villagers"):
        save_to_json(data)
        print(f"\nSuccessfully scraped {len(data['villagers'])} villagers!")
        print("\nSample villager data structure:")
        # Show a sample of the first villager
        first_villager = list(data["villagers"].values())[0]
        print(json.dumps({
            "name": first_villager["name"],
            "birthday": first_villager["birthday"],
            "marriageable": first_villager["marriageable"],
            "gifts_count": {k: len(v) for k, v in first_villager["gifts"].items()},
            "schedule_sections": list(first_villager["schedule"].keys())
        }, indent=2))
    else:
        print("No data was scraped. Please check for errors above.")


if __name__ == "__main__":
    main()

