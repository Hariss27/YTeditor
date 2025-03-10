import streamlit as st
import os
import requests
from bs4 import BeautifulSoup
from pytube import YouTube
from moviepy import VideoFileClip, TextClip, CompositeVideoClip  # Updated import for moviepy v2.0+
from PIL import Image, ImageDraw, ImageFont
import openai

# Ensure FFmpeg is available (for Streamlit Cloud)
os.environ["IMAGEIO_FFMPEG_EXE"] = "/usr/bin/ffmpeg"

# Load OpenAI API key from Streamlit Cloud secrets
try:
    openai_api_key = st.secrets["openai"]["api_key"]
except KeyError:
    openai_api_key = os.getenv("OPENAI_API_KEY")

if not openai_api_key:
    st.error("OpenAI API key not found. Please add it to the app secrets.")
    raise ValueError("OpenAI API key is missing.")

openai.api_key = openai_api_key

# -------------------
# Function Definitions
# -------------------

# A. Scrape Trailer URL (Rotten Tomatoes + YouTube Fallback)
def get_trailer_url(movie_name):
    try:
        # Step 1: Try Rotten Tomatoes
        search_url_rotten = f"https://www.rottentomatoes.com/search?search={movie_name}"
        response_rotten = requests.get(search_url_rotten)
        if response_rotten.status_code != 200:
            st.error(f"Failed to fetch data from Rotten Tomatoes for {movie_name}. Status code: {response_rotten.status_code}")
            return None

        soup_rotten = BeautifulSoup(response_rotten.text, 'html.parser')
        movie_result = soup_rotten.find('search-page-media-row')
        if movie_result:
            movie_url = movie_result['data-url']
            movie_page_response = requests.get(f"https://www.rottentomatoes.com{movie_url}")
            if movie_page_response.status_code != 200:
                st.error(f"Failed to fetch movie page for {movie_name}. Status code: {movie_page_response.status_code}")
                return None

            movie_page_soup = BeautifulSoup(movie_page_response.text, 'html.parser')
            trailer_div = movie_page_soup.find('a', {'class': 'trailer-player'})
            if trailer_div:
                trailer_url = trailer_div['href']
                return trailer_url
    except Exception as e:
        st.error(f"Error fetching trailer from Rotten Tomatoes for {movie_name}: {e}")

    # Step 2: Fallback to YouTube
    st.warning(f"No trailer found on Rotten Tomatoes for {movie_name}. Searching on YouTube...")
    try:
        search_query = f"{movie_name} official trailer"
        youtube_search_url = f"https://www.youtube.com/results?search_query={search_query}"
        response_youtube = requests.get(youtube_search_url)
        if response_youtube.status_code != 200:
            st.error(f"Failed to fetch data from YouTube for {movie_name}. Status code: {response_youtube.status_code}")
            return None

        soup_youtube = BeautifulSoup(response_youtube.text, 'html.parser')
        video_id = None
        for a in soup_youtube.find_all('a', href=True):
            if '/watch?v=' in a['href']:
                video_id = a['href'].split('v=')[1].split('&')[0]
                break
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"
    except Exception as e:
        st.error(f"Error fetching trailer from YouTube for {movie_name}: {e}")

    return None

# B. Download Trailer
def download_trailer(url, output_dir="downloads"):
    yt = YouTube(url)
    stream = yt.streams.filter(file_extension='mp4').first()
    os.makedirs(output_dir, exist_ok=True)
    video_path = stream.download(output_path=output_dir)
    return video_path

# C. Add Subtitles (Updated for moviepy v2.0+)
def add_subtitles(video_path, subtitle_text, output_dir="edited_videos"):
    video = VideoFileClip(video_path)
    txt_clip = TextClip(
        text=subtitle_text,
        font="Arial",
        fontsize=50,
        color="white"
    ).set_position("bottom").set_duration(video.duration)

    final = CompositeVideoClip([video, txt_clip])
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, os.path.basename(video_path))
    final.write_videofile(output_path, codec="libx264")
    return output_path

# D. Enhance Video Quality (Using moviepy instead of OpenCV)
def enhance_video(input_path, output_dir="enhanced_videos"):
    video = VideoFileClip(input_path)
    enhanced_video = video.fx(lambda clip: clip.set_fps(clip.fps * 1.5))  # Example enhancement: Increase frame rate
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, os.path.basename(input_path))
    enhanced_video.write_videofile(output_path, codec="libx264")
    return output_path

# E. Generate SEO Content (Using OpenAI's gpt-4o)
def generate_seo_content(movie_name):
    try:
        # Define the prompt for SEO content generation
        prompt = f"Generate SEO-optimized title, description, and tags for a movie trailer of {movie_name}. Return the result in JSON format: {{'title': '...', 'description': '...', 'tags': ['...']}}."

        # Call the OpenAI API with gpt-4o
        response = openai.ChatCompletion.create(
            model="gpt-4o",  # Use gpt-4o instead of gpt-3.5-turbo
            messages=[
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": ""}
            ]
        )

        # Extract the generated content
        content = response.choices[0].message.content.strip()
        try:
            seo_data = eval(content)  # Convert the string to a dictionary
        except Exception as e:
            st.error(f"Invalid JSON response from OpenAI: {content}. Error: {e}")
            return (
                f"{movie_name} Official Trailer",
                f"Watch the official trailer for {movie_name}.",
                [movie_name, "movie trailer", "official trailer"]
            )

        # Ensure the required fields are present
        title = seo_data.get("title", f"{movie_name} Official Trailer")
        description = seo_data.get("description", f"Watch the official trailer for {movie_name}.")
        tags = seo_data.get("tags", [movie_name, "movie trailer", "official trailer"])

        return title, description, tags

    except Exception as e:
        st.error(f"Error generating SEO content using OpenAI: {e}")
        # Fallback to default SEO content
        return (
            f"{movie_name} Official Trailer",
            f"Watch the official trailer for {movie_name}.",
            [movie_name, "movie trailer", "official trailer"]
        )

# F. Create Thumbnail (Using PIL instead of OpenCV)
def create_thumbnail(video_path, output_dir="thumbnails"):
    video = VideoFileClip(video_path)
    frame = video.get_frame(1)  # Get the first frame of the video
    thumbnail_path = os.path.join(output_dir, os.path.splitext(os.path.basename(video_path))[0] + ".png")
    os.makedirs(output_dir, exist_ok=True)

    img = Image.fromarray(frame)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype("arial.ttf", 50)
    draw.text((50, 50), "Watch Now!", fill="white", font=font)
    img.save(thumbnail_path)
    return thumbnail_path

# G. Authenticate YouTube API
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

def authenticate_youtube():
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    credentials = flow.run_local_server(port=0)
    from googleapiclient.discovery import build
    return build('youtube', 'v3', credentials=credentials)

# H. Upload to YouTube
def upload_to_youtube(youtube, video_path, title, description, tags):
    request_body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': tags
        },
        'status': {
            'privacyStatus': 'public'
        }
    }

    media = MediaFileUpload(video_path)
    response = youtube.videos().insert(
        part='snippet,status',
        body=request_body,
        media_body=media
    ).execute()

    return response['id']

# -------------------
# Streamlit Interface
# -------------------

st.title("Movie Trailer Editor & YouTube Uploader")

# Input for movie names
movie_names = st.text_area("Enter movie names (one per line):").splitlines()

if st.button("Process Movies"):
    try:
        youtube = authenticate_youtube()

        for movie_name in movie_names:
            st.write(f"Processing movie: {movie_name}")

            # Step 1: Get trailer URL
            trailer_url = get_trailer_url(movie_name)
            if not trailer_url:
                st.error(f"No trailer found for {movie_name}. Skipping...")
                continue
            st.write(f"Trailer URL: {trailer_url}")

            # Step 2: Download trailer
            st.write("Downloading trailer...")
            downloaded_video = download_trailer(trailer_url)
            st.success(f"Trailer downloaded: {downloaded_video}")

            # Step 3: Add subtitles
            st.write("Adding subtitles...")
            subtitled_video = add_subtitles(downloaded_video, f"{movie_name} Trailer")
            st.success(f"Subtitles added: {subtitled_video}")

            # Step 4: Enhance video quality
            st.write("Enhancing video quality...")
            enhanced_video = enhance_video(subtitled_video)
            st.success(f"Video enhanced: {enhanced_video}")

            # Step 5: Generate SEO content
            st.write("Generating SEO content...")
            title, description, tags = generate_seo_content(movie_name)
            st.write(f"Generated SEO Content:\nTitle: {title}\nDescription: {description}\nTags: {tags}")

            # Step 6: Create thumbnail
            st.write("Creating thumbnail...")
            thumbnail_path = create_thumbnail(enhanced_video)
            st.success(f"Thumbnail created: {thumbnail_path}")

            # Step 7: Upload to YouTube
            st.write("Uploading to YouTube...")
            video_id = upload_to_youtube(youtube, enhanced_video, title, description, tags)
            st.success(f"Uploaded to YouTube! Video ID: {video_id}")

    except Exception as e:
        st.error(f"An error occurred: {e}")
