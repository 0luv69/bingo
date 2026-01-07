from openpyxl import Workbook

wb = Workbook()
ws = wb.active
ws.title = "Welcome Program Performances"

headers = [
    "Semester",
    "Program",
    "Performer(s)",
    "Performance Type",
    "Song / Content",
    "Contact Number",
    "Status"
]

ws.append(headers)

rows = [
    # 1st Sem BBA
    ("1st", "BBA", "Laxmi Sha", "Solo Dance", "", "", "Confirmed"),
    ("1st", "BBA", "Susmita Yadav", "Solo Dance", "", "", "Confirmed"),
    ("1st", "BBA", "Sherya Rajbanshi", "Solo Dance", "", "", "Confirmed"),
    ("1st", "BBA", "Puspa Metha", "Solo Dance", "", "", "Confirmed"),
    ("1st", "BBA", "Deepika + Lucy", "Group Dance", "", "", "Confirmed"),
    ("1st", "BBA", "Dilshat Shek", "Shayari", "", "", "Confirmed"),

    # 1st Sem BIT
    ("1st", "BIT", "—", "—", "", "", "No Entry"),

    # 1st Sem BHM
    ("1st", "BHM", "Group", "Group Dance", "", "", "Confirmed"),

    # 3rd Sem BBA
    ("3rd", "BBA", "Rosa, Perena, Manisha", "Group Dance", "", "", "Confirmed"),
    ("3rd", "BBA", "Rohit & Shruti", "Dance", "", "", "Confirmed"),
    ("3rd", "BBA", "Rosa + Json", "Group Song", "", "", "Confirmed"),

    # 3rd Sem BIT
    ("3rd", "BIT", "Madav", "Shayari", "", "", "Confirmed"),

    # 5th Sem BBA
    ("5th", "BBA", "Anish", "Solo Song", "", "", "Confirmed"),

    # 5th Sem BIT
    ("5th", "BIT", "MD Osama", "Song", "", "", "Confirmed"),

    # 7th Sem BBA
    ("7th", "BBA", "Rajesh Mandal", "Poem", "", "", "Confirmed"),
    ("7th", "BBA", "Kumar Ghimire", "Poem", "", "", "Confirmed"),
    ("7th", "BBA", "Neha Maji", "Solo Dance", "", "", "Confirmed"),
    ("7th", "BBA", "Nirjala Nisha Group", "Group Dance", "", "", "Waiting"),

    # 8th Sem BBA Marketing
    ("8th", "BBA Marketing", "Sangit Adhikari", "Poem", "", "", "Confirmed"),
    ("8th", "BBA Marketing", "Unika Board Team", "Dance", "", "", "Confirmed"),

    # Teachers
    ("—", "Teacher", "Teachers (Boys)", "Dance", "", "", "Confirmed"),
    ("—", "Teacher", "Teachers (Girls)", "Dance", "", "", "Confirmed"),
    ("—", "Teacher", "Saurab Subedi", "Poem", "", "", "Confirmed"),
    ("—", "Teacher", "Faruk Sir", "Poem", "", "", "Confirmed"),
    ("—", "Teacher", "Sushant Sir", "Poem", "", "", "Confirmed"),
    ("—", "Teacher", "Ronil Sir", "Song", "", "", "Waiting"),
]

for r in rows:
    ws.append(r)

file_path = "/mnt/data/Welcome_Program_Performance_List.xlsx"
wb.save(file_path)

file_path
