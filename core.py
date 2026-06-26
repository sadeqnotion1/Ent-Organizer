import os
import io
import struct
import ctypes
import shutil
from PIL import Image


# Windows File Attribute Constants
FILE_ATTRIBUTE_READONLY = 0x01
FILE_ATTRIBUTE_HIDDEN = 0x02
FILE_ATTRIBUTE_SYSTEM = 0x04
INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF

# Image formats we scan for
AVATAR_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp')
AVATAR_NAMES = ('avatar', 'icon', 'folder', 'cover')

def get_win_attributes(path):
    """Get Windows attributes of a file or folder using ctypes."""
    try:
        attrs = ctypes.windll.kernel32.GetFileAttributesW(path)
        return attrs if attrs != INVALID_FILE_ATTRIBUTES else None
    except Exception:
        return None

def set_win_attributes(path, hidden=False, system=False, readonly=False):
    """Set Windows attributes of a file or folder using ctypes."""
    try:
        attrs = ctypes.windll.kernel32.GetFileAttributesW(path)
        if attrs == INVALID_FILE_ATTRIBUTES:
            return False
        
        # Apply readonly
        if readonly:
            attrs |= FILE_ATTRIBUTE_READONLY
        else:
            attrs &= ~FILE_ATTRIBUTE_READONLY
            
        # Apply hidden
        if hidden:
            attrs |= FILE_ATTRIBUTE_HIDDEN
        else:
            attrs &= ~FILE_ATTRIBUTE_HIDDEN
            
        # Apply system
        if system:
            attrs |= FILE_ATTRIBUTE_SYSTEM
        else:
            attrs &= ~FILE_ATTRIBUTE_SYSTEM
            
        return ctypes.windll.kernel32.SetFileAttributesW(path, attrs) != 0
    except Exception:
        return False

def remove_win_attributes(path):
    """Clear hidden, system, and readonly attributes of a file/folder."""
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
    """Notify the Windows Shell that folder properties have changed to refresh the UI."""
    try:
        # 1. Global Shell Association Changed refresh
        # This forces Windows to reload file icons and association configurations
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
        
        # 2. Specific Folder refresh if provided
        if folder_path:
            abs_path = os.path.abspath(folder_path)
            # SHCNE_UPDATEDIR = 0x00001000
            # SHCNF_PATHW = 0x0005 (wide string path)
            ctypes.windll.shell32.SHChangeNotify(0x00001000, 0x0005, abs_path, None)
            
            # SHCNE_ATTRIBUTES = 0x00000800 (attributes changed)
            ctypes.windll.shell32.SHChangeNotify(0x00000800, 0x0005, abs_path, None)
            
            # Also refresh parent directory so its view updates immediately!
            parent_dir = os.path.dirname(abs_path)
            if parent_dir and os.path.exists(parent_dir):
                ctypes.windll.shell32.SHChangeNotify(0x00001000, 0x0005, parent_dir, None)
                
        return True
    except Exception as e:
        print(f"Failed to refresh Explorer: {e}")
        return False

def _has_real_transparency(img):
    """
    Returns True if the image actually contains semi-transparent or fully transparent pixels.
    JPEG, BMP, and similar formats always return False; true PNG/WebP with alpha return True.
    """
    if img.mode not in ("RGBA", "LA"):
        return False
    # Sample the alpha channel — if any pixel is non-opaque it's a real transparent image
    alpha = img.getchannel("A") if img.mode == "RGBA" else img.getchannel("L")
    extrema = alpha.getextrema()
    return extrema[0] < 255  # min alpha < 255 means at least one transparent pixel

def _apply_circular_mask(img_rgba, size):
    """
    Crop+resize the image to `size`×`size` and apply a smooth anti-aliased circular mask.
    This turns solid-background avatars (JPG) into clean circle icons with transparent corners.
    """
    from PIL import ImageDraw, ImageFilter

    # Resize on a 4× canvas for anti-aliasing, then scale down
    ss = size * 4
    img_large = img_rgba.resize((ss, ss), Image.Resampling.LANCZOS)

    # Draw a white circle on black background (the mask)
    mask = Image.new("L", (ss, ss), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, ss - 1, ss - 1), fill=255)

    # Smooth the mask edge slightly before downscaling
    mask = mask.filter(ImageFilter.GaussianBlur(radius=ss * 0.01))

    # Apply mask, then downscale to final size with LANCZOS
    result = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
    result.paste(img_large, mask=mask)
    return result.resize((size, size), Image.Resampling.LANCZOS)

def convert_image_to_png_ico(image_path, icon_path):
    """
    Convert an image (PNG, JPG, WebP, etc.) into a fully transparent, multi-resolution ICO file.

    - If the source image has real alpha (PNG/WebP), transparency is preserved as-is.
    - If the source is opaque (JPEG, BMP), a smooth anti-aliased circular mask is applied so the
      icon has clean transparent corners instead of a solid black box.
    - All sizes (256, 128, 48, 32, 16) are embedded as PNG bytes inside the ICO for guaranteed
      alpha support across every Windows Explorer view and DPI scaling level.
    """
    img = Image.open(image_path)

    # 1. Detect original format transparency BEFORE converting
    original_has_alpha = _has_real_transparency(img) if img.mode in ("RGBA", "LA", "P") else False

    # 2. Convert palette/LA modes — check P mode for transparency
    if img.mode == "P":
        original_has_alpha = "transparency" in img.info
        img = img.convert("RGBA")
    elif img.mode != "RGBA":
        img = img.convert("RGBA")

    # 3. Square Center Crop
    w, h = img.size
    crop_size = min(w, h)
    x = (w - crop_size) // 2
    y = (h - crop_size) // 2
    img_cropped = img.crop((x, y, x + crop_size, y + crop_size))

    # 4. For each target size, generate the frame using the right strategy
    SIZES = [256, 128, 48, 32, 16]
    frames = []  # list of (size, png_bytes)

    for size in SIZES:
        if original_has_alpha:
            # Source already has transparency — preserve it, just resize
            frame = img_cropped.resize((size, size), Image.Resampling.LANCZOS)
        else:
            # Opaque source (JPEG etc.) — apply circular mask at this exact size
            frame = _apply_circular_mask(img_cropped, size)

        # Encode each frame as PNG bytes (guarantees alpha across all Windows views)
        buf = io.BytesIO()
        frame.save(buf, format="PNG")
        frames.append(buf.getvalue())

    # 5. Build ICO binary manually — all frames as PNG
    # ICO Header: Reserved(2) + Type(2, 1=icon) + Count(2)
    num = len(frames)
    header = struct.pack("<HHH", 0, 1, num)

    # Directory entries come after the 6-byte header + num × 16-byte entries
    dir_offset = 6 + num * 16
    entries = b""
    image_data = b""

    for i, (size, png_bytes) in enumerate(zip(SIZES, frames)):
        w_byte = 0 if size == 256 else size   # 0 means 256 in ICO spec
        h_byte = 0 if size == 256 else size
        data_offset = dir_offset + sum(len(frames[j]) for j in range(i))
        entry = struct.pack(
            "<BBBBHHII",
            w_byte, h_byte,   # width, height (0 = 256)
            0, 0,              # color count, reserved
            1, 32,             # color planes, bits per pixel
            len(png_bytes),   # image data size
            data_offset,      # offset to image data
        )
        entries += entry
        image_data += png_bytes

    with open(icon_path, "wb") as f:
        f.write(header)
        f.write(entries)
        f.write(image_data)


def scan_folders(root_path):
    """
    Scan subdirectories in root_path for potential avatar images and icon status.
    Returns a list of dictionaries with folder details.
    """
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
        if not os.path.isdir(full_path) or entry.startswith('.') or entry.lower() in ('__pycache__', 'node_modules', 'venv', '.git', 'env', '.idea', '.vscode'):
            continue

        # Check for avatar image
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
            # Skip folders we don't have permission to read
            print(f"Skipping restricted folder '{entry}': {e}")
            continue

        # Check for existing desktop.ini and avatar.ico
        desktop_ini = os.path.join(full_path, 'desktop.ini')
        icon_path = os.path.join(full_path, 'avatar.ico')
        
        has_ini = os.path.exists(desktop_ini)
        has_ico = os.path.exists(icon_path)
        
        # Verify folder Read-Only attribute
        attrs = get_win_attributes(full_path)
        is_readonly = bool(attrs & FILE_ATTRIBUTE_READONLY) if attrs is not None else False

        folders_list.append({
            'name': entry,
            'path': full_path,
            'avatar_path': avatar_path,
            'icon_path': icon_path if has_ico else None,
            'has_ini': has_ini,
            'is_readonly': is_readonly,
            'status': 'configured' if (has_ini and has_ico and is_readonly) else 'missing_icon' if avatar_path else 'no_avatar'
        })
        
    return folders_list

def apply_folder_icon(folder_path, avatar_image_path):
    """
    Creates the avatar.ico, updates desktop.ini, and sets correct system attributes 
    to make Windows display the custom folder icon immediately.
    """
    if not os.path.isdir(folder_path):
        raise ValueError(f"Path is not a directory: {folder_path}")
        
    if not os.path.isfile(avatar_image_path):
        raise ValueError(f"Avatar image not found: {avatar_image_path}")

    icon_path = os.path.join(folder_path, 'avatar.ico')
    desktop_ini = os.path.join(folder_path, 'desktop.ini')

    # 1. Strip attributes from existing files before overwrite/deletion
    if os.path.exists(desktop_ini):
        remove_win_attributes(desktop_ini)
    if os.path.exists(icon_path):
        remove_win_attributes(icon_path)

    # 2. Generate new icon file
    convert_image_to_png_ico(avatar_image_path, icon_path)

    # 3. Create desktop.ini content using UTF-16 encoding with BOM (standard Windows Unicode)
    abs_icon_path = os.path.normpath(icon_path)
    ini_content = f"[.ShellClassInfo]\nIconResource={abs_icon_path},0\nIconFile={abs_icon_path}\nIconIndex=0\n"
    with open(desktop_ini, 'w', encoding='utf-16') as f:
        f.write(ini_content)

    # 4. Hide desktop.ini and avatar.ico, and set system flag for desktop.ini
    set_win_attributes(desktop_ini, hidden=True, system=True)
    set_win_attributes(icon_path, hidden=True)

    # 5. VERY IMPORTANT: Toggle the folder Read-Only attribute off first and then on.
    # This toggling forces Windows Explorer to clear its cached icon mask for this folder
    # and re-evaluate the desktop.ini immediately, preventing the black background bug!
    set_win_attributes(folder_path, readonly=False, system=False)
    set_win_attributes(folder_path, readonly=True, system=True)
    
    # 6. Notify the shell immediately about the specific folder and parent folder changes!
    refresh_explorer(folder_path)
    
    return True

def remove_folder_icon(folder_path):
    """
    Reverts the folder icon configuration back to default, cleaning up files 
    and resetting the folder Read-Only attribute.
    """
    if not os.path.isdir(folder_path):
        raise ValueError(f"Path is not a directory: {folder_path}")

    icon_path = os.path.join(folder_path, 'avatar.ico')
    desktop_ini = os.path.join(folder_path, 'desktop.ini')
    removed_any = False

    # Strip and delete desktop.ini
    if os.path.exists(desktop_ini):
        remove_win_attributes(desktop_ini)
        os.remove(desktop_ini)
        removed_any = True

    # Strip and delete avatar.ico
    if os.path.exists(icon_path):
        remove_win_attributes(icon_path)
        os.remove(icon_path)
        removed_any = True

    # Remove folder Read-Only and System properties
    set_win_attributes(folder_path, readonly=False, system=False)
    
    # Notify the shell immediately about the specific folder and parent folder changes!
    refresh_explorer(folder_path)
    
    return removed_any

def clear_windows_cache():
    """
    Clears the Windows Icon and Thumbnail caches completely to fix the famous
    'Folder Icon Black Background' bug. Requires killing and restarting explorer.exe.
    """
    import subprocess
    import time
    
    # 1. Kill explorer.exe
    try:
        subprocess.run(["taskkill", "/f", "/im", "explorer.exe"], capture_output=True, check=False)
    except Exception:
        pass
        
    time.sleep(1.5)
    
    # 2. Delete cache files
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        explorer_cache_dir = os.path.join(local_app_data, "Microsoft", "Windows", "Explorer")
        icon_cache_db = os.path.join(local_app_data, "IconCache.db")
        
        # Clear main IconCache.db
        if os.path.exists(icon_cache_db):
            try:
                os.remove(icon_cache_db)
            except Exception:
                pass
                
        # Clear explorer database files
        if os.path.exists(explorer_cache_dir) and os.path.isdir(explorer_cache_dir):
            try:
                for file in os.listdir(explorer_cache_dir):
                    if file.startswith("iconcache_") or file.startswith("thumbcache_"):
                        full_file = os.path.join(explorer_cache_dir, file)
                        try:
                            os.remove(full_file)
                        except Exception:
                            pass
            except Exception:
                pass
                        
    # 3. Restart explorer.exe
    try:
        os.system("start explorer.exe")
    except Exception:
        try:
            subprocess.Popen(["explorer.exe"], shell=True)
        except Exception:
            pass
        
    return True
