import pdfplumber
import json
import timetable_fetcher
import io
import requests

SUBJECT_MAP = {
    'HG': 'Fizika',
    'DL': 'Matematika',
    'MM': 'Povijest',
    'KN': 'Informatika',
    'BR': 'Hrvatski Jezik',
    'SK': 'Engleski Jezik',
    'ŠT': 'Kemija',
    'CV': 'Latinski',
    'ES': 'Biologija',
    'HK': 'Likovna umjetnost',
    'RK': 'Tjelesna i zdravstvena kultura',
    'RO': 'Glazbena umjetnost',
    'NP': 'Vjeronauk - Nista',
    'VI': 'Etika',
}

ROOM_NUMBERS = [x for x in range(1, 29)]

def extract_schedule(pdf_path):
    """
    Extract schedule with proper handling of merged cells(double periods).
    """
    
    schedule = {
        'Ponedjeljak': {},
        'Utorak': {},
        'Srijeda': {},
        'Četvrtak': {},
        'Petak': {}
    }
    
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
        
        # Find 1.PMG row
        pmg_row_idx = None
        for i, row in enumerate(table):
            if row and any(cell and '1.PMG' in str(cell) for cell in row):
                pmg_row_idx = i
                break
        
        if pmg_row_idx is None:
            print("1.PMG row not found")
            return None
        
        pmg_row = table[pmg_row_idx]
        
        # Parse row with merge detection
        days = ['Ponedjeljak', 'Utorak', 'Srijeda', 'Četvrtak', 'Petak']
        
        cell_idx = 1  # Skip first cell (class name)
        
        for day in days:
            period = 1
            while period <= 7:
                if cell_idx >= len(pmg_row):
                    schedule[day][period] = None
                    period += 1
                    continue
                
                current_cell = pmg_row[cell_idx]
                
                # Check if next cell exists
                next_cell = pmg_row[cell_idx + 1] if cell_idx + 1 < len(pmg_row) else None
                
                # Detect if this is a split merged cell
                is_merged = is_split_cell(current_cell, next_cell)
                
                if is_merged and next_cell is not None:
                    # Merge the two cells
                    merged = merge_cells(current_cell, next_cell)
                    schedule[day][period] = merged
                    schedule[day][period + 1] = merged.copy()  # Same for next period
                    cell_idx += 2
                    period += 2
                else:
                    # Single cell
                    parsed = parse_cell(current_cell)
                    schedule[day][period] = parsed
                    cell_idx += 1
                    period += 1
        
        # Validate and fix using subject map
        schedule = validate_with_subject_map(schedule)
        
        return schedule

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
    teacher = teacher1 + teacher2
    
    # Use first room number (they should be the same)
    room = room1 + room2
    
    # Get subject name
    subject = SUBJECT_MAP.get(teacher, 'Unknown')
    
    return {
        "teacher": teacher,
        "room": room,
        "subject": subject,
        "double_period": True
    }

def parse_cell(cell_content):
    """Parse a single (non-merged) cell."""
    if not cell_content or str(cell_content).strip() == '':
        return None
    
    content = str(cell_content).strip()
    lines = content.split('\n')
    
    if len(lines) >= 2:
        teacher = lines[0].strip()
        room = lines[1].strip()
        
        # Handle cases like "MR / ZE" (alternative teachers)
        if '/' in teacher:
            # Keep as is for now
            subject = "Multiple"
        else:
            subject = SUBJECT_MAP.get(teacher, 'Unknown')
        
        return {
            "teacher": teacher,
            "room": room,
            "subject": subject,
            "double_period": False
        }
    
    return None

def validate_with_subject_map(schedule):
    """
    Validate and fix teacher codes using the subject map.
    Fix any remaining split cells that weren't caught.
    """
    days = ['Ponedjeljak', 'Utorak', 'Srijeda', 'Četvrtak', 'Petak']
    
    for day in days:
        period = 1
        while period <= 7:
            current = schedule[day].get(period)
            
            if current and current.get('teacher'):
                teacher = current['teacher']
                
                # If teacher code is not in map and is single char
                if teacher not in SUBJECT_MAP and len(teacher) == 1:
                    # Try to combine with next period
                    if period < 7:
                        next_period = schedule[day].get(period + 1)
                        if next_period and next_period.get('teacher'):
                            next_teacher = next_period['teacher']
                            if len(next_teacher) == 1:
                                combined = teacher + next_teacher
                                if combined in SUBJECT_MAP:
                                    # Fix both periods
                                    merged = {
                                        "teacher": combined,
                                        "room": current['room'],
                                        "subject": SUBJECT_MAP[combined],
                                        "double_period": True
                                    }
                                    schedule[day][period] = merged
                                    schedule[day][period + 1] = merged.copy()
                                    period += 1  # Skip next period
            period += 1
    return schedule

def return_schedule_as_json():
    timetable_pdf_link = timetable_fetcher.fetch_timetable()
    schedule = extract_schedule(pdf_path=io.BytesIO(requests.get(timetable_pdf_link).content))
    return json.dumps(schedule, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    print(return_schedule_as_json())