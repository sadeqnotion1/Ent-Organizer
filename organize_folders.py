import os
import sys
import re
import shutil
import urllib.request
import urllib.parse
import json
import time
import argparse
import zipfile
import io

# Ensure standard output supports UTF-8 for unicode movie names in Windows terminal
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Add current directory to path so we can import core.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    import core
    HAS_CORE = True
except ImportError:
    HAS_CORE = False

IMDB_SUGGEST_URL = "https://v3.sg.media-imdb.com/suggests/{char}/{query}.json"
SUBSOURCE_BASE_URL = "https://api.subsource.net/api/v1"
VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v')
SUB_EXTENSIONS = ('.srt', '.sub', '.vtt', '.ass')
INFO_EXTENSIONS = ('.txt', '.nfo')

LOG_FILE_PATH = "folder_organizer.log"

def log_msg(msg, level="INFO", console_prefix="", console=True):
    """Logs messages to console and a local folder_organizer.log file."""
    # Strip non-ASCII characters for log file to prevent encoding errors on older Windows shells
    clean_msg = "".join([c for c in msg if ord(c) < 128])
    
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    log_line = f"[{timestamp}] [{level}] {clean_msg}\n"
    
    try:
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception:
        pass
        
    if console:
        color_prefixes = {
            "SUCCESS": "✔️",
            "OK": "✔️",
            "WARNING": "⚠️",
            "ERROR": "❌",
            "DEBUG": "🔍"
        }
        prefix = color_prefixes.get(level, "🎬")
        print(f"{console_prefix}{prefix} [{level}] {msg}")

def clean_movie_filename(filename):
    """
    Parse the filename to extract the movie title and release year.
    Returns (cleaned_title, year_int_or_None)
    """
    base_name, _ = os.path.splitext(filename)
    
    # Replace dots, underscores, and hyphens with spaces first so word boundaries work perfectly
    normalized_name = base_name.replace('.', ' ').replace('_', ' ').replace('-', ' ')
    
    # 1. Search for a 4-digit year (1900-2099)
    year_match = re.search(r'\b(19\d{2}|20\d{2})\b', normalized_name)
    if year_match:
        year = int(year_match.group(1))
        title_raw = normalized_name[:year_match.start()]
    else:
        year = None
        title_raw = normalized_name

    title = title_raw
    
    # 2. Strip common release group keywords, resolutions, codecs, and TV Show Season/Episode tags
    tech_patterns = [
        r'\bs\d{2}e\d{2}\b', r'\bs\d{2}\b', r'\bseason\s*\d+\b', r'\bepisodes?\s*\d+\b',
        r'\b\d{3,4}p\b', r'\b\d+k\b', r'\bweb[-.]?dl\b', r'\bwebrip\b', 
        r'\bbluray\b', r'\bbrrip\b', r'\bx26[45]\b', r'\bhevc\b', r'\b10bit\b', 
        r'\b6ch\b', r'\b8ch\b', r'\bsoftsub\b', r'\bhardsub\b', r'\bdubbed\b', 
        r'\bfarsi\b', r'\bsub\b', r'\byify\b', r'\byts\b', r'\bpahe\b', 
        r'\bdigimoviez\b', r'\bavamovie\b', r'\bzarfilm\b', r'\bvalamovie\b',
        r'\bfilm2media\b', r'\bnightmovie\b', r'\b30nama\b', r'\bpsa\b',
        r'\bdonyayeserial\b', r'\bar\b', r'\bdd\d\.\d\b', r'\bddp\d\.\d\b',
        r'\baac\d\.\d\b', r'\baac\b', r'\bopus\b', r'\bhdr\b',
        r'\bdovi\b', r'\bmac\b', r'\bma\b', r'\bds4k\b', r'\batmos\b',
        r'\bmkvcage\b', r'\bco\b', r'\bfoxmovie\b', r'\bmydonyaye\b',
        r'\bmmdleecher\b', r'\bsilence\b', r'\bbandi\b', r'\bsaberfun\b'
    ]
    
    for pat in tech_patterns:
        title = re.sub(pat, '', title, flags=re.IGNORECASE)
        
    # Remove any trailing brackets or symbols
    title = re.sub(r'[\[\]\(\)\-\+\_]+', ' ', title)
    title = re.sub(r'\s+', ' ', title).strip()
    
    # Capitalize title words beautifully
    title = title.title()
    
    return title, year

def search_imdb_poster(title, year=None):
    """
    Search IMDb suggest API and return the highest quality poster URL.
    Returns (poster_url, imdb_id, matched_title, matched_year) or None.
    """
    # Normalize query: lowercase, replace spaces with underscores, alphanumeric only
    query_clean = re.sub(r'[^a-z0-9\s\_]+', '', title.lower())
    query_clean = re.sub(r'\s+', '_', query_clean).strip('_')
    
    if not query_clean:
        return None
        
    first_char = query_clean[0]
    url = IMDB_SUGGEST_URL.format(char=first_char, query=query_clean)
    
    req = urllib.request.Request(
        url, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode('utf-8')
            start = content.find('(')
            end = content.rfind(')')
            if start == -1 or end == -1:
                return None
                
            json_str = content[start + 1:end]
            data = json.loads(json_str)
            
            suggestions = data.get('d', [])
            if not suggestions:
                return None
                
            best_match = None
            
            # Phase 1: Try to match title AND year
            if year:
                for entry in suggestions:
                    if entry.get('id', '').startswith('tt') and 'i' in entry:
                        entry_year = entry.get('y')
                        if entry_year == year:
                            best_match = entry
                            break
                            
            # Phase 2: Match close title only
            if not best_match:
                for entry in suggestions:
                    if entry.get('id', '').startswith('tt') and 'i' in entry:
                        entry_title = entry.get('l', '').lower()
                        if title.lower() in entry_title or entry_title in title.lower():
                            best_match = entry
                            break
                            
            # Phase 3: Fall back to first title with image
            if not best_match:
                for entry in suggestions:
                    if entry.get('id', '').startswith('tt') and 'i' in entry:
                        best_match = entry
                        break
                        
            if best_match:
                img_data = best_match['i']
                raw_url = img_data[0]
                
                # Boost image resolution by removing IMDb thumbnail suffix if present
                poster_url = re.sub(r'\._V1_.*\.jpg$', '._V1_.jpg', raw_url)
                
                return (
                    poster_url, 
                    best_match.get('id'), 
                    best_match.get('l'), 
                    best_match.get('y')
                )
    except Exception:
        pass
        
    return None

def download_poster(url, save_path):
    """Download poster from the web."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            with open(save_path, 'wb') as out_file:
                out_file.write(response.read())
        return True
    except Exception as e:
        log_msg(f"Failed to download poster: {e}", "WARNING", "  ")
        return False

def clean_text_for_matching(text):
    return set(re.findall(r'[a-z0-9]+', text.lower()))

def download_subtitles_from_subsource(imdb_id, movie_filename, save_dir, language="english"):
    """Query Subsource.net API (Prioritized) to search and download subtitles."""
    lang_key = "english" if language == "english" else "farsi"
    zip_filename = "english_subtitles.zip" if language == "english" else "farsi_subtitles.zip"
    sub_ext = ".srt" if language == "english" else ".farsi.srt"
    
    if not SUBSOURCE_API_KEY:
        return False
        
    log_msg(f"[SubSource] Searching subtitles for IMDb ID: {imdb_id} (Language: {language})", "DEBUG", "  ")
    
    search_url = f"{SUBSOURCE_BASE_URL}/movies/search?imdb={imdb_id}&searchType=imdb"
    req = urllib.request.Request(
        search_url, 
        headers={"X-API-Key": SUBSOURCE_API_KEY, "User-Agent": "Mozilla/5.0"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            res = json.loads(r.read().decode('utf-8'))
            
        if not res.get("success") or not res.get("data") or len(res["data"]) == 0:
            return False
            
        movie_data = res["data"][0]
        movie_id = movie_data["movieId"]
        
        subs_url = f"{SUBSOURCE_BASE_URL}/subtitles?movieId={movie_id}"
        req_subs = urllib.request.Request(
            subs_url,
            headers={"X-API-Key": SUBSOURCE_API_KEY, "User-Agent": "Mozilla/5.0"}
        )
        
        with urllib.request.urlopen(req_subs, timeout=10) as r:
            res_subs = json.loads(r.read().decode('utf-8'))
            
        if not res_subs.get("success") or not res_subs.get("data") or len(res_subs["data"]) == 0:
            return False
            
        subs_list = res_subs["data"]
        
        # Filter by language
        lang_subs = [s for s in subs_list if s.get("lang", "").lower() == lang_key]
        if not lang_subs:
            return False
            
        # Match by filename likeness
        file_words = clean_text_for_matching(movie_filename)
        best_sub = None
        best_score = -1
        
        for sub in lang_subs:
            sub_name = sub.get("releaseName", "")
            sub_words = clean_text_for_matching(sub_name)
            
            score = 0
            key_weights = {
                '1080p': 10, '720p': 10, '2160p': 10, 'bluray': 8, 'brrip': 8, 'bdrip': 8,
                'webrip': 8, 'web': 8, 'dl': 8, 'x264': 5, 'x265': 5, 'hevc': 5, '10bit': 5,
                'yify': 12, 'yts': 12, 'psa': 12, 'rarbg': 12, 'pahe': 12
            }
            for word in file_words:
                if word in sub_words:
                    score += key_weights.get(word, 2)
            
            if score > best_score:
                best_score = score
                best_sub = sub
                
        if not best_sub:
            best_sub = lang_subs[0]
            
        sub_id = best_sub["subId"]
        
        dl_url = f"{SUBSOURCE_BASE_URL}/subtitles/{sub_id}/download"
        req_dl = urllib.request.Request(
            dl_url,
            headers={"X-API-Key": SUBSOURCE_API_KEY, "User-Agent": "Mozilla/5.0"}
        )
        
        with urllib.request.urlopen(req_dl, timeout=15) as response:
            zip_bytes = response.read()
            
        if len(zip_bytes) == 0:
            return False
            
        # Save ZIP pack
        zip_save_path = os.path.join(save_dir, zip_filename)
        with open(zip_save_path, 'wb') as f:
            f.write(zip_bytes)
            
        # Extract best matching .srt file
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            srt_files = [f for f in z.infolist() if f.filename.lower().endswith('.srt')]
            if not srt_files:
                return False
                
            selected_file = srt_files[0]
            srt_data = z.read(selected_file)
            base_name, _ = os.path.splitext(movie_filename)
            save_path = os.path.join(save_dir, f"{base_name}{sub_ext}")
            
            with open(save_path, 'wb') as f:
                f.write(srt_data)
                
            log_msg(f"Successfully downloaded {language.upper()} subtitles from prioritized API: SubSource", "OK", "  ")
            return True
            
    except Exception as e:
        log_msg(f"[SubSource] SubSource API downloader failed: {e}", "WARNING", "  ")
        
    return False

def download_subtitles_from_mirrors(imdb_id, movie_filename, save_dir, language="english"):
    """Search backup mirrors (YIFY/YTS) for English or Farsi subtitles."""
    SUBTITLE_MIRRORS = [
        "https://yts-subs.com",
        "https://yifysubtitles.ch",
        "https://yifysubtitles.org"
    ]
    
    lang_slug_key = "english" if language == "english" else "farsipersian"
    zip_filename = "english_subtitles.zip" if language == "english" else "farsi_subtitles.zip"
    sub_ext = ".srt" if language == "english" else ".farsi.srt"
    
    log_msg(f"[MirrorFailover] Starting backup search for {language.upper()} subtitles on mirrors.", "DEBUG", "  ")
    
    for mirror in SUBTITLE_MIRRORS:
        url = f"{mirror}/movie-imdb/{imdb_id}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                html = r.read().decode('utf-8')
        except Exception:
            continue
            
        rows = re.findall(r'<tr[^>]*>.*?</tr>', html, re.DOTALL)
        
        subs_list = []
        for row in rows:
            slug_match = re.search(rf'/subtitles/([^"\'\s]+-{lang_slug_key}-yify-[0-9]+)', row)
            if slug_match:
                slug = slug_match.group(1)
                desc = re.sub(r'<[^>]+>', ' ', row)
                desc = re.sub(r'\s+', ' ', desc).strip()
                
                rating_match = re.search(r'rating-cell.*?label[^>]*>([0-9\-]+)', row, re.DOTALL)
                rating = int(rating_match.group(1)) if rating_match else 0
                
                subs_list.append((slug, desc, rating))
                
        if not subs_list:
            continue
            
        file_words = clean_text_for_matching(movie_filename)
        best_slug = None
        best_score = -1
        
        for slug, desc, rating in subs_list:
            desc_words = clean_text_for_matching(desc)
            score = 0
            key_weights = {
                '1080p': 10, '720p': 10, '2160p': 10, 'bluray': 8, 'brrip': 8, 'bdrip': 8,
                'webrip': 8, 'web': 8, 'dl': 8, 'x264': 5, 'x265': 5, 'hevc': 5, '10bit': 5,
                'yify': 12, 'yts': 12, 'psa': 12, 'rarbg': 12, 'pahe': 12
            }
            for word in file_words:
                if word in desc_words:
                    score += key_weights.get(word, 2)
            score += max(0, rating)
            
            if score > best_score:
                best_score = score
                best_slug = slug
                
        if not best_slug:
            best_slug = subs_list[0][0]
            
        zip_url = f"{mirror}/subtitle/{best_slug}.zip"
        req_zip = urllib.request.Request(
            zip_url, 
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                'Referer': f"{mirror}/subtitles/{best_slug}",
                'Origin': mirror
            }
        )
        
        try:
            with urllib.request.urlopen(req_zip, timeout=15) as response:
                zip_bytes = response.read()
                
            zip_save_path = os.path.join(save_dir, zip_filename)
            with open(zip_save_path, 'wb') as f:
                f.write(zip_bytes)
                
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
                for file_info in z.infolist():
                    if file_info.filename.lower().endswith('.srt'):
                        srt_data = z.read(file_info)
                        base_name, _ = os.path.splitext(movie_filename)
                        save_path = os.path.join(save_dir, f"{base_name}{sub_ext}")
                        
                        with open(save_path, 'wb') as f:
                            f.write(srt_data)
                            
                        log_msg(f"Downloaded {language.upper()} subtitles zip & extracted srt from mirror: {mirror}", "OK", "  ")
                        return True
        except Exception:
            continue
            
    log_msg(f"Failed to download {language.upper()} subtitles from all mirrors.", "ERROR", "  ")
    return False

def download_subtitles(imdb_id, movie_filename, save_dir, language="english"):
    """Search and download subtitles for the movie."""
    if download_subtitles_from_subsource(imdb_id, movie_filename, save_dir, language):
        return True
    return download_subtitles_from_mirrors(imdb_id, movie_filename, save_dir, language)

def download_movie_details(imdb_id, save_dir):
    """Queries OMDb API and writes info.txt."""
    if not OMDB_API_KEY:
        return False
        
    log_msg(f"  📥 [Metadata] Fetching OMDb details for IMDb ID: {imdb_id}", "INFO")
    
    try:
        omdb_url = f"https://www.omdbapi.com/?i={imdb_id}&apikey={OMDB_API_KEY}&plot=full"
        req = urllib.request.Request(omdb_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            omdb_data = json.loads(r.read().decode('utf-8'))
            
        if omdb_data.get("Response") == "False":
            log_msg(f"  ⚠️ OMDb API Error: {omdb_data.get('Error')}", "WARNING")
            return False
            
        title = omdb_data.get("Title", "N/A")
        year = omdb_data.get("Year", "N/A")
        rated = omdb_data.get("Rated", "N/A")
        released = omdb_data.get("Released", "N/A")
        genre = omdb_data.get("Genre", "N/A")
        runtime = omdb_data.get("Runtime", "N/A")
        language = omdb_data.get("Language", "N/A")
        country = omdb_data.get("Country", "N/A")
        plot = omdb_data.get("Plot", "N/A")
        
        director = omdb_data.get("Director", "N/A")
        writer = omdb_data.get("Writer", "N/A")
        actors = omdb_data.get("Actors", "N/A")
        
        imdb_score = omdb_data.get("imdbRating", "N/A")
        if imdb_score != "N/A":
            imdb_score = f"{imdb_score}/10"
            
        metascore = omdb_data.get("Metascore", "N/A")
        if metascore != "N/A":
            metascore = f"{metascore}/100"
            
        rt_score = "N/A"
        for r_entry in omdb_data.get("Ratings", []):
            if r_entry.get("Source") == "Rotten Tomatoes":
                rt_score = r_entry.get("Value", "N/A")
                break

        # Generate info.txt layout
        sheet = []
        sheet.append("=" * 60)
        sheet.append(f" 🎬 MOVIE PROFILE - {title.upper()} 🎬")
        sheet.append("=" * 60)
        sheet.append("")
        
        sheet.append("📌 GENERAL INFO")
        sheet.append("-" * 60)
        sheet.append(f"• Title:             {title}")
        sheet.append(f"• Year:              {year}")
        sheet.append(f"• Rated:             {rated}")
        sheet.append(f"• Released:          {released}")
        sheet.append(f"• Genre:             {genre}")
        sheet.append(f"• Runtime:           {runtime}")
        sheet.append(f"• Language:          {language}")
        sheet.append(f"• Country:           {country}")
        sheet.append("")
        
        sheet.append("⭐ RATINGS")
        sheet.append("-" * 60)
        sheet.append(f"• IMDb Score:        {imdb_score}")
        sheet.append(f"• Metascore:         {metascore}")
        sheet.append(f"• Rotten Tomatoes:   {rt_score}")
        sheet.append("")
        
        sheet.append("👥 CREW & CAST")
        sheet.append("-" * 60)
        sheet.append(f"• Director:          {director}")
        sheet.append(f"• Writer:            {writer}")
        sheet.append(f"• Starring:          {actors}")
        sheet.append("")
        
        sheet.append("📖 PLOT SUMMARY")
        sheet.append("-" * 60)
        sheet.append(plot)
        sheet.append("")
        sheet.append("=" * 60)
        
        # Write to info.txt
        info_path = os.path.join(save_dir, "info.txt")
        with open(info_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(sheet))
            
        log_msg(f"  ✔️ Generated movie metadata sheet: info.txt", "SUCCESS")
        return True
    except Exception as e:
        log_msg(f"  ❌ Failed to download movie details for {imdb_id}: {e}", "ERROR")
        return False

def find_video_file_in_folder(folder_path):
    """Scans folder and returns the first large video file path."""
    try:
        candidates = []
        for file in os.listdir(folder_path):
            ext = os.path.splitext(file.lower())[1]
            if ext in VIDEO_EXTENSIONS:
                file_path = os.path.join(folder_path, file)
                candidates.append((file, os.path.getsize(file_path)))
        if candidates:
            # Return the largest video file
            candidates.sort(key=lambda x: x[1], reverse=True)
            return candidates[0][0]
    except Exception:
        pass
    return None

def has_english_subtitle(folder_path):
    try:
        for file in os.listdir(folder_path):
            if file.lower().endswith('.srt') and not file.lower().endswith('.farsi.srt'):
                return True
    except Exception:
        pass
    return False

def has_farsi_subtitle(folder_path):
    try:
        for file in os.listdir(folder_path):
            if file.lower().endswith('.farsi.srt'):
                return True
    except Exception:
        pass
    return False

def main():
    parser = argparse.ArgumentParser(
        description="Folder Organizer & Poster Icon Script - Clean raw folder/file names, set custom folder icons, and fetch subtitles."
    )
    
    parser.add_argument(
        "--dir", "-d",
        type=str,
        help="Directory containing the folders or video files to process."
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Display changes without modifying any files or downloading images."
    )
    
    parser.add_argument(
        "--skip-icons",
        action="store_true",
        help="Only organize files, do not apply custom circular folder icons."
    )
    
    parser.add_argument(
        "--skip-subs",
        action="store_true",
        help="Skip downloading subtitles."
    )
    
    parser.add_argument(
        "--skip-farsi",
        action="store_true",
        help="Skip downloading Farsi subtitles."
    )
    
    parser.add_argument(
        "--skip-info",
        action="store_true",
        help="Skip programmatically generating the info.txt movie metadata sheets."
    )
    
    parser.add_argument(
        "--subsource-key", "-sk",
        type=str,
        default=os.environ.get("SUBSOURCE_API_KEY", "sk_f09acde5b3891eac1fa07375cfde7910f2b82ecab83b3a308ed258b809ed4213"),
        help="Custom Subsource API Key."
    )
    
    parser.add_argument(
        "--omdb-key", "-ok",
        type=str,
        default=os.environ.get("OMDB_API_KEY", "trilogy"),
        help="Custom OMDB API Key."
    )
    
    args = parser.parse_args()
    
    global SUBSOURCE_API_KEY, OMDB_API_KEY
    SUBSOURCE_API_KEY = args.subsource_key
    OMDB_API_KEY = args.omdb_key
    
    target_dir = args.dir
    if not target_dir:
        default_path = os.getcwd()
        print("🎬 FOLDER ORGANIZER & POSTER ICON WIZARD 🎬")
        print("=" * 60)
        try:
            user_input = input(f"📂 Enter the directory path to process\n   [Default: {default_path}]: ").strip()
            target_dir = user_input if user_input else default_path
        except (EOFError, KeyboardInterrupt):
            target_dir = default_path
            print()
            
    target_dir = os.path.abspath(target_dir)
    
    # Initialize / clean log file on new execution run
    try:
        with open(LOG_FILE_PATH, "w", encoding="utf-8") as f:
            f.write(f"=== FOLDER ORGANIZER RUN START | TIME: {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            f.write(f"Target Directory: {target_dir}\n")
            f.write(f"Dry Run: {args.dry_run}\n")
            f.write("=" * 60 + "\n\n")
    except Exception:
        pass
        
    log_msg("=" * 60)
    log_msg(" 🎬 FOLDER ORGANIZER & POSTER ICON WIZARD 🎬")
    log_msg("=" * 60)
    log_msg(f"📂 Target Directory: {target_dir}")
    log_msg(f"🔬 Run Mode: {'DRY RUN (No changes)' if args.dry_run else 'ACTIVE (Organizing & Setting Icons)'}")
    log_msg(f"🔄 Auto-Apply Folder Icons: {'ENABLED' if not args.skip_icons and HAS_CORE else 'DISABLED'}")
    log_msg(f"📥 Download English Subtitles: {'ENABLED' if not args.skip_subs else 'DISABLED'}")
    log_msg(f"📥 Download Farsi/Persian Subtitles: {'ENABLED' if not args.skip_subs and not args.skip_farsi else 'DISABLED'}")
    log_msg(f"📝 Generate Info Text Sheets: {'ENABLED' if not args.skip_info else 'DISABLED'}")
    log_msg("-" * 60)
    
    if not os.path.exists(target_dir) or not os.path.isdir(target_dir):
        log_msg(f"Error: Directory does not exist: {target_dir}", "ERROR")
        sys.exit(1)
        
    try:
        root_items = os.listdir(target_dir)
    except Exception as e:
        log_msg(f"Error listing directory: {e}", "ERROR")
        sys.exit(1)
        
    video_files = []
    subfolders = []
    companion_files = []
    
    for item in root_items:
        full_path = os.path.join(target_dir, item)
        if os.path.isdir(full_path):
            if not item.startswith('.') and item.lower() not in ('__pycache__', 'node_modules', '.git'):
                subfolders.append(item)
        else:
            ext = os.path.splitext(item.lower())[1]
            if ext in VIDEO_EXTENSIONS:
                video_files.append(item)
            elif ext in SUB_EXTENSIONS or ext in INFO_EXTENSIONS:
                companion_files.append(item)
                
    log_msg("📋 Found in Root:")
    log_msg(f"  • Video Files to Organize: {len(video_files)}")
    log_msg(f"  • Existing Folders to Process: {len(subfolders)}")
    log_msg(f"  • Subtitles/Info Files: {len(companion_files)}")
    log_msg("-" * 60)
    
    organized_count = 0
    posters_downloaded = 0
    icons_applied = 0
    subtitles_downloaded = 0
    farsi_subtitles_downloaded = 0
    info_sheets_generated = 0
    
    # -------------------------------------------------------------
    # STEP 1: Process Unorganized Video Files
    # -------------------------------------------------------------
    if video_files:
        log_msg("📁 Organizing Movie Files into Folders...")
        for idx, filename in enumerate(video_files, 1):
            file_path = os.path.join(target_dir, filename)
            title, year = clean_movie_filename(filename)
            
            folder_name = f"{title} ({year})" if year else title
            folder_path = os.path.join(target_dir, folder_name)
            
            log_msg(f"[{idx}/{len(video_files)}] Movie: '{title}'" + (f" ({year})" if year else ""))
            log_msg(f"  📁 New Folder: {folder_name}")
            
            if args.dry_run:
                imdb_match = search_imdb_poster(title, year)
                if imdb_match:
                    log_msg(f"🔍 IMDb Match: '{imdb_match[2]}' ({imdb_match[3]}) - Poster Found!", "DEBUG", "  ")
                else:
                    log_msg("IMDb Match: Poster not found.", "ERROR", "  ")
                continue
                
            if not os.path.exists(folder_path):
                try:
                    os.makedirs(folder_path)
                except Exception as e:
                    log_msg(f"Error creating folder: {e}", "ERROR", "  ")
                    continue
                    
            try:
                shutil.move(file_path, os.path.join(folder_path, filename))
                organized_count += 1
            except Exception as e:
                log_msg(f"Error moving video file: {e}", "ERROR", "  ")
                continue
                
            # Move companions
            base_name, _ = os.path.splitext(filename)
            moved_companions = 0
            for comp_file in companion_files:
                if comp_file.startswith(base_name):
                    comp_path = os.path.join(target_dir, comp_file)
                    if os.path.exists(comp_path):
                        try:
                            shutil.move(comp_path, os.path.join(folder_path, comp_file))
                            moved_companions += 1
                        except Exception:
                            pass
            if moved_companions > 0:
                log_msg(f"Moved {moved_companions} companion file(s).", "OK", "  ")
                
            # Poster/Icon
            imdb_match = search_imdb_poster(title, year)
            imdb_id = None
            if imdb_match:
                poster_url, imdb_id, m_title, m_year = imdb_match
                log_msg(f"IMDb Match: '{m_title}' ({m_year})", "OK", "  ")
                avatar_path = os.path.join(folder_path, "avatar.jpg")
                
                log_msg("Downloading HD Movie Poster...", "INFO", "  ")
                if download_poster(poster_url, avatar_path):
                    posters_downloaded += 1
                    
                    if not args.skip_icons and HAS_CORE:
                        try:
                            log_msg("Applying custom folder icon...", "INFO", "  ")
                            core.apply_folder_icon(folder_path, avatar_path)
                            icons_applied += 1
                            log_msg("Folder icon set successfully!", "SUCCESS", "  ")
                        except Exception as e:
                            log_msg(f"Folder icon failed: {e}", "WARNING", "  ")
            else:
                log_msg("IMDb Match: Poster not found.", "ERROR", "  ")
                
            # Subtitles
            if not args.skip_subs and imdb_id:
                if not has_english_subtitle(folder_path):
                    log_msg("Downloading English subtitles...", "INFO", "  ")
                    if download_subtitles(imdb_id, filename, folder_path, language="english"):
                        subtitles_downloaded += 1
                        
            if not args.skip_subs and not args.skip_farsi and imdb_id:
                if not has_farsi_subtitle(folder_path):
                    log_msg("Downloading Farsi/Persian subtitles...", "INFO", "  ")
                    if download_subtitles(imdb_id, filename, folder_path, language="farsi"):
                        farsi_subtitles_downloaded += 1
                        
            # Movie Details
            if not args.skip_info and imdb_id:
                if download_movie_details(imdb_id, folder_path):
                    info_sheets_generated += 1
                        
            time.sleep(0.5)
            print()
            
    # -------------------------------------------------------------
    # STEP 2: Process Existing Subfolders
    # -------------------------------------------------------------
    if subfolders:
        log_msg("📁 Processing Existing Folders...")
        for idx, folder_name in enumerate(subfolders, 1):
            folder_path = os.path.join(target_dir, folder_name)
            
            title, year = clean_movie_filename(folder_name)
            target_folder_name = f"{title} ({year})" if year else title
            
            has_existing_avatar = False
            avatar_path = None
            
            if HAS_CORE:
                try:
                    for file in os.listdir(folder_path):
                        name, ext = os.path.splitext(file.lower())
                        if name in core.AVATAR_NAMES and ext in core.AVATAR_EXTENSIONS:
                            has_existing_avatar = True
                            avatar_path = os.path.join(folder_path, file)
                            break
                except Exception:
                    pass
            else:
                for ext in ['.jpg', '.jpeg', '.png', '.webp']:
                    test_path = os.path.join(folder_path, f"avatar{ext}")
                    if os.path.exists(test_path):
                        has_existing_avatar = True
                        avatar_path = test_path
                        break
            
            current_folder_path = folder_path
            if folder_name != target_folder_name:
                new_folder_path = os.path.join(target_dir, target_folder_name)
                log_msg(f"[{idx}/{len(subfolders)}] Renaming folder: '{folder_name}' ➡️ '{target_folder_name}'")
                
                if not args.dry_run:
                    try:
                        if HAS_CORE:
                            core.remove_win_attributes(folder_path)
                            
                        if os.path.exists(new_folder_path) and new_folder_path.lower() != folder_path.lower():
                            log_msg(f"Destination folder '{target_folder_name}' already exists! Skipping rename.", "WARNING", "  ")
                        else:
                            shutil.move(folder_path, new_folder_path)
                            current_folder_path = new_folder_path
                            log_msg("Folder renamed successfully!", "SUCCESS", "  ")
                            
                            if has_existing_avatar:
                                avatar_path = os.path.join(current_folder_path, os.path.basename(avatar_path))
                    except Exception as e:
                        log_msg(f"Rename failed: {e}", "ERROR", "  ")
            else:
                log_msg(f"[{idx}/{len(subfolders)}] Folder is already clean: '{folder_name}'")
                
            imdb_id = None
            if has_existing_avatar:
                if not args.dry_run and not args.skip_icons and HAS_CORE:
                    icon_path = os.path.join(current_folder_path, 'avatar.ico')
                    desktop_ini = os.path.join(current_folder_path, 'desktop.ini')
                    is_configured = os.path.exists(icon_path) and os.path.exists(desktop_ini)
                    
                    if not is_configured or folder_name != target_folder_name:
                        try:
                            core.apply_folder_icon(current_folder_path, avatar_path)
                            icons_applied += 1
                            log_msg("Folder icon refreshed successfully!", "OK", "  ")
                        except Exception:
                            pass
            else:
                if args.dry_run:
                    imdb_match = search_imdb_poster(title, year)
                    if imdb_match:
                        log_msg(f"🔍 IMDb Match: '{imdb_match[2]}' ({imdb_match[3]}) - Poster Found!", "DEBUG", "  ")
                else:
                    imdb_match = search_imdb_poster(title, year)
                    if imdb_match:
                        poster_url, imdb_id, m_title, m_year = imdb_match
                        log_msg(f"IMDb Match: '{m_title}' ({m_year})", "OK", "  ")
                        avatar_path = os.path.join(current_folder_path, "avatar.jpg")
                        
                        log_msg("Downloading HD Movie Poster...", "INFO", "  ")
                        if download_poster(poster_url, avatar_path):
                            posters_downloaded += 1
                            
                            if not args.skip_icons and HAS_CORE:
                                try:
                                    core.apply_folder_icon(current_folder_path, avatar_path)
                                    icons_applied += 1
                                    log_msg("Folder icon set successfully!", "SUCCESS", "  ")
                                except Exception as e:
                                    log_msg(f"Folder icon failed: {e}", "WARNING", "  ")
                                    
            if not args.skip_subs:
                if not has_english_subtitle(current_folder_path):
                    video_file = find_video_file_in_folder(current_folder_path)
                    if video_file:
                        if not imdb_id:
                            imdb_match = search_imdb_poster(title, year)
                            if imdb_match:
                                imdb_id = imdb_match[1]
                        if imdb_id:
                            log_msg("English subtitles missing. Searching and downloading...", "INFO", "  ")
                            if download_subtitles(imdb_id, video_file, current_folder_path, language="english"):
                                subtitles_downloaded += 1
                                
            if not args.skip_subs and not args.skip_farsi:
                if not has_farsi_subtitle(current_folder_path):
                    video_file = find_video_file_in_folder(current_folder_path)
                    if video_file:
                        if not imdb_id:
                            imdb_match = search_imdb_poster(title, year)
                            if imdb_match:
                                imdb_id = imdb_match[1]
                        if imdb_id:
                            log_msg("Farsi subtitles missing. Searching and downloading...", "INFO", "  ")
                            if download_subtitles(imdb_id, video_file, current_folder_path, language="farsi"):
                                farsi_subtitles_downloaded += 1
                                
            if not args.skip_info:
                info_path = os.path.join(current_folder_path, "info.txt")
                if not os.path.exists(info_path):
                    if not imdb_id:
                        imdb_match = search_imdb_poster(title, year)
                        if imdb_match:
                            imdb_id = imdb_match[1]
                    if imdb_id:
                        if download_movie_details(imdb_id, current_folder_path):
                            info_sheets_generated += 1
                            
            time.sleep(0.1)
            print()
            
    log_msg("=" * 60)
    log_msg("📊 BATCH PROCESS SUMMARY:")
    log_msg(f"  📁 Movies Organized into Folders: {organized_count}")
    log_msg(f"  📥 HD Posters Downloaded: {posters_downloaded}")
    log_msg(f"  📥 English Subtitles Downloaded: {subtitles_downloaded}")
    log_msg(f"  📥 Farsi/Persian Subtitles Downloaded: {farsi_subtitles_downloaded}")
    log_msg(f"  📝 Movie Metadata Sheets (info.txt): {info_sheets_generated}")
    log_msg(f"  ⭐ Folder Icons Configured: {icons_applied}")
    log_msg("=" * 60)
    
    if icons_applied > 0 and HAS_CORE and not args.dry_run:
        log_msg("Sending Windows Explorer Shell refresh to redraw all folder icons immediately...", "INFO")
        core.refresh_explorer()
        log_msg("Finished! Open your folder in Windows Explorer to see the beautiful results!", "SUCCESS")
        
if __name__ == "__main__":
    main()
