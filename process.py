import os
import json
import subprocess
import requests

video_url = os.environ["VIDEO_URL"]
timestamps_json = os.environ["TIMESTAMPS"]
aspect_ratio = os.environ["ASPECT_RATIO"]
watermark_config = json.loads(os.environ["WATERMARK_CONFIG"])
chat_id = os.environ["TELEGRAM_CHAT_ID"]
bot_token = os.environ["TELEGRAM_BOT_TOKEN"]

timestamps = json.loads(timestamps_json)
os.makedirs("output_clips", exist_ok=True)

crop_filters = {
    "9:16": "crop=ih*(9/16):ih",
    "1:1": "crop=min(iw\\,ih):min(iw\\,ih)",
    "4:5": "crop=ih*(4/5):ih"
}
crop_filter = crop_filters.get(aspect_ratio, "crop=ih*(9/16):ih")
wm_text = watermark_config.get("watermark_content", "@Bot")
vf_filter = f"{crop_filter},drawtext=text='{wm_text}':fontcolor=white:fontsize=24:x=w-tw-20:y=h-th-20"

for i, ts in enumerate(timestamps):
    start = ts["start"]
    end = ts["end"]
    output_filename = f"output_clips/clip_{i+1}.mp4"

    print(f"Processing clip {i+1}: {start}s to {end}s")
    cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--download-sections", f"*{start}-{end}",
        "--postprocessor-args", f"ffmpeg:-vf \"{vf_filter}\"",
        "-o", output_filename,
        video_url
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(f"Error processing clip {i+1}: {result.stderr}")
        continue

    if os.path.exists(output_filename):
        print(f"Sending clip {i+1} to Telegram...")
        url = f"https://api.telegram.org/bot{bot_token}/sendVideo"
        with open(output_filename, "rb") as video_file:
            response = requests.post(
                url,
                data={"chat_id": chat_id, "caption": f"Viral Clip #{i+1}"},
                files={"video": video_file}
            )
            print(response.json())
        os.remove(output_filename)

print("All clips processed and sent successfully.")
