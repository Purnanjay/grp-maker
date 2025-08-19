# save as grplugin_editor.py
import streamlit as st
import os
import re

# =======================
# CONFIGURATION
# =======================
st.set_page_config(page_title="GRpluginMaps Editor", layout="wide")
st.title("✈️ GRpluginMaps Editor & SCT Converter")
st.write("Upload an SCT file to convert, or a GRpluginMaps.txt file to edit.")


# =======================
# Helper Functions
# =======================

def parse_file(content):
    """Parse the GRpluginMaps file into structured sections, merging duplicates"""
    sections = {}
    current_header = None

    for line in content.splitlines():
        if line.strip().startswith("//"):  # new section header
            current_header = line.strip()
            if current_header not in sections:
                sections[current_header] = []
        else:
            if current_header is not None:
                sections[current_header].append(line)
            else:
                sections.setdefault("__ROOT__", []).append(line)

    parsed = [{"header": h, "lines": sections[h]} for h in sections]
    return parsed


def split_lines(lines):
    """Group COORD with its COLOR, LINE with its COLOR, rest in others"""
    coords, lines_, others = [], [], []
    i = 0
    while i < len(lines):
        l = lines[i].strip()
        if l.startswith("COLOR:"):
            block = [lines[i]]
            j = i + 1
            while j < len(lines) and lines[j].strip().startswith(("COORD:", "LINE:")):
                block.append(lines[j])
                j += 1
            if len(block) > 1 and block[1].strip().startswith("LINE:"):
                lines_.extend(block)
            elif len(block) > 1 and block[1].strip().startswith("COORD:"):
                coords.extend(block)
            else:
                others.append(lines[i])
            i = j
        elif l.startswith("COORD:"):
            coords.append(lines[i])
            i += 1
        elif l.startswith("LINE:"):
            lines_.append(lines[i])
            i += 1
        else:
            others.append(lines[i])
            i += 1
    return coords, lines_, others


def rebuild_file(sections):
    """Rebuild text file from structured sections"""
    out_lines = []
    for sec in sections:
        if sec["header"] and sec["header"] != "__ROOT__":
            out_lines.append(sec["header"])
        out_lines.extend(sec["lines"])
        out_lines.append("")  # spacing
    return "\n".join(out_lines)


# -----------------------
# SCT → GRplugin Converter
# -----------------------
def convert_sct_to_grplugin(sct_file_content, sct_filename="file.sct", airport="VABB"):
    lines = sct_file_content.splitlines()
    output = []
    region_name = None
    coords = []
    current_color = "REGIONS"  # default if not specified

    def flush_region():
        if region_name and coords:
            output.append(f"//{region_name}")
            output.append(f"COLOR:{current_color}")
            output.extend(coords)
            output.append("")

    def flush_line(name, color, coords_list):
        if coords_list:
            output.append(f"//{name}")
            output.append(f"GEO:{color}")
            output.extend(coords_list)
            output.append("")

    for line in lines:
        line = line.strip()
        if not line or line.startswith(";"):
            continue

        if line.upper().startswith("REGIONNAME"):
            flush_region()
            region_name = line.split(" ", 1)[1]
            coords = []
            current_color = "REGIONS"

        elif line.upper().startswith("COLOR_"):
            parts = line.split()
            current_color = parts[0].split("_", 1)[1].strip().upper()
            if len(parts) == 3:
                lat, lon = parts[1], parts[2]
                coords.append(f"COORD:{lat}:{lon}")

        elif re.match(r'^[NS]\d{3}\.\d{2}\.\d{2}\.\d{3}', line):
            parts = line.split()
            if len(parts) == 2:
                lat, lon = parts
                coords.append(f"COORD:{lat}:{lon}")

        elif line.upper().startswith("LINE:"):
            parts = line.split()
            if len(parts) >= 4:
                try:
                    color = parts[0].split(":")[1].split("_", 1)[1].strip().upper()
                    name = f"LINE_{color}"
                except IndexError:
                    color = "REGIONS"
                    name = "LINE"

                coord_pairs = parts[1:]
                geo_coords = []
                for i in range(0, len(coord_pairs), 2):
                    if i + 1 < len(coord_pairs):
                        lat, lon = coord_pairs[i], coord_pairs[i + 1]
                        geo_coords.append(f"COORD:{lat}:{lon}")

                flush_line(name, color, geo_coords)

    flush_region()

    header = [
        "// Converted from SCT to GRplugin",
        f"MAP:{airport}grass:GTA2",
        f"FOLDER:{airport}grass",
        f"AIRPORT:{airport}",
        "ZOOM:3",
        "ACTIVE:1",
        f"SCTFILEPATH:\\{sct_filename}",
        ""
    ]

    return "\n".join(header + output)


# =======================
# Streamlit UI
# =======================

file_type = st.radio("Select input type:", ["GRpluginMaps.txt", "SCT file"])

uploaded_file = st.file_uploader("Upload file", type=["txt", "sct"])
if uploaded_file:
    uploaded_bytes = uploaded_file.read()
    try:
        content = uploaded_bytes.decode("utf-8")
    except UnicodeDecodeError:
        content = uploaded_bytes.decode("latin-1")

    if file_type == "SCT file":
        converted_txt = convert_sct_to_grplugin(content, uploaded_file.name)
        st.success("✅ SCT file converted to GRplugin format")
        st.download_button("💾 Download Converted File", converted_txt, file_name="GRpluginMaps_converted.txt")
        # Allow editing after conversion
        content = converted_txt

    # Parse GRpluginMaps content
    sections = parse_file(content)

    st.sidebar.title("Sections")
    selected = st.sidebar.radio("Choose section", range(len(sections)),
                                format_func=lambda i: sections[i]["header"])

    if selected is not None:
        sec = sections[selected]
        st.subheader(sec["header"] or "Unnamed Section")

        coords, lines_, others = split_lines(sec["lines"])

        # RAW editor FIRST
        st.markdown("### 📝 Raw Section (all lines)")
        raw_edit = st.text_area("Edit Raw Section:", "\n".join(sec["lines"]), height=300)

        # COORD editor
        st.markdown("### 📍 COORD blocks (with COLOR)")
        coords_edit = st.text_area("Edit COORD group:", "\n".join(coords), height=250)

        # LINE editor
        st.markdown("### 📏 LINE blocks (with COLOR)")
        lines_edit = st.text_area("Edit LINE group:", "\n".join(lines_), height=250)

        # Merge back — priority: raw editor (if changed)
        if raw_edit != "\n".join(sec["lines"]):
            sec["lines"] = raw_edit.splitlines()
        else:
            sec["lines"] = coords_edit.splitlines() + lines_edit.splitlines() + others

    # Download updated file
    final_txt = rebuild_file(sections)
    st.download_button("💾 Download Edited File", final_txt, file_name="GRpluginMaps_edited.txt")
