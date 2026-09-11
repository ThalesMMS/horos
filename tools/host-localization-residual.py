#!/usr/bin/env python3
"""English values that stay English on purpose in the host catalogs.

Technical names, product names, units, hanging-protocol anatomy codes, format
tokens and the ASCII overlay strings used by legacy rendering are not
translations. Everything else in the Italian and Spanish catalogs must differ
from the English value.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Overlay strings the English catalog marks ASCII-only for legacy rendering.
ASCII_OVERLAYS = {
    " Angle: %0.0f",
    "From: %d %% (%0.2f) to: %d %% (%0.2f)",
    "Fused Image : X: %d px Y: %d px Value: %2.2f %@",
    "Fused Image : X: %d px Y: %d px Value: R:%ld G:%ld B:%ld",
    "Im: %ld-%ld/%ld %@",
    "Im: %ld/%ld %@",
    "Length: %2.2f cm ",
    "Length: %2.2f mm ",
    "Mean: %2.2f SDev: %2.2f\nMin: %2.2f Max: %2.2f",
    "SUV (fused image): %.2f",
    "SUV: %.2f",
    "X: %d px Y: %d px Value: %2.2f %@",
    "X: %d px Y: %d px Value: R:%ld G:%ld B:%ld",
    "Zoom: %0.0f%%",
}

# Product, platform, format and protocol names that are the same in every UI.
PRODUCT = {
    "Horos", "Horos 64-bit", "Horos Light", "Horos Lite", "Horos MD",
    "Horos bundle", "Horos CD/DVD",
    "OsiriX", "OsiriX 64-bit", "OsiriXDB.plist",
    "iPhoto", "Photos", "iChat", "QuickTime", "QuickTime VR", "Quicktime Export",
    "Microsoft Word", "Mac OS X", "macOS", "macOS Version", "MacOS Version",
    "Mac OS Version",
    "Pages", "LibreOffice",
}

TECHNICAL = {
    "DICOM", "DICOMDIR", "PACS", "ROI", "ROIs", "ROI ", "CLUT", "WLWW",
    "WL / WW", "WL & WW", "WL/WW & CLUT", "WL/WW & CLUT & Opacity",
    "Default WL & WW", "Default WW/WL", "Full Dynamic WW/WL",
    "MIP", "MPR", "CPR", "PET", "SUV", "RGB", "JPEG", "TIFF", "LOD",
    "WADO", "QIDO", "C-MOVE", "C-GET", "RTSTRUCT", "XML-RPC Network Access",
    "16-bit CLUT", "16-bit CLUT Editor", "16-bit CLUTs",
    "8-bit CLUT Editor", "8-bit CLUTs",
    "No CLUT", "CLUT Editor",
    "3DCut", "3DRotate", "3DRotateCamera", "2D/3D", "3D", "32-bit", "64-bit",
    "BW", "B/W Inverse", "Cobb", "Repulsor", "FlyThru", "Fly Thru",
    "AccessionNumber", "Study Instance UID",
    "DICOMNodes.plist", "DICOMPrinters.plist", "DatabaseAlbums.albums",
    "N/A", "n/a", "OK", "OK !", "OPENGL ERROR",
    "Plugin", "Preset", "Password", "Password:", "Password:<br><br>",
    "Listener", "Routing", "Routing...", "Query", "Zoom", "Frame", "Frames",
    "On-Demand", "Stereo", "CD/DVD", "Database", "Database & DICOM",
        "File", "file", "N2Connection timeout.",
        "%d series", "%i bytes", "bytes",
        "Series", "series", "Album: %@", "Axial", "CD-Rom", "CD/DVD",
        "Color", "Coronal", "Error", "Error: %@", "File: %@",
        "General", "Horizontal", "Vertical", "Local", "Total", "Zoom",
        "Incompatible", "N2Connection timeout.", "Routing...",
        "Perpendicular", "Rendering...", "Reslicing...", "Report PDF",
        "Database: %@", "Name: %@", "Opacity: %@", "Projection: %@",
        "Shadings: %@", "Meta-Data: %@",
    "Q&R Auto-Query", "Q&R Auto-Retrieve",
    "WW/WL Tool",
}

MODALITY = {
    "CR", "CT", "MR", "US", "XA", "PT", "NM", "MG", "DX", "RF", "SC", "OT",
    "ES", "PR", "KO", "ECG",
}

# Hanging-protocol / laterality codes kept as the stored English tokens.
ANATOMY = {
    "A", "I", "L", "P", "R", "S",
    "ABD", "ABDOMEN", "AC JOINT", "ACROMIAL", "ADRENAL", "ANKLE", "APPENDIX",
    "BICEPS", "BLADDER", "BRACHIAL", "BRAIN",
    "C SPINE", "CALCANEUS", "CARDIAC", "CAROTID", "CARPAL", "CERVICAL",
    "CHEST", "CLAVICLE", "ELBOW", "FACE", "FEMUR", "FIBULA", "FINGER",
    "FOOT", "FOREARM", "HALLUX", "HAND", "HEAD", "HEART", "HEEL", "HIP",
    "HIPS", "HUMERUS", "IAC", "IVP", "KIDNEY", "KNEE", "L SPINE", "LIVER",
    "LOWER LEG", "LUNG", "MANDIBLE", "MAXILLOFACIAL", "MEDIASTINUM",
    "NAVICULAR", "NECK", "ORBIT", "ORBITS", "OS CALCIS", "OVARIES", "OVARY",
    "PANCREAS", "PELVIC", "PELVIS", "PITUITARY", "PROSTATE", "PULMONARY",
    "RADIUS", "RENAL", "ROTATOR CUFF", "SCAPHOID", "SCAPULA", "SHOULDER",
    "SINUS", "STERNUM", "T SPINE", "TALUS", "TEMPORAL BONE", "THIGH",
    "THORACIC", "THORAX", "THUMB", "THYROID", "TIBIA", "TOE", "TOES",
    "ULNA", "UPPER ARM", "UTERUS", "WRIST",
}

UNITS = {
    "cm", "mm", "px", "dB", "sec", "hertz",
    "cm/sec", "cm²", "cm²/sec", "cm³", "cm³/sec", "m/sec", "dB/sec",
    " DB", " m", " y",
}

# Album names that embed a modality code; the token is the search key.
TODAY_YESTERDAY = {
    "Today CR", "Today CT", "Today MG", "Today MR", "Today RF", "Today US",
    "Today XA",
    "Yesterday CR", "Yesterday CT", "Yesterday MG", "Yesterday MR",
    "Yesterday RF", "Yesterday US", "Yesterday XA",
}

# On-image measurement readouts. Legacy rendering and the Italian catalog keep
# these English; translating them would also violate several ASCII comments.
OVERLAY = {
    "\n - the same location for each image",
    "\n - the same number of images",
    "\n - the same pixels spacing",
    "\rMean: %2.4f SDev: %2.4f Total: %2.4f",
    "\rMin: %2.4f Max: %2.4f ",
    "\rSkewness: %2.4f Kurtosis: %2.4f ",
    "   Measurement: %2.2f cm ",
    "   Measurement: %2.2f mm ",
    "   Pixel: %@    %@ %@",
    "   Scale: %2.3f %% ",
    "%0.0f im/s",
    "%0.1f im/s",
    "%0.1f %cm",
    "%0.2f cm",
    "%0.2f mm",
    "2D Pos: X:%0.3f %@ Y:%0.3f %@",
    "2D Pos: X:%0.3f %@ Y:n/a %@",
    "2D Pos: X:%0.3f px Y:%0.3f px",
    "2D Pos: X:n/a %@ Y:%0.3f %@",
    "2D Pos: X:n/a %@ Y:n/a %@",
    "3D Length: %0.1f %cm",
    "3D Length: %0.3f cm",
    "3D Length: %0.3f mm",
    "3D Pos: X:%0.3f mm Y:%0.3f mm Z:%0.3f mm",
    "A-B : %2.2f cm",
    "A-C : %2.2f cm",
    "A: %@",
    "B-C : %2.2f cm",
    "B-C: %@",
    "B: %@",
    "C: %@",
    "Angle 2: %0.2f%@",
    "Angle: %0.2f%@",
    "Angle: %0.2f%@ with: %@",
    "Angle: %0.3f%@ / %0.3f%@",
    "Area: %0.1f %cm²",
    "Area: %0.1f %cm² (W: %0.1f %cm H: %0.1f %cm)",
    "Area: %0.3f cm²",
    "Area: %0.3f cm² (W: %0.3f cm H: %0.3f cm)",
    "Area: %0.3f mm²",
    "Area: %0.3f mm² (W: %0.3f mm H: %0.3f mm)",
    "Area: %0.3f pix2",
    "Area: %0.3f pix2 (W: %0.3f pix H: %0.3f pix)",
    "Calcium Mass: %0.1f",
    "Calcium Score: %0.1f",
    "Calcium Volume: %0.1f",
    "Fused Image Mean: %0.3f%@ SDev: %0.3f%@ Sum: %0.0f%@",
    "Fused Image Mean: %0.3f%@ SDev: %0.3f%@ Sum: %0.0f%@ Median: %@%@",
    "Fused Image Min: %0.3f%@ Max: %0.3f%@",
    "Fused Image Min: %0.3f%@ Max: %0.3f%@ Skewness: %0.3f Kurtosis: %0.3f",
    "Fused Image Value: %0.3f%@",
    "Length: %0.1f %cm",
    "Length: %0.3f cm",
    "Length: %0.3f mm",
    "Length: %0.3f pix",
    "Length: X=%0.3f %@, Y=%0.3f %@",
    "Mean: %0.3f%@ SDev: %0.3f%@ Sum: %0.0f%@",
    "Mean: %0.3f%@ SDev: %0.3f%@ Sum: %0.0f%@ Median: %@%@",
    "Min: %0.3f%@ Max: %0.3f%@",
    "Min: %0.3f%@ Max: %0.3f%@ Skewness: %0.3f Kurtosis: %0.3f",
    "Thickness: %0.2f %cm Location: %0.2f %cm",
    "Thickness: %0.2f %cm Location: %0.2f mm",
    "Thickness: %0.2f mm Location: %0.2f mm",
    "Volume : %2.4f cm³",
    "Volume : %2.4f mm³",
    "WL: %.0f WW: %.0f",
    "WL: %0.4f WW: %0.4f",
    "WL: %d WW: %d",
    "Value: %0.3f%@",
    "value : %.0f",
    "value : %.0f\nalpha : %1.3f",
    "value:\t%2.2f",
    "alpha : %1.3f",
    "mm:\t\tx:%2.2f y:%2.2f z:%2.2f",
    "px:\t\tx:%d y:%d",
    "r:%.0f%%, g:%.0f%%, b:%.0f%%",
    "Ambient: %2.1f\nDiffuse: %2.1f\nSpecular :%2.1f-%2.1f",
    "Ambient: %2.2f\nDiffuse: %2.2f\nSpecular :%2.2f, %2.2f",
    "Background: red:%.0f%%, green:%.0f%%, blue:%.0f%%",
    "Image %d\r%.2f",
    "Image size: %ld x %ld",
    "View Size: %d x %d",
    "View size: %ld x %ld",
    "zoom x %.1f",
    "Elapsed Time:\r%2.2d:%2.2d:%2.2d",
    "Last Duration:\r%2.2d:%2.2d:%2.2d",
    "Estimated remaining time: %2.2d:%2.2d:%2.2d",
    "(~/Library/Application Support/Horos App/)",
    "%@-Report.pdf",
}

EXACT = (
    ASCII_OVERLAYS | PRODUCT | TECHNICAL | MODALITY | ANATOMY | UNITS
    | TODAY_YESTERDAY | OVERLAY | {
        " (TLS)", " (SUV Converted)", " (retired)",
        "Horos Screen Captures", "OsiriX Screen Captures",
        "iChat Theatre shared view",
        "MPEG-2 File",
        "Uncompressed BigEndian",
        "Linear Table", "Logarithmic Inverse Table",
    }
)

WORD = re.compile(r"[A-Za-zÀ-ÿ]{3,}")
FORMAT = re.compile(
    r"%(?:\d+\$)?[-+#0 ]*(?:\d+|\*)?(?:\.(?:\d+|\*))?(?:hh|ll|[hljztLq])?"
    r"[@diuoxXfFeEgGaAcCsSpn%]"
)


def is_format_or_token(text):
    """True when the string has no translatable word of three letters or more."""
    stripped = FORMAT.sub("", text)
    stripped = re.sub(r"[\d\s\.\,:;_\-–—/\\|()\[\]<>•·×xX%#\+\*=\"'`~]+", "", stripped)
    return not WORD.search(stripped)


def is_residual(key, english_value=None):
    value = english_value if english_value is not None else key
    if key in EXACT or value in EXACT:
        return True
    if is_format_or_token(key) and is_format_or_token(value):
        return True
    return False


def english_comments():
    source = (ROOT / "Horos/Resources/en.lproj/Localizable.strings").read_text(
        encoding="utf-16")
    ascii_keys = []
    for comment, literal in re.findall(
            r'/\*(.*?)\*/\s*("(?:\\.|[^"\\])*")\s*=', source, re.S):
        if "ASCII" in comment:
            ascii_keys.append(json.loads(literal))
    return ascii_keys
