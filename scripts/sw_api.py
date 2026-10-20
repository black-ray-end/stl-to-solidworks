"""Version-checked SolidWorks connection; no hardcoded installation paths."""
import os
from pathlib import Path
import re


def connect(year=2024):
    import pythoncom
    import win32com.client as win32
    import winreg
    from win32com.client import makepy
    major = int(year) - 1992
    progid = f"SldWorks.Application.{major}"
    try:
        clsid = winreg.QueryValue(winreg.HKEY_CLASSES_ROOT, progid + "\\CLSID")
        server = winreg.QueryValue(winreg.HKEY_CLASSES_ROOT, "CLSID\\" + clsid + "\\LocalServer32")
    except OSError as exc:
        raise RuntimeError(f"SolidWorks {year} is not registered. No automatic version fallback.") from exc
    match = re.search(r'(?i)"?(.+?\.exe)"?', server)
    exe = Path(match.group(1)) if match else None
    if exe is None or not exe.is_file():
        raise RuntimeError(f"SolidWorks {year} executable is missing")
    typelib = exe.parent / "sldworks.tlb"
    if not typelib.is_file():
        raise RuntimeError("SolidWorks type library is missing")
    # Build wrappers from the installed typelib, not another version's registry entry.
    lib = pythoncom.LoadTypeLib(str(typelib))
    guid, lcid, syskind, libmajor, libminor, flags = lib.GetLibAttr()
    makepy.GenerateFromTypeLibSpec(str(typelib))
    types = win32.gencache.EnsureModule(str(guid), lcid, libmajor, libminor)
    app = types.ISldWorks(win32.Dispatch(progid)._oleobj_)
    revision = app.RevisionNumber()
    if int(revision.split(".")[0]) != major:
        raise RuntimeError(f"Requested {year}, connected to revision {revision}; refusing to create newer files")
    return app, types, revision


def template_path(app, year, explicit=None):
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            raise FileNotFoundError(p)
        return str(p)
    default = app.GetDocumentTemplate(1, "", 0, 0, 0)
    if default and Path(default).is_file():
        return default
    # Use only the requested year's templates, and avoid unrelated MBD templates.
    base = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "SOLIDWORKS" / f"SOLIDWORKS {year}" / "templates"
    candidates = sorted(base.glob("*.prtdot"))
    if not candidates:
        raise RuntimeError("No valid part template found. Supply --template PATH from the requested version.")
    return str(candidates[0])
