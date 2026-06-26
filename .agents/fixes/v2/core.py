import os
import io
import struct
import ctypes
from PIL import Image

# Windows File Attribute Constants
FILE_ATTRIBUTE_READONLY = 0x01
FILE_ATTRIBUTE_HIDDEN = 0x02
FILE_ATTRIBUTE_SYSTEM = 0x04
INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF

# Image formats / names we scan for when looking for a folder poster
AVATAR_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp')
AVATAR_NAMES = ('avatar', 'icon', 'folder', 'cover', 'poster')

# Single, relative icon filename so the folder stays self-contained and move-safe
ICON_FILENAME = 'avatar.ico'


def get_win_attributes(path):
    try:
        attrs = ctypes.windll.kernel32.GetFileAttributesW(path)
        return attrs if attrs != INVALID_FILE_ATTRIBUTES else None
    except Exception:
        return None


def set_win_attributes(path, hidden=False, system=False, readonly=False):
    try:
        attrs = ctypes.windll.kernel32.GetFileAttributesW(path)
        if attrs == INVALID_FILE_ATTRIBUTES:
            return False
        if readonly:
            attrs |= FILE_ATTRIBUTE_READONLY
        else:
            attrs &= ~FILE_ATTRIBUTE_READONLY
        if hidden:
            attrs |= FILE_ATTRIBUTE_HIDDEN
        else:
            attrs &= ~FILE_ATTRIBUTE_HIDDEN
        if system:
            attrs |= FILE_ATTRIBUTE_SYSTEM
        else:
            attrs &= ~FILE_ATTRIBUTE_SYSTEM
        return ctypes.windll.kernel32.SetFileAttributesW(path, attrs) != 0
    except Exception:
        return False


def remove_win_attributes(path):
    try:
        attrs = ctypes.windll.kernel32.GetFileAttributesW(path)
        if attrs == INVALID_FILE_ATTRIBUTES:
            return False
        attrs &= ~FILE_ATTRIBUTE_READONLY
        attrs &= ~FILE_ATTRIBUTE_HIDDEN
        attrs &= ~FILE_ATTRIBUTE_SYSTEM
        return ctypes.windll.kernel32.SetFileAttributesW(path, attrs) != 0
    except Exception:
        return False


def refresh_explorer(folder_path=None):
    """Tell the Windows shell to redraw icons so changes show up immediately."""
    try:
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
        if folder_path:
            abs_path = os.path.abspath(folder_path)
            ctypes.windll.shell32.SHChangeNotify(0x00001000, 0x0005, abs_path, None)
            ctypes.windll.shell32.SHChangeNotify(0x00000800, 0x0005, abs_path, None)
            parent_dir = os.path.dirname(abs_path)
            if parent_dir and os.path.exists(parent_dir):
                ctypes.windll.shell32.SHChangeNotify(0x00001000, 0x0005, parent_dir, None)
        return True
    except Exception as e:
        print(f"Failed to refresh Explorer: {e}")
        return False


def _has_real_transparency(img):
    if img.mode not in ("RGBA", "LA"):
        return False
    alpha = img.getchannel("A") if img.mode == "RGBA" else img.getchannel("L")
    return alpha.getextrema()[0] < 255


def convert_image_to_png_ico(image_path, icon_path):
    """
    Build a multi-resolution ICO from a poster using a SQUARE crop.
    No circular/rounded mask is applied (square artwork keeps its natural look).
    Transparency from PNG/WebP is preserved; opaque sources stay square+opaque,
    which also avoids the transparent-corner 'black background' artifact.
    """
    img = Image.open(image_path)

    original_has_alpha = _has_real_transparency(img) if img.mode in ("RGBA", "LA", "P") else False
    if img.mode == "P":
        original_has_alpha = "transparency" in img.info
        img = img.convert("RGBA")
    elif img.mode != "RGBA":
        img = img.convert("RGBA")

    # Square center crop
    w, h = img.size
    crop_size = min(w, h)
    x = (w - crop_size) // 2
    y = (h - crop_size) // 2
    img_cropped = img.crop((x, y, x + crop_size, y + crop_size))

    SIZES = [256, 128, 64, 48, 32, 16]
    frames = []
    for size in SIZES:
        frame = img_cropped.resize((size, size), Image.Resampling.LANCZOS)
        if not original_has_alpha and frame.mode != "RGBA":
            frame = frame.convert("RGBA")
        buf = io.BytesIO()
        frame.save(buf, format="PNG")
        frames.append(buf.getvalue())

    num = len(frames)
    header = struct.pack("<HHH", 0, 1, num)
    dir_offset = 6 + num * 16
    entries = b""
    image_data = b""
    for i, (size, png_bytes) in enumerate(zip(SIZES, frames)):
        w_byte = 0 if size == 256 else size
        h_byte = 0 if size == 256 else size
        data_offset = dir_offset + sum(len(frames[j]) for j in range(i))
        entries += struct.pack(
            "<BBBBHHII",
            w_byte, h_byte, 0, 0, 1, 32,
            len(png_bytes), data_offset,
        )
        image_data += png_bytes

    with open(icon_path, "wb") as f:
        f.write(header)
        f.write(entries)
        f.write(image_data)


def cleanup_source_image(avatar_image_path):
    """Delete the leftover poster (e.g. avatar.jpg) after the .ico is built so each
    folder only keeps the hidden avatar.ico + desktop.ini."""
    try:
        if avatar_image_path and os.path.isfile(avatar_image_path):
            remove_win_attributes(avatar_image_path)
            os.remove(avatar_image_path)
            return True
    except Exception:
        pass
    return False


def apply_folder_icon(folder_path, avatar_image_path):
    """Create avatar.ico, write a RELATIVE desktop.ini, and set attributes so the
    custom icon shows immediately and keeps working after the folder is moved."""
    if not os.path.isdir(folder_path):
        raise ValueError(f"Path is not a directory: {folder_path}")
    if not os.path.isfile(avatar_image_path):
        raise ValueError(f"Avatar image not found: {avatar_image_path}")

    icon_path = os.path.join(folder_path, ICON_FILENAME)
    desktop_ini = os.path.join(folder_path, 'desktop.ini')

    if os.path.exists(desktop_ini):
        remove_win_attributes(desktop_ini)
    if os.path.exists(icon_path):
        remove_win_attributes(icon_path)

    convert_image_to_png_ico(avatar_image_path, icon_path)

    # RELATIVE reference -> the icon is resolved inside the folder, so moving or
    # renaming the folder does not break it.
    ini_content = (
        "[.ShellClassInfo]\n"
        f"IconResource={ICON_FILENAME},0\n"
        f"IconFile={ICON_FILENAME}\n"
        "IconIndex=0\n"
        "ConfirmFileOp=0\n"
    )
    with open(desktop_ini, 'w', encoding='utf-16') as f:
        f.write(ini_content)

    set_win_attributes(desktop_ini, hidden=True, system=True)
    set_win_attributes(icon_path, hidden=True)

    # Toggle read-only off then on so Explorer re-reads desktop.ini right away.
    set_win_attributes(folder_path, readonly=False, system=False)
    set_win_attributes(folder_path, readonly=True, system=True)

    refresh_explorer(folder_path)
    return True


def remove_folder_icon(folder_path):
    """Revert a single folder back to the default Windows icon."""
    if not os.path.isdir(folder_path):
        raise ValueError(f"Path is not a directory: {folder_path}")

    icon_path = os.path.join(folder_path, ICON_FILENAME)
    desktop_ini = os.path.join(folder_path, 'desktop.ini')
    removed_any = False

    if os.path.exists(desktop_ini):
        remove_win_attributes(desktop_ini)
        os.remove(desktop_ini)
        removed_any = True
    if os.path.exists(icon_path):
        remove_win_attributes(icon_path)
        os.remove(icon_path)
        removed_any = True

    set_win_attributes(folder_path, readonly=False, system=False)
    refresh_explorer(folder_path)
    return removed_any


def revert_icons_recursive(root_path):
    """Recursively remove custom folder icons (handles nested Series/Season/Episode
    folders, not just the top level)."""
    count = 0
    if not os.path.isdir(root_path):
        return 0
    for dirpath, dirnames, filenames in os.walk(root_path):
        lower = {f.lower() for f in filenames}
        if ICON_FILENAME in lower or 'desktop.ini' in lower:
            try:
                if remove_folder_icon(dirpath):
                    count += 1
            except Exception:
                pass
    return count


def scan_folders(root_path):
    """Scan immediate subfolders for poster/icon status (used by tooling)."""
    folders_list = []
    if not os.path.exists(root_path) or not os.path.isdir(root_path):
        return folders_list
    try:
        entries = os.listdir(root_path)
    except Exception as e:
        print(f"Error reading root directory: {e}")
        return folders_list

    for entry in entries:
        full_path = os.path.join(root_path, entry)
        if not os.path.isdir(full_path) or entry.startswith('.') or entry.lower() in (
                '__pycache__', 'node_modules', 'venv', '.git', 'env', '.idea', '.vscode'):
            continue

        avatar_path = None
        try:
            for file in os.listdir(full_path):
                file_path = os.path.join(full_path, file)
                if os.path.isfile(file_path):
                    name, ext = os.path.splitext(file.lower())
                    if name in AVATAR_NAMES and ext in AVATAR_EXTENSIONS:
                        avatar_path = file_path
                        break
        except Exception as e:
            print(f"Skipping restricted folder '{entry}': {e}")
            continue

        desktop_ini = os.path.join(full_path, 'desktop.ini')
        icon_path = os.path.join(full_path, ICON_FILENAME)
        has_ini = os.path.exists(desktop_ini)
        has_ico = os.path.exists(icon_path)
        attrs = get_win_attributes(full_path)
        is_readonly = bool(attrs & FILE_ATTRIBUTE_READONLY) if attrs is not None else False

        folders_list.append({
            'name': entry,
            'path': full_path,
            'avatar_path': avatar_path,
            'icon_path': icon_path if has_ico else None,
            'has_ini': has_ini,
            'is_readonly': is_readonly,
            'status': 'configured' if (has_ini and has_ico) else 'missing_icon' if avatar_path else 'no_avatar',
        })
    return folders_list


def clear_windows_cache():
    """Clear the Windows icon/thumbnail caches to fix the 'black background' bug."""
    import subprocess
    import time

    try:
        subprocess.run(["taskkill", "/f", "/im", "explorer.exe"], capture_output=True, check=False)
    except Exception:
        pass

    time.sleep(1.5)

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        explorer_cache_dir = os.path.join(local_app_data, "Microsoft", "Windows", "Explorer")
        icon_cache_db = os.path.join(local_app_data, "IconCache.db")
        if os.path.exists(icon_cache_db):
            try:
                os.remove(icon_cache_db)
            except Exception:
                pass
        if os.path.isdir(explorer_cache_dir):
            try:
                for file in os.listdir(explorer_cache_dir):
                    if file.startswith("iconcache_") or file.startswith("thumbcache_"):
                        try:
                            os.remove(os.path.join(explorer_cache_dir, file))
                        except Exception:
                            pass
            except Exception:
                pass

    try:
        os.system("start explorer.exe")
    except Exception:
        try:
            subprocess.Popen(["explorer.exe"], shell=True)
        except Exception:
            pass
    return True
