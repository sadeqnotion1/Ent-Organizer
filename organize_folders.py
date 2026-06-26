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

# Ensure standard output supports UTF-8 for unicode names in Windows terminals.
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

# --- Endpoints. {char}/{query}/{imdb_id}/{OMDB_API_KEY} are format/f-string fields ---
IMDB_SUGGEST_URL = "https://v3.sg.media-imdb.com/suggests/{char}/{query}.json"
SUBSOURCE_BASE_URL = "https://api.subsource.net/api/v1"

VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v')
SUB_EXTENSIONS = ('.srt', '.sub', '.vtt', '.ass')
INFO_EXTENSIONS = ('.txt', '.nfo')

LOG_FILE_PATH = "folder_organizer.log"

# API keys are loaded at runtime from api_keys.txt or CLI flags. No secrets in source.
API_KEYS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_keys.txt")
DEFAULT_KEYS = {"subsource": "", "omdb": ""}
SUBSOURCE_API_KEY = ""
OMDB_API_KEY = ""

# Episode detection: S01E02, 1x02, Season 1 Episode 2
EPISODE_REGEXES = [
    r'[Ss](\d{1,2})[\s._-]*[Ee](\d{1,3})',
    r'(?<![a-z0-9])(\d{1,2})x(\d{1,3})(?![a-z0-9])',
    r'[Ss]eason[\s._-]*(\d{1,2})[\s._-]*[Ee]pisode[\s._-]*(\d{1,3})',
]
SEASON_DIR_RX = re.compile(r'^[Ss]eason[\s._-]*(\d{1,2})$')


def log_msg(msg, level="INFO", console_prefix="", console=True):
    """Logs messages to console and a local folder_organizer.log file."""
    # Strip non-ASCII for the log file to avoid encoding errors on older shells.
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
            "SUCCESS": "[OK]",
            "OK": "[OK]",
            "WARNING": "[!]",
            "ERROR": "[X]",
            "DEBUG": "[.]",
        }
        prefix = color_prefixes.get(level, "[*]")
        print(f"{console_prefix}{prefix} [{level}] {msg}")


def load_api_keys():
    """Read api_keys.txt (key=value lines). Returns a dict; missing keys blank."""
    keys = dict(DEFAULT_KEYS)
    try:
        with open(API_KEYS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip().lower()
                v = v.strip()
                if k in keys:
                    keys[k] = v
    except FileNotFoundError:
        pass
    except Exception as e:
        log_msg(f"Could not read api_keys.txt: {e}", "WARNING")
    return keys


def save_api_keys(subsource="", omdb=""):
    """Write api_keys.txt on the local machine. Never committed (see .gitignore)."""
    if isinstance(subsource, dict):
        omdb = subsource.get("omdb", "")
        subsource = subsource.get("subsource", "")
    try:
        with open(API_KEYS_PATH, "w", encoding="utf-8") as f:
            f.write("# Ent-Organizer API keys. This file stays on your PC and is gitignored.\n")
            f.write("# Get a free OMDb key at https://www.omdbapi.com/apikey.aspx\n")
            f.write(f"subsource={subsource.strip()}\n")
            f.write(f"omdb={omdb.strip()}\n")
        return True
    except Exception as e:
        log_msg(f"Could not write api_keys.txt: {e}", "ERROR")
        return False


def clean_movie_filename(filename):
    """
    Parse the filename to extract the title and release year.
    Returns (cleaned_title, year_int_or_None)
    """
    base_name, _ = os.path.splitext(filename)
    normalized_name = base_name.replace('.', ' ').replace('_', ' ').replace('-', ' ')

    year_match = re.search(r'\b(19\d{2}|20\d{2})\b', normalized_name)
    if year_match:
        year = int(year_match.group(1))
        title_raw = normalized_name[:year_match.start()]
    else:
        year = None
        title_raw = normalized_name

    title = title_raw
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

    title = re.sub(r'[\[\]\(\)\-\+\_]+', ' ', title)
    title = re.sub(r'\s+', ' ', title).strip()
    title = title.title()
    return title, year


def detect_episode(name):
    """Return (season, episode) if name looks like a TV episode, else None."""
    for rx in EPISODE_REGEXES:
        m = re.search(rx, name)
        if m:
            try:
                return (int(m.group(1)), int(m.group(2)))
            except (ValueError, IndexError):
                continue
    return None


def parse_media(filename):
    """Classify a filename as movie or tv and pull out title/year/season/episode."""
    title, year = clean_movie_filename(filename)
    se = detect_episode(filename)
    if se:
        return {"kind": "tv", "title": title or "Unknown", "year": year,
                "season": se[0], "episode": se[1]}
    return {"kind": "movie", "title": title or "Unknown", "year": year}


def series_folder_name(title, year):
    return f"{title} ({year})" if year else f"{title}"


def movie_folder_name(title, year):
    return f"{title} ({year})" if year else f"{title}"


def season_folder_name(season):
    return f"Season {season:02d}"


def episode_folder_name(title, season, episode):
    return f"{title} S{season:02d}E{episode:02d}"


def _sanitize(name):
    """Strip characters Windows forbids in folder names."""
    name = re.sub(r'[<>:"/\\|?*]+', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip().rstrip('.')
    return name or "Unknown"


def search_imdb_poster(title, year=None, kind=None):
    """
    Search IMDb suggest API and return the best poster URL.
    kind: 'tv', 'movie', or None. When set, prefer matching IMDb entry types.
    Returns (poster_url, imdb_id, matched_title, matched_year) or None.
    """
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

    tv_types = ('tvseries', 'tvminiseries', 'tv')
    movie_types = ('movie', 'feature', 'video', 'short')

    def type_matches(entry):
        if not kind:
            return True
        qid = (entry.get('qid') or entry.get('q') or '').lower()
        if kind == 'tv':
            return any(t in qid for t in tv_types)
        return any(t in qid for t in movie_types)

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode('utf-8')
        start = content.find('(')
        end = content.rfind(')')
        if start == -1 or end == -1:
            return None
        data = json.loads(content[start + 1:end])
        suggestions = data.get('d', [])
        if not suggestions:
            return None

        def usable(entry):
            return entry.get('id', '').startswith('tt') and 'i' in entry

        best_match = None
        # Phase 1: title + year + kind
        if year:
            for entry in suggestions:
                if usable(entry) and entry.get('y') == year and type_matches(entry):
                    best_match = entry
                    break
        # Phase 2: title + kind
        if not best_match:
            for entry in suggestions:
                if usable(entry) and type_matches(entry):
                    et = entry.get('l', '').lower()
                    if title.lower() in et or et in title.lower():
                        best_match = entry
                        break
        # Phase 3: first entry of the right kind
        if not best_match:
            for entry in suggestions:
                if usable(entry) and type_matches(entry):
                    best_match = entry
                    break
        # Phase 4: any usable entry
        if not best_match:
            for entry in suggestions:
                if usable(entry):
                    best_match = entry
                    break

        if best_match:
            raw_url = best_match['i'][0]
            poster_url = re.sub(r'\._V1_.*\.jpg$', '._V1_FMjpg_UX1000_.jpg', raw_url)
            return (poster_url, best_match.get('id'), best_match.get('l'), best_match.get('y'))
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
        log_msg(f"Failed to download poster: {e}", "WARNING", "   ")
        return False


def download_media_details(imdb_id, save_dir, kind='movie'):
    """Query OMDb API and write info.txt for a movie or TV series."""
    if not OMDB_API_KEY:
        return False
    label = "SERIES PROFILE" if kind == 'tv' else "MOVIE PROFILE"
    log_msg(f"[Metadata] Fetching OMDb details for IMDb ID: {imdb_id}", "INFO", "   ")
    try:
        omdb_url = f"https://www.omdbapi.com/?i={imdb_id}&apikey={OMDB_API_KEY}&plot=full"
        req = urllib.request.Request(omdb_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            omdb_data = json.loads(r.read().decode('utf-8'))

        if omdb_data.get("Response") == "False":
            log_msg(f"OMDb API Error: {omdb_data.get('Error')}", "WARNING", "   ")
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
        total_seasons = omdb_data.get("totalSeasons", "N/A")
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

        sheet = []
        sheet.append("=" * 60)
        sheet.append(f"  {label} - {title.upper()}")
        sheet.append("=" * 60)
        sheet.append("")
        sheet.append("GENERAL INFO")
        sheet.append("-" * 60)
        sheet.append(f"- Title: {title}")
        sheet.append(f"- Year: {year}")
        if kind == 'tv':
            sheet.append(f"- Total Seasons: {total_seasons}")
        sheet.append(f"- Rated: {rated}")
        sheet.append(f"- Released: {released}")
        sheet.append(f"- Genre: {genre}")
        sheet.append(f"- Runtime: {runtime}")
        sheet.append(f"- Language: {language}")
        sheet.append(f"- Country: {country}")
        sheet.append("")
        sheet.append("RATINGS")
        sheet.append("-" * 60)
        sheet.append(f"- IMDb Score: {imdb_score}")
        sheet.append(f"- Metascore: {metascore}")
        sheet.append(f"- Rotten Tomatoes: {rt_score}")
        sheet.append("")
        sheet.append("CREW & CAST")
        sheet.append("-" * 60)
        sheet.append(f"- Director: {director}")
        sheet.append(f"- Writer: {writer}")
        sheet.append(f"- Starring: {actors}")
        sheet.append("")
        sheet.append("PLOT SUMMARY")
        sheet.append("-" * 60)
        sheet.append(plot)
        sheet.append("")
        sheet.append("=" * 60)

        info_path = os.path.join(save_dir, "info.txt")
        with open(info_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(sheet))
        log_msg("Generated metadata sheet: info.txt", "SUCCESS", "   ")
        return True
    except Exception as e:
        log_msg(f"Failed to download details for {imdb_id}: {e}", "ERROR", "   ")
        return False


# ===========================================================================
# Subtitle stack - preserved verbatim from the original project
# (only the mirror row regex was repaired to close the <tr> tag).
# ===========================================================================
def clean_text_for_matching(text):
    return set(re.findall(r'[a-z0-9]+', text.lower()))


def download_subtitles_from_subsource(imdb_id, movie_filename, save_dir, language="english"):
    """Query Subsource.net API (Prioritized) to search and download subtitles."""
    lang_key = "english" if language == "english" else "farsi"
    zip_filename = "english_subtitles.zip" if language == "english" else "farsi_subtitles.zip"
    sub_ext = ".srt" if language == "english" else ".farsi.srt"

    if not SUBSOURCE_API_KEY:
        return False

    log_msg(f"[SubSource] Searching subtitles for IMDb ID: {imdb_id} (Language: {language})", "DEBUG", "   ")

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
        lang_subs = [s for s in subs_list if s.get("lang", "").lower() == lang_key]
        if not lang_subs:
            return False

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

        zip_save_path = os.path.join(save_dir, zip_filename)
        with open(zip_save_path, 'wb') as f:
            f.write(zip_bytes)

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

        log_msg(f"Successfully downloaded {language.upper()} subtitles from prioritized API: SubSource", "OK", "   ")
        return True
    except Exception as e:
        log_msg(f"[SubSource] SubSource API downloader failed: {e}", "WARNING", "   ")
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

    log_msg(f"[MirrorFailover] Starting backup search for {language.upper()} subtitles on mirrors.", "DEBUG", "   ")

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
                        log_msg(f"Downloaded {language.upper()} subtitles zip & extracted srt from mirror: {mirror}", "OK", "   ")
                        return True
        except Exception:
            continue

    log_msg(f"Failed to download {language.upper()} subtitles from all mirrors.", "ERROR", "   ")
    return False


def download_subtitles(imdb_id, movie_filename, save_dir, language="english"):
    """Search and download subtitles for the media."""
    if download_subtitles_from_subsource(imdb_id, movie_filename, save_dir, language):
        return True
    return download_subtitles_from_mirrors(imdb_id, movie_filename, save_dir, language)


def find_video_file_in_folder(folder_path):
    """Scans folder and returns the largest video file name."""
    try:
        candidates = []
        for file in os.listdir(folder_path):
            ext = os.path.splitext(file.lower())[1]
            if ext in VIDEO_EXTENSIONS:
                file_path = os.path.join(folder_path, file)
                candidates.append((file, os.path.getsize(file_path)))
        if candidates:
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


# ===========================================================================
# Organizing helpers
# ===========================================================================
def _move_companions(src_dir, base_name, dest_dir, video_name):
    """Move sidecar files (subs/nfo sharing the video's base name) next to it."""
    moved = 0
    try:
        for f in os.listdir(src_dir):
            full = os.path.join(src_dir, f)
            if not os.path.isfile(full) or f == video_name:
                continue
            stem, ext = os.path.splitext(f)
            if ext.lower() in (SUB_EXTENSIONS + INFO_EXTENSIONS) and stem.startswith(base_name):
                try:
                    shutil.move(full, os.path.join(dest_dir, f))
                    moved += 1
                except Exception:
                    pass
    except Exception:
        pass
    return moved


def _looks_like_series_dir(folder_path):
    """True if a folder already contains Season NN subfolders."""
    try:
        for item in os.listdir(folder_path):
            if os.path.isdir(os.path.join(folder_path, item)) and SEASON_DIR_RX.match(item):
                return True
    except Exception:
        pass
    return False


def _set_icon(folder_path, poster_url, dry_run, skip_icons, cache_jpg=None):
    """Apply a square, move-safe poster icon to a folder.
    Returns the local jpg path used (so it can be reused across episode folders)."""
    if skip_icons or not HAS_CORE or not poster_url:
        return cache_jpg
    if dry_run:
        log_msg(f"[DryRun] Would set folder icon: {folder_path}", "INFO", "   ")
        return cache_jpg
    jpg_path = os.path.join(folder_path, "avatar.jpg")
    try:
        if cache_jpg and os.path.exists(cache_jpg):
            shutil.copyfile(cache_jpg, jpg_path)
        elif not download_poster(poster_url, jpg_path):
            return cache_jpg
        if core.apply_folder_icon(folder_path, jpg_path):
            log_msg("Applied square move-safe folder icon.", "OK", "   ")
        # Keep only the hidden .ico; remove the leftover .jpg source.
        core.cleanup_source_image(folder_path)
    except Exception as e:
        log_msg(f"Icon step failed: {e}", "WARNING", "   ")
    return jpg_path if os.path.exists(jpg_path) else cache_jpg


def _fetch_subs_for(folder_path, imdb_id, video_filename, args):
    """Download English/Farsi subtitles for one media folder."""
    if args.skip_subs or not imdb_id or not video_filename:
        return
    if args.dry_run:
        log_msg(f"[DryRun] Would fetch subtitles for: {video_filename}", "INFO", "   ")
        return
    if not has_english_subtitle(folder_path):
        download_subtitles(imdb_id, video_filename, folder_path, language="english")
    if not args.skip_farsi and not has_farsi_subtitle(folder_path):
        download_subtitles(imdb_id, video_filename, folder_path, language="farsi")


def _resolve_series(series_cache, title, year, args):
    """Resolve (and cache) IMDb id + poster url for a series title."""
    key = f"{title}|{year}"
    if key in series_cache:
        return series_cache[key]
    info = {"imdb_id": None, "poster_url": None}
    result = search_imdb_poster(title, year, kind='tv')
    if result:
        info["poster_url"], info["imdb_id"] = result[0], result[1]
    series_cache[key] = info
    return info


def main():
    parser = argparse.ArgumentParser(
        description="Ent-Organizer - organize movies & TV shows into clean folders, "
                    "apply square move-safe poster icons, and fetch subtitles."
    )
    parser.add_argument("--dir", "-d", type=str, help="Directory to process.")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes only.")
    parser.add_argument("--skip-icons", action="store_true", help="Do not apply folder icons.")
    parser.add_argument("--skip-subs", action="store_true", help="Skip downloading subtitles.")
    parser.add_argument("--skip-farsi", action="store_true", help="Skip Farsi subtitles.")
    parser.add_argument("--skip-info", action="store_true", help="Skip info.txt metadata sheets.")
    parser.add_argument("--subsource-key", "-sk", type=str, default=None, help="Subsource API key (overrides api_keys.txt).")
    parser.add_argument("--omdb-key", "-ok", type=str, default=None, help="OMDb API key (overrides api_keys.txt).")
    args = parser.parse_args()

    # Resolve keys: CLI flag wins, else api_keys.txt, else blank (feature disabled).
    stored = load_api_keys()
    global SUBSOURCE_API_KEY, OMDB_API_KEY
    SUBSOURCE_API_KEY = args.subsource_key if args.subsource_key is not None else stored.get("subsource", "")
    OMDB_API_KEY = args.omdb_key if args.omdb_key is not None else stored.get("omdb", "")

    target_dir = args.dir
    if not target_dir:
        default_path = os.getcwd()
        print("=== ENT-ORGANIZER ===")
        try:
            user_input = input(f"Enter the directory path to process\n [Default: {default_path}]: ").strip()
            target_dir = user_input if user_input else default_path
        except (EOFError, KeyboardInterrupt):
            target_dir = default_path
        print()
    target_dir = os.path.abspath(target_dir)

    try:
        with open(LOG_FILE_PATH, "w", encoding="utf-8") as f:
            f.write(f"=== ENT-ORGANIZER RUN START | TIME: {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            f.write(f"Target Directory: {target_dir}\n")
            f.write(f"Dry Run: {args.dry_run}\n")
            f.write("=" * 60 + "\n\n")
    except Exception:
        pass

    log_msg("=" * 60)
    log_msg("  ENT-ORGANIZER - Movies & TV Shows")
    log_msg("=" * 60)
    log_msg(f"Target Directory: {target_dir}")
    log_msg(f"Run Mode: {'DRY RUN (No changes)' if args.dry_run else 'ACTIVE'}")
    log_msg(f"Folder Icons: {'ENABLED' if not args.skip_icons and HAS_CORE else 'DISABLED'}")
    log_msg(f"English Subtitles: {'ENABLED' if not args.skip_subs else 'DISABLED'}")
    log_msg(f"Farsi Subtitles: {'ENABLED' if not args.skip_subs and not args.skip_farsi else 'DISABLED'}")
    log_msg(f"Info Sheets: {'ENABLED' if not args.skip_info else 'DISABLED'}")
    log_msg("-" * 60)

    if not os.path.isdir(target_dir):
        log_msg(f"Error: Directory does not exist: {target_dir}", "ERROR")
        sys.exit(1)

    try:
        root_items = os.listdir(target_dir)
    except Exception as e:
        log_msg(f"Error listing directory: {e}", "ERROR")
        sys.exit(1)

    video_files = []
    subfolders = []
    for item in root_items:
        full_path = os.path.join(target_dir, item)
        if os.path.isdir(full_path):
            if not item.startswith('.') and item.lower() not in ('__pycache__', 'node_modules', '.git'):
                subfolders.append(item)
        else:
            ext = os.path.splitext(item.lower())[1]
            if ext in VIDEO_EXTENSIONS:
                video_files.append(item)

    log_msg("Found in Root:")
    log_msg(f"  - Loose Video Files: {len(video_files)}")
    log_msg(f"  - Existing Folders: {len(subfolders)}")
    log_msg("-" * 60)

    series_cache = {}
    stats = {"movies": 0, "episodes": 0, "skipped": 0}

    def handle_video_file(src_dir, filename):
        """Organize one loose video file into movie or TV layout under src_dir."""
        media = parse_media(filename)
        src_path = os.path.join(src_dir, filename)
        base_name, _ = os.path.splitext(filename)

        if media["kind"] == "tv":
            series = _sanitize(series_folder_name(media["title"], media["year"]))
            season = season_folder_name(media["season"])
            episode = _sanitize(episode_folder_name(media["title"], media["season"], media["episode"]))
            series_dir = os.path.join(src_dir, series)
            season_dir = os.path.join(series_dir, season)
            episode_dir = os.path.join(season_dir, episode)
            log_msg(f"TV: {filename}  ->  {series}/{season}/{episode}/", "INFO")
            if args.dry_run:
                stats["episodes"] += 1
                return
            os.makedirs(episode_dir, exist_ok=True)
            try:
                shutil.move(src_path, os.path.join(episode_dir, filename))
            except Exception as e:
                log_msg(f"Could not move {filename}: {e}", "ERROR", "   ")
                return
            _move_companions(src_dir, base_name, episode_dir, filename)

            info = _resolve_series(series_cache, media["title"], media["year"], args)
            poster = info.get("poster_url")
            imdb_id = info.get("imdb_id")
            jpg = _set_icon(series_dir, poster, args.dry_run, args.skip_icons)
            _set_icon(episode_dir, poster, args.dry_run, args.skip_icons, cache_jpg=jpg)
            if not args.skip_info and imdb_id and not os.path.exists(os.path.join(series_dir, "info.txt")):
                download_media_details(imdb_id, series_dir, kind='tv')
            _fetch_subs_for(episode_dir, imdb_id, filename, args)
            stats["episodes"] += 1
        else:
            folder = _sanitize(movie_folder_name(media["title"], media["year"]))
            movie_dir = os.path.join(src_dir, folder)
            log_msg(f"MOVIE: {filename}  ->  {folder}/", "INFO")
            if args.dry_run:
                stats["movies"] += 1
                return
            os.makedirs(movie_dir, exist_ok=True)
            try:
                shutil.move(src_path, os.path.join(movie_dir, filename))
            except Exception as e:
                log_msg(f"Could not move {filename}: {e}", "ERROR", "   ")
                return
            _move_companions(src_dir, base_name, movie_dir, filename)

            result = search_imdb_poster(media["title"], media["year"], kind='movie')
            poster = result[0] if result else None
            imdb_id = result[1] if result else None
            _set_icon(movie_dir, poster, args.dry_run, args.skip_icons)
            if not args.skip_info and imdb_id:
                download_media_details(imdb_id, movie_dir, kind='movie')
            _fetch_subs_for(movie_dir, imdb_id, filename, args)
            stats["movies"] += 1

    # STEP 1: organize loose video files in the root.
    for filename in video_files:
        handle_video_file(target_dir, filename)

    # STEP 2: process existing subfolders.
    for folder in subfolders:
        folder_path = os.path.join(target_dir, folder)
        if _looks_like_series_dir(folder_path):
            # Already a series tree: refresh icon + per-episode subtitles.
            media_title, media_year = clean_movie_filename(folder)
            info = _resolve_series(series_cache, media_title, media_year, args)
            poster, imdb_id = info.get("poster_url"), info.get("imdb_id")
            jpg = _set_icon(folder_path, poster, args.dry_run, args.skip_icons)
            if not args.skip_info and imdb_id and not os.path.exists(os.path.join(folder_path, "info.txt")):
                download_media_details(imdb_id, folder_path, kind='tv')
            for season in sorted(os.listdir(folder_path)):
                season_path = os.path.join(folder_path, season)
                if not (os.path.isdir(season_path) and SEASON_DIR_RX.match(season)):
                    continue
                for ep in sorted(os.listdir(season_path)):
                    ep_path = os.path.join(season_path, ep)
                    if not os.path.isdir(ep_path):
                        continue
                    _set_icon(ep_path, poster, args.dry_run, args.skip_icons, cache_jpg=jpg)
                    vid = find_video_file_in_folder(ep_path)
                    _fetch_subs_for(ep_path, imdb_id, vid, args)
                    stats["episodes"] += 1
            continue

        # A normal folder: detect whether its contents are a movie or an episode.
        vid = find_video_file_in_folder(folder_path)
        if not vid:
            stats["skipped"] += 1
            continue
        media = parse_media(vid if detect_episode(vid) else folder)
        if media["kind"] == "tv":
            info = _resolve_series(series_cache, media["title"], media["year"], args)
            poster, imdb_id = info.get("poster_url"), info.get("imdb_id")
            _set_icon(folder_path, poster, args.dry_run, args.skip_icons)
            if not args.skip_info and imdb_id and not os.path.exists(os.path.join(folder_path, "info.txt")):
                download_media_details(imdb_id, folder_path, kind='tv')
            _fetch_subs_for(folder_path, imdb_id, vid, args)
            stats["episodes"] += 1
        else:
            result = search_imdb_poster(media["title"], media["year"], kind='movie')
            poster = result[0] if result else None
            imdb_id = result[1] if result else None
            _set_icon(folder_path, poster, args.dry_run, args.skip_icons)
            if not args.skip_info and imdb_id:
                download_media_details(imdb_id, folder_path, kind='movie')
            _fetch_subs_for(folder_path, imdb_id, vid, args)
            stats["movies"] += 1

    log_msg("-" * 60)
    log_msg(f"Done. Movies: {stats['movies']} | Episodes: {stats['episodes']} | Skipped: {stats['skipped']}", "SUCCESS")


if __name__ == "__main__":
    main()
