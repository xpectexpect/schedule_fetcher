import pdfplumber
import json
import timetable_fetcher
import io
import requests
import datetime
import re
import os

base_path = os.path.dirname(os.path.abspath(__file__))

SUBJECT_MAP = {
    'HG': ('Goran Hajnal', 'Fizika'),
    'DL': ('Darija Lozić', 'Matematika'),
    'MM': ('Marina Međurečan', 'Povijest'),
    'KN': ('Barbara Knežević', 'Informatika'),
    'BR': ('Rikard Borić', 'Hrvatski Jezik'),
    'SK': ('Snježana Krištofik Juranić', 'Engleski Jezik'),
    'ŠT': ('Tomislava Špehar', 'Kemija'),
    'CV': ('Anđelko Cvijetković', 'Latinski'),
    'ES': ('Senka Erdeš', 'Biologija'),
    'HK': ('Ivan Hajek', 'Likovna umjetnost'),
    'RK': ('Kristijan Reljac', 'Tjelesna i zdravstvena kultura'),
    'RO': ('Romana Borš Maček', 'Glazbena umjetnost'),
    'NP': ('Nikolina Pavlović', 'Vjeronauk'),
    'VI': ('Višnja Markotić', 'Etika'),
}

ROOM_NUMBERS = [x for x in range(1, 29)]

def extract_schedule(pdf_path):
    """
    Extract schedule with proper handling of merged cells(double periods).
    """

    whole_schedule = {}
    
    
    table_settings = {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
        "snap_tolerance": 3,
        "join_tolerance": 3,
        "edge_min_length": 3,
    }
    
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        
        table = page.extract_table(table_settings)

        if not table:
            table = page.extract_table()
        
        if not table:
            print("No table found")
            return None

        for class_index, class_row in enumerate(table):
            current_class_row = table[class_index]
            class_name = current_class_row[0].strip() if current_class_row[0] else f"Class_{class_index+1}"

            days = ['Ponedjeljak', 'Utorak', 'Srijeda', 'Četvrtak', 'Petak']
            whole_schedule[class_name] = {day: {} for day in days}
            
            cell_idx = 1  # Skip first cell (class name)
            
            for day in list(days):
                period = 1
                while period <= 7:
                    if cell_idx >= len(current_class_row):
                        whole_schedule[class_name][day][period] = None
                        period += 1
                        continue
                    
                    current_cell = current_class_row[cell_idx]
                    
                    # Check if next cell exists
                    next_cell = current_class_row[cell_idx + 1] if cell_idx + 1 < len(current_class_row) else None
                    
                    # Detect if this is a split merged cell
                    is_merged = is_split_cell(current_cell, next_cell)
                    
                    if is_merged and next_cell is not None:
                        # Merge the two cells
                        merged = merge_cells(current_cell, next_cell)
                        whole_schedule[class_name][day][period] = merged
                        whole_schedule[class_name][day][period + 1] = merged.copy()  # Same for next period
                        cell_idx += 2
                        period += 2
                    else:
                        # Single cell
                        parsed = parse_cell(current_cell)
                        whole_schedule[class_name][day][period] = parsed
                        cell_idx += 1
                        period += 1
        
        # Validate and fix using subject map
        # """whole_schedule = validate_with_subject_map(whole_schedule)"""
        
        return whole_schedule

def is_split_cell(cell1, cell2):
    """
    Detect if two cells are part of a merged cell (double period).
    
    Indicators:
    - Both cells have single character teachers (H + G = HG)
    - Both cells have same or similar room numbers
    - When combined, they form a valid teacher code
    """
    if not cell1 or not cell2:
        return False
    
    c1 = str(cell1).strip()
    c2 = str(cell2).strip()

    if not c1 or not c2:
        return False
    
    # Split by newline
    parts1 = c1.split('\n')
    parts2 = c2.split('\n')
    
    teacher1 = parts1[0].strip()
    room1 = parts1[1].strip() if len(parts1) > 1 else ''
    teacher2 = parts2[0].strip()
    room2 = parts2[1].strip() if len(parts2) > 1 else ''
    
    # Check if teachers are single characters that combine to form valid code
    if len(teacher1) == 1 and len(teacher2) == 1:
        combined_name = teacher1 + teacher2
        combined_room = room1 + room2
        if combined_name in SUBJECT_MAP and int(combined_room) in ROOM_NUMBERS:
            return True
    
    # Check if room numbers are identical (another indicator)
    if len(teacher1) <= 2 and len(teacher2) <= 2:
        combined_name = teacher1 + teacher2
        combined_room = room1 + room2
        if combined_name in SUBJECT_MAP and int(combined_room) in ROOM_NUMBERS:
            return True
    
    return False

def merge_cells(cell1, cell2):
    """
    Merge two split cells into one complete entry.
    """
    c1 = str(cell1).strip()
    c2 = str(cell2).strip()
    
    parts1 = c1.split('\n')
    parts2 = c2.split('\n')
    
    teacher1 = parts1[0].strip()
    room1 = parts1[1].strip() if len(parts1) > 1 else ''
    teacher2 = parts2[0].strip()
    room2 = parts2[1].strip() if len(parts2) > 1 else ''
    
    # Combine teacher initials
    teacher_initials = teacher1 + teacher2
    
    # Use first room number (they should be the same)
    room = room1 + room2
    
    # Get subject name
    teacher = SUBJECT_MAP.get(teacher_initials)[0] if teacher_initials in SUBJECT_MAP else 'Unknown'
    subject = SUBJECT_MAP.get(teacher_initials, ['Unknown', 'Unknown'])[1]
    
    return {
        "teacher_initials": teacher_initials if teacher_initials in SUBJECT_MAP else 'Unknown initials',
        "teacher": teacher if teacher != 'Unknown' else 'Unknown teacher',
        "room": room if room else 'Unknown room',
        "subject": subject if subject != 'Unknown' else 'Unknown subject',
        "double_period": True
    }

def parse_cell(cell_content):
    if not cell_content or str(cell_content).strip() == '':
        return None
    
    content = str(cell_content).strip()
    lines = content.split('\n')
    
    if len(lines) >= 2:
        teacher_initials = lines[0].strip()
        room = lines[1].strip()

        teacher = ''
        subject = ''
        
        # Handle cases like "MR / ZE" (alternative teachers)
        if '/' in teacher_initials:
            # Keep as is for now
            teacher = "Multiple"
            subject = "Multiple"
        else:
            teacher = SUBJECT_MAP.get(teacher_initials)[0] if teacher_initials in SUBJECT_MAP else 'Unknown'
            subject = SUBJECT_MAP.get(teacher_initials, ['Unknown', 'Unknown'])[1]
        
        return {
            "teacher_initials": teacher_initials if teacher_initials in SUBJECT_MAP else 'Unknown initials',
            "teacher": teacher if teacher != 'Unknown' else 'Unknown teacher',
            "room": room if room else 'Unknown room',
            "subject": subject if subject != 'Unknown' else 'Unknown subject',
            "double_period": False
        }
    
    return None

def extract_date_from_link(pdf_link):
    match = re.search(r'(\d{1,2})\.(\d{1,2})\.?\-?(\d{4})', pdf_link)
    
    if match:
        day = match.group(1).zfill(2)
        month = match.group(2).zfill(2)
        year = match.group(3)
        return f"{day}.{month}.{year}"
    else:
        return datetime.datetime.now().strftime("%d.%m.%Y.")

def return_schedule_as_json(pdf_link):
    schedule = extract_schedule(pdf_path=io.BytesIO(requests.get(pdf_link).content))
    return schedule

def return_info_as_json(pdf_link):
    # Extract shift from URL (A for morning, B for afternoon)
    shift_match = re.search(r'GIM-EK-([AB])', pdf_link)
    shift = "morning" if shift_match and shift_match.group(1) == "A" else "afternoon"

    info = {
        "timetable_link": pdf_link,
        "link_date": extract_date_from_link(pdf_link),
        "shift": shift,
        "class_teacher": SUBJECT_MAP.get("SK", ["Unknown", "Unknown"])[0]
    }

    return info

def save_whole_schedule_data(pdf_link, save_path):
    data_directory = os.path.join(save_path, extract_date_from_link(pdf_link))
    data_directory.mkdir(parents=True, exist_ok=True)

    pdf_data_directory_path = os.path.join(data_directory, "schedule.pdf")
    with open(pdf_data_directory_path, "wb") as file:
        file.write(requests.get(pdf_link).content)
    
    json_data_directory_path = os.path.join(data_directory, "schedule.json")
    schedule = return_schedule_as_json(pdf_link)
    with open(json_data_directory_path, "w") as file:
        json.dump(schedule, file, ensure_ascii=False, indent=2)

    info_data_directory_path = os.path.join(data_directory, "info.json")
    info = return_info_as_json(pdf_link)
    with open(info_data_directory_path, "w") as file:
        json.dump(info, file, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    pdf_link = timetable_fetcher.fetch_timetable()

    base_path = os.path.dirname(os.path.abspath(__file__))
    saved_schedules_path = os.path.join(base_path, "saved_schedules")

    save_whole_schedule_data(pdf_link, saved_schedules_path)


