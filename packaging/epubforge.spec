# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec producing a self-contained EPUB-Forge directory.

Two executables share one distribution: a windowed GUI and a console CLI. They
are built from separate entry scripts but collected once, so the ~100 MB of Qt,
Python and the bundled Java runtime is paid for only a single time.

Run through ``packaging/build.py``, which stages the JRE and EPUBCheck into
``packaging/_bundle`` before invoking PyInstaller.
"""

import os
import sys
from pathlib import Path

SPEC_DIR = Path(SPECPATH).resolve()
PROJECT_ROOT = SPEC_DIR.parent
BUNDLE_DIR = SPEC_DIR / "_bundle"

block_cipher = None

# Bundled resources are optional: a build without them still works, it just
# cannot run EPUBCheck. epubforge.resources looks for exactly these names.
datas = []
if (BUNDLE_DIR / "jre").is_dir():
    datas.append((str(BUNDLE_DIR / "jre"), "jre"))
if (BUNDLE_DIR / "epubcheck").is_dir():
    datas.append((str(BUNDLE_DIR / "epubcheck"), "epubcheck"))

# The window and taskbar icons are loaded at runtime; the executable's own
# resource icon (set below) only covers how Explorer draws the file.
for icon_name in ("epubforge.ico", "epubforge.png"):
    if (SPEC_DIR / icon_name).is_file():
        datas.append((str(SPEC_DIR / icon_name), "."))

# Qt ships far more than this app touches; dropping the unused stacks saves
# well over a hundred megabytes.
excludes = [
    "tkinter", "unittest", "pydoc_data", "pytest", "setuptools", "pip",
    "matplotlib", "numpy", "scipy", "pandas", "IPython",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtSerialPort",
    "PySide6.QtWebSockets", "PySide6.QtWebChannel", "PySide6.QtSql", "PySide6.QtTest",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSpatialAudio", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtSensors", "PySide6.QtStateMachine", "PySide6.QtUiTools",
]

hiddenimports = [
    # cssutils resolves its profile and codec modules dynamically.
    "cssutils.css", "cssutils.stylesheets", "cssutils.scripts", "encodings.idna",
    # The corpus panel imports this inside the worker, to keep the window's
    # start-up free of it. Named here as well: if the analysis ever missed it
    # the button would fail in the installed build and nowhere else, which is
    # the one place nobody here can test.
    "epubforge.edge_cases",
]

common = dict(
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# The PySide6 hook collects every Qt shared library and plugin regardless of
# what was imported, so the Python-level `excludes` above do not shrink Qt at
# all. These are dropped by filename after analysis. Everything listed here is
# a stack a QtWidgets-only application never loads.
QT_DROP_SUBSTRINGS = (
    "qt6quick", "qt6qml", "qt6pdf", "qt6webengine", "qt6webview",
    "qt6charts", "qt6datavisualization", "qt63d", "qt6multimedia",
    "qt6spatialaudio", "qt6bluetooth", "qt6nfc", "qt6positioning",
    "qt6location", "qt6serialport", "qt6serialbus", "qt6sensors",
    "qt6scxml", "qt6statemachine", "qt6remoteobjects", "qt6test",
    "qt6help", "qt6designer", "qt6uitools", "qt6sql", "qt6websockets",
    "qt6webchannel", "qt6texttospeech", "qt6httpserver", "qt6quick3d",
)

QT_DROP_DIRS = (
    "pyside6/qt/qml/", "pyside6/qt/translations/", "pyside6/qt6/qml/",
    "pyside6/qt6/translations/", "pyside6/translations/",
    "plugins/qmltooling/", "plugins/sqldrivers/", "plugins/multimedia/",
    "plugins/canbus/", "plugins/position/", "plugins/sensors/",
    "plugins/renderers/", "plugins/geometryloaders/", "plugins/webview/",
    "plugins/designer/", "plugins/scxmldatamodel/", "plugins/texttospeech/",
    "plugins/sceneparsers/", "plugins/renderplugins/", "plugins/assetimporters/",
)


def _keep(destination: str) -> bool:
    normalised = destination.replace("\\", "/").lower()
    if any(fragment in normalised for fragment in QT_DROP_DIRS):
        return False
    leaf = normalised.rsplit("/", 1)[-1]
    return not any(fragment in leaf for fragment in QT_DROP_SUBSTRINGS)


def prune(entries):
    return [entry for entry in entries if _keep(entry[0])]


gui_analysis = Analysis([str(SPEC_DIR / "entry_gui.py")], **common)
cli_analysis = Analysis([str(SPEC_DIR / "entry_cli.py")], **common)

for analysis in (gui_analysis, cli_analysis):
    analysis.binaries = prune(analysis.binaries)
    analysis.datas = prune(analysis.datas)

gui_pyz = PYZ(gui_analysis.pure, gui_analysis.zipped_data, cipher=block_cipher)
cli_pyz = PYZ(cli_analysis.pure, cli_analysis.zipped_data, cipher=block_cipher)

icon = str(SPEC_DIR / "epubforge.ico")
if not os.path.isfile(icon):
    icon = None

gui_exe = EXE(
    gui_pyz,
    gui_analysis.scripts,
    [],
    exclude_binaries=True,
    name="EPUB-Forge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)

cli_exe = EXE(
    cli_pyz,
    cli_analysis.scripts,
    [],
    exclude_binaries=True,
    name="epubforge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)

# Both executables resolve their dependencies from the same _internal folder.
COLLECT(
    gui_exe,
    cli_exe,
    gui_analysis.binaries,
    gui_analysis.zipfiles,
    gui_analysis.datas,
    cli_analysis.binaries,
    cli_analysis.zipfiles,
    cli_analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="EPUB-Forge",
)
