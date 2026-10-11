# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic

import os
import re
import json
import random
import asyncio
import aiohttp
from pathlib import Path
import yt_dlp
from py_yt import Playlist, VideosSearch

from anony import logger
from anony.helpers import Track, utils


class DummyLogger:
    def debug(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass


class YouTube:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.cookies = []
        self.checked = False
        self.cookie_dir = "anony/cookies"
        self.warned = False
        self.api_url = os.getenv("MUSIC_API_URL", "https://music.yukiapi.site").rstrip("/")
        self.api_key = os.getenv("MUSIC_API_KEY", "yuki_96fcd2d09a8d4f1e36896505bd6ebda8")
        self._session: aiohttp.ClientSession | None = None

        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )
        self.iregex = re.compile(
            r"https?://(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be)"
            r"(?!/(watch\?v=[A-Za-z0-9_-]{11}|shorts/[A-Za-z0-9_-]{11}"
            r"|playlist\?list=PL[A-Za-z0-9_-]+|[A-Za-z0-9_-]{11}))\S*"
        )
        self.spotify_regex = re.compile(
            r"https?://(?:open\.)?spotify\.com/(track|album|playlist)/[a-zA-Z0-9]+"
        )

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=100,
                keepalive_timeout=300,
                enable_cleanup_closed=True,
                force_close=False,
                ssl=False,
            )
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=45, connect=10),
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def get_cookies(self):
        if not self.checked:
            if os.path.exists(self.cookie_dir):
                for file in os.listdir(self.cookie_dir):
                    if file.endswith(".txt"):
                        self.cookies.append(f"{self.cookie_dir}/{file}")
            self.checked = True
        if not self.cookies:
            if not self.warned:
                self.warned = True
                logger.warning("Cookies are missing; downloads might fail.")
            return None
        return random.choice(self.cookies)

    async def save_cookies(self, urls: list[str]) -> None:
        logger.info("Saving cookies from urls...")
        os.makedirs(self.cookie_dir, exist_ok=True)
        session = await self.get_session()
        for url in urls:
            name = url.split("/")[-1]
            link = "https://batbin.me/raw/" + name
            try:
                async with session.get(link) as resp:
                    resp.raise_for_status()
                    with open(f"{self.cookie_dir}/{name}.txt", "wb") as fw:
                        fw.write(await resp.read())
            except Exception as e:
                logger.warning(f"Failed to fetch cookie {url}: {e}")
        logger.info(f"Cookies saved in {self.cookie_dir}.")

    def valid(self, url: str) -> bool:
        if bool(re.match(self.spotify_regex, url)):
            return True
        return bool(re.match(self.regex, url))

    def invalid(self, url: str) -> bool:
        if bool(re.match(self.spotify_regex, url)):
            return False
        return bool(re.match(self.iregex, url))

    async def search(self, query: str, m_id: int, video: bool = False) -> Track | None:
        session = await self.get_session()

        # Handle Spotify Track / URL
        if "open.spotify.com" in query or "spotify:" in query:
            try:
                clean_url = query.split("?")[0]
                oembed_url = f"https://open.spotify.com/oembed?url={clean_url}"
                async with session.get(oembed_url) as resp:
                    if resp.status == 200:
                        sp_data = await resp.json()
                        sp_title = sp_data.get("title")
                        sp_author = sp_data.get("author_name")
                        if sp_title:
                            query = f"{sp_title} {sp_author}".strip() if sp_author else sp_title
            except Exception as e:
                logger.warning(f"Spotify oEmbed resolution failed: {e}")

        # Primary: py_yt VideosSearch (Direct, reliable, official YouTube search results)
        try:
            _search = VideosSearch(query, limit=1, with_live=False)
            results = await _search.next()
            if results and results.get("result"):
                data = results["result"][0]
                dur = data.get("duration", "0:00")
                raw_title = data.get("title", "Unknown Title")
                clean_title = utils.scale_title(raw_title, 25)
                v_id = data.get("id")
                thumbnails = data.get("thumbnails", [{}])
                thumb_url = thumbnails[-1].get("url", "").split("?")[0] if thumbnails else f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg"
                channel_name = data.get("channel", {}).get("name", "")
                view_cnt = data.get("viewCount", {}).get("short", "")
                link = data.get("link", f"https://www.youtube.com/watch?v={v_id}")

                return Track(
                    id=v_id,
                    channel_name=channel_name,
                    duration=dur,
                    duration_sec=utils.to_seconds(dur),
                    message_id=m_id,
                    title=clean_title,
                    thumbnail=thumb_url,
                    url=link,
                    view_count=view_cnt,
                    video=video,
                )
        except Exception as e:
            logger.warning(f"py_yt search error: {e}")

        # Fallback: yt-dlp flat search if py-yt-search fails
        try:
            ydl_opts = {
                "format": "bestaudio/best",
                "default_search": "ytsearch1:",
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
            }
            loop = asyncio.get_running_loop()
            info = await loop.run_in_executor(
                None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(query, download=False)
            )
            if info and "entries" in info and info["entries"]:
                first = info["entries"][0]
                v_id = first.get("id")
                dur_sec = int(first.get("duration") or 0)
                dur = f"{dur_sec // 60}:{dur_sec % 60:02d}"
                raw_title = first.get("title", "Unknown Title")
                clean_title = utils.scale_title(raw_title, 25)
                return Track(
                    id=v_id,
                    channel_name=first.get("uploader", "") or first.get("channel", ""),
                    duration=dur,
                    duration_sec=dur_sec,
                    message_id=m_id,
                    title=clean_title,
                    thumbnail=f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg",
                    url=f"https://www.youtube.com/watch?v={v_id}",
                    view_count="",
                    video=video,
                )
        except Exception as e:
            logger.warning(f"yt-dlp fallback search error: {e}")

        return None

    async def playlist(self, limit: int, user: str, url: str, video: bool) -> list[Track | None]:
        tracks = []
        session = await self.get_session()

        # Handle Spotify Playlist or Album
        if "open.spotify.com/playlist" in url or "open.spotify.com/album" in url:
            try:
                clean_url = url.split("?")[0]
                embed_url = clean_url.replace("open.spotify.com/", "open.spotify.com/embed/")
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                async with session.get(embed_url, headers=headers) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html)
                        if m:
                            d = json.loads(m.group(1))
                            sp_list = (
                                d.get("props", {})
                                .get("pageProps", {})
                                .get("state", {})
                                .get("data", {})
                                .get("entity", {})
                                .get("trackList", [])
                            )
                            for item in sp_list[:limit]:
                                title = item.get("title", "")
                                artist = item.get("subtitle", "")
                                if title:
                                    search_query = f"{title} {artist}".strip()
                                    resolved = await self.search(search_query, 0, video=video)
                                    if resolved:
                                        resolved.user = user
                                        tracks.append(resolved)
            except Exception as e:
                logger.warning(f"Spotify playlist extraction error: {e}")

            if tracks:
                return tracks

        # Handle YouTube Playlist via py_yt
        try:
            plist = await Playlist.get(url)
            for data in plist.get("videos", [])[:limit]:
                track = Track(
                    id=data.get("id"),
                    channel_name=data.get("channel", {}).get("name", ""),
                    duration=data.get("duration", "0:00"),
                    duration_sec=utils.to_seconds(data.get("duration", "0:00")),
                    title=utils.scale_title(data.get("title", "Track"), 25),
                    thumbnail=data.get("thumbnails", [{}])[-1].get("url", "").split("?")[0],
                    url=data.get("link", "").split("&list=")[0],
                    user=user,
                    view_count="",
                    video=video,
                )
                tracks.append(track)
        except Exception:
            pass

        # Fallback YouTube Playlist via yt_dlp flat extraction
        if not tracks:
            try:
                def _extract_flat():
                    ydl_opts = {
                        "extract_flat": "in_playlist",
                        "skip_download": True,
                        "quiet": True,
                        "playlist_items": f"1-{limit}",
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        return info.get("entries", [])

                entries = await asyncio.to_thread(_extract_flat)
                for item in entries[:limit]:
                    if not item:
                        continue
                    v_id = item.get("id")
                    if not v_id:
                        continue
                    t_title = utils.scale_title(item.get("title") or "Track", 25)
                    d_sec = int(item.get("duration") or 0)
                    t_dur = f"{d_sec // 60}:{d_sec % 60:02d}"
                    track = Track(
                        id=v_id,
                        channel_name=item.get("uploader", ""),
                        duration=t_dur,
                        duration_sec=d_sec,
                        title=t_title,
                        thumbnail=f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg",
                        url=f"https://www.youtube.com/watch?v={v_id}",
                        user=user,
                        view_count="",
                        video=video,
                    )
                    tracks.append(track)
            except Exception as e:
                logger.warning(f"yt_dlp playlist fallback error: {e}")

        return tracks

    async def download(self, video_id: str, video: bool = False) -> str | None:
        url = self.base + video_id
        ext = "mp4" if video else "mp3"
        filename = f"downloads/{video_id}.{ext}"

        if Path(filename).exists() and os.path.getsize(filename) > 10000:
            return filename

        os.makedirs("downloads", exist_ok=True)

        # Tier 1: Public Yuki API High-Speed Stream Ingestion (Persistent keep-alive connection)
        try:
            session = await self.get_session()
            stream_url = (
                f"{self.api_url}/stream/{video_id}?type=video&key={self.api_key}"
                if video
                else f"{self.api_url}/stream/{video_id}?key={self.api_key}"
            )
            async with session.get(stream_url) as resp:
                if resp.status == 200:
                    c_type = resp.headers.get("Content-Type", "").lower()
                    if (video and "video" in c_type) or (not video and "audio" in c_type):
                        with open(filename, "wb") as f:
                            async for chunk in resp.content.iter_chunked(65536):
                                f.write(chunk)
                        if os.path.exists(filename) and os.path.getsize(filename) > 10000:
                            logger.info(f"Yuki API successfully downloaded {video_id} ({os.path.getsize(filename)} bytes)")
                            return filename
                        else:
                            if os.path.exists(filename):
                                os.remove(filename)
        except Exception as e:
            logger.warning(f"Yuki API stream error for {video_id}: {e}")
            if os.path.exists(filename):
                os.remove(filename)

        # Tier 2: yt-dlp Native Download Fallback
        cookie = self.get_cookies()
        base_opts = {
            "outtmpl": "downloads/%(id)s.%(ext)s",
            "quiet": True,
            "noplaylist": True,
            "geo_bypass": True,
            "no_warnings": True,
            "overwrites": False,
            "logger": DummyLogger(),
            "nocheckcertificate": True,
            "cookiefile": cookie,
            "remote_components": ["ejs:github"],
        }

        if video:
            ydl_opts = {
                **base_opts,
                "format": "(bestvideo[height<=?720][width<=?1280][ext=mp4])+(bestaudio)",
                "merge_output_format": "mp4",
            }
        else:
            ydl_opts = {
                **base_opts,
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
            }

        def _download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    ydl.download([url])
                except (yt_dlp.utils.DownloadError, yt_dlp.utils.ExtractorError):
                    return None
                except Exception as ex:
                    logger.warning(f"yt-dlp download failed: {ex}")
                    return None
            return filename

        return await asyncio.to_thread(_download)
