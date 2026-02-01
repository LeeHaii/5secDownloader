import os
import csv
import subprocess
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urlparse, parse_qs


CLIP_DURATION = 5.0  # seconds


def clean_youtube_url(url: str) -> str:
    """Extract just the video ID from YouTube URL, removing playlist/list parameters."""
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        
        if 'v' in params:
            video_id = params['v'][0]
            return f"https://www.youtube.com/watch?v={video_id}"
    except:
        pass
    
    return url


def download_clip(
    url: str,
    start_time: float,
    duration: float,
    output_template: str,
) -> None:
    """
    Download a short clip directly from YouTube using yt-dlp --download-sections
    """
    start = start_time
    end = start_time + duration
    section = f"*{int(start)}-{int(end)}"

    # Get Python executable from the virtual environment
    python_exe = str(Path(__file__).parent.parent.parent / ".venv" / "Scripts" / "python.exe")
    
    cmd = [
        python_exe,
        "-m",
        "yt_dlp",
        "--download-sections",
        section,
        "-f",
        "bv*[vcodec^=avc1][height<=1080]+ba[acodec^=mp4a]/b",
        "--merge-output-format",
        "mp4",
        "--postprocessor-args",
        "ffmpeg:-c:v libx264 -preset veryfast -crf 18 -pix_fmt yuv420p -c:a aac -b:a 192k",
        "-o",
        output_template,
        url,
    ]

    # Don't capture output so we can see the yt-dlp progress bar
    print(f"    Downloading... ", end="", flush=True)
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if result.returncode != 0:
        raise Exception(f"Failed to download clip")

    print(f"✓")


def parse_input_csv(
    csv_path: str,
) -> List[List[Tuple[str, List[float]]]]:
    rows = []

    def convert_timestamp(ts: str) -> float:
        parts = ts.split(".")
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        return float(ts)

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if not any(row):
                rows.append([])
                continue

            pairs = []
            for i in range(0, len(row), 2):
                if i + 1 >= len(row):
                    continue

                url = row[i].strip()
                ts_raw = row[i + 1].strip()

                if not url or not ts_raw:
                    continue

                # Clean URL to remove playlist parameters
                url = clean_youtube_url(url)

                timestamps = [
                    convert_timestamp(t.strip())
                    for t in ts_raw.split(";")
                    if t.strip()
                ]

                pairs.append((url, timestamps))

            rows.append(pairs)

    return rows


def process_clips(
    csv_path: str,
    output_base_dir: str,
) -> None:
    rows = parse_input_csv(csv_path)

    # Filter out empty rows and count only non-empty rows
    non_empty_rows = [(idx, pairs) for idx, pairs in enumerate(rows) if pairs]
    
    print(f"Processing {len(non_empty_rows)} non-empty rows\n")

    total_clips = sum(len(ts) for _, pairs in non_empty_rows for _, ts in pairs)
    clips_done = 0

    for output_row_num, (_, pairs) in enumerate(non_empty_rows, start=1):
        print(f"Row {output_row_num}:")
        clip_count = 1

        row_out = os.path.join(output_base_dir, str(output_row_num))
        os.makedirs(row_out, exist_ok=True)

        for url, timestamps in pairs:
            print(f"  URL with {len(timestamps)} timestamp(s)")

            for ts in timestamps:
                clips_done += 1
                # Save as x.y without extension (yt-dlp will add it)
                output_template = os.path.join(
                    row_out, f"{output_row_num}.{clip_count}"
                )

                print(f"    [{clips_done}/{total_clips}] {int(ts)}s ", end="", flush=True)
                try:
                    download_clip(
                        url,
                        ts,
                        CLIP_DURATION,
                        output_template,
                    )
                    clip_count += 1
                except Exception as e:
                    print(f"✗ Error: {str(e)[:50]}")

        print(f"Row {output_row_num}: completed\n")


def main():
    root = Path(__file__).parent.parent

    csv_path = root / "input" / "input.csv"
    output_dir = root / "output"

    if not csv_path.exists():
        print(f"Input CSV not found: {csv_path}")
        return

    print("=" * 50)
    print("YT-DLP SECTION CLIP PROCESSOR")
    print("=" * 50)

    process_clips(
        str(csv_path),
        str(output_dir),
    )

    print("All done.")


if __name__ == "__main__":
    main()
