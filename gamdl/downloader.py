import base64
import functools
import re
import shutil
import subprocess
from pathlib import Path

import ciso8601
import requests
from mutagen.mp4 import MP4, MP4Cover
from pywidevine import PSSH, Cdm, Device
from yt_dlp import YoutubeDL

from .apple_music_api import AppleMusicApi
from .constants import MP4_TAGS_MAP
from .enums import CoverFormat, DownloadMode, RemuxMode
from .hardcoded_wvd import HARDCODED_WVD
from .itunes_api import ItunesApi
from .models import DownloadQueueItem, UrlInfo


class Downloader:
    ILLEGAL_CHARACTERS_REGEX = r'[\\/:*?"<>|;]'

    def __init__(
        self,
        apple_music_api: AppleMusicApi,
        itunes_api: ItunesApi,
        output_path: Path = Path("./Apple Music"),
        temp_path: Path = Path("./temp"),
        wvd_path: Path = None,
        nm3u8dlre_path: str = "N_m3u8dl-RE",
        mp4decrypt_path: str = "mp4decrypt",
        ffmpeg_path: str = "ffmpeg",
        mp4box_path: str = "MP4Box",
        download_mode: DownloadMode = DownloadMode.YTDLP,
        remux_mode: RemuxMode = RemuxMode.FFMPEG,
        cover_format: CoverFormat = CoverFormat.JPG,
        template_folder_album: str = "{album_artist}/{album}",
        template_folder_compilation: str = "Compilations/{album}",
        template_file_single_disc: str = "{track:02d} {title}",
        template_file_multi_disc: str = "{disc}-{track:02d} {title}",
        template_folder_no_album: str = "{artist}/Unknown Album",
        template_file_no_album: str = "{title}",
        template_date: str = "%Y-%m-%dT%H:%M:%SZ",
        exclude_tags: str = None,
        cover_size: int = 1200,
        truncate: int = 40,
        no_progress: bool = False,
    ):
        self.apple_music_api = apple_music_api
        self.itunes_api = itunes_api
        self.output_path = output_path
        self.temp_path = temp_path
        self.wvd_path = wvd_path
        self.nm3u8dlre_path = nm3u8dlre_path
        self.mp4decrypt_path = mp4decrypt_path
        self.ffmpeg_path = ffmpeg_path
        self.mp4box_path = mp4box_path
        self.download_mode = download_mode
        self.remux_mode = remux_mode
        self.cover_format = cover_format
        self.template_folder_album = template_folder_album
        self.template_folder_compilation = template_folder_compilation
        self.template_file_single_disc = template_file_single_disc
        self.template_file_multi_disc = template_file_multi_disc
        self.template_folder_no_album = template_folder_no_album
        self.template_file_no_album = template_file_no_album
        self.template_date = template_date
        self.exclude_tags = exclude_tags
        self.cover_size = cover_size
        self.truncate = truncate
        self.no_progress = no_progress
        self._set_binaries_path_full()
        self._set_exclude_tags_list()
        self._set_truncate()

    def _set_binaries_path_full(self):
        self.nm3u8dlre_path_full = shutil.which(self.nm3u8dlre_path)
        self.ffmpeg_path_full = shutil.which(self.ffmpeg_path)
        self.mp4box_path_full = shutil.which(self.mp4box_path)
        self.mp4decrypt_path_full = shutil.which(self.mp4decrypt_path)

    def _set_exclude_tags_list(self):
        self.exclude_tags_list = (
            [i.lower() for i in self.exclude_tags.split(",")]
            if self.exclude_tags is not None
            else []
        )

    def _set_truncate(self):
        self.truncate = None if self.truncate < 4 else self.truncate

    def set_cdm(self):
        if self.wvd_path:
            self.cdm = Cdm.from_device(Device.load(self.wvd_path))
        else:
            self.cdm = Cdm.from_device(Device.loads(HARDCODED_WVD))

    def get_url_info(self, url: str) -> UrlInfo:
        url_info = UrlInfo()
        url_regex_result = re.search(
            r"/([a-z]{2})/(album|playlist|song|music-video|post)/([^/]*)(?:/([^/?]*))?(?:\?i=)?([0-9a-z]*)?",
            url,
        )
        url_info.storefront = url_regex_result.group(1)
        url_info.type = (
            "song" if url_regex_result.group(5) else url_regex_result.group(2)
        )
        url_info.id = (
            url_regex_result.group(5)
            or url_regex_result.group(4)
            or url_regex_result.group(3)
        )
        return url_info

    def get_download_queue(self, url_info: UrlInfo) -> list[DownloadQueueItem]:
        download_queue = []
        if url_info.type == "song":
            download_queue.append(
                DownloadQueueItem(self.apple_music_api.get_song(url_info.id))
            )
        elif url_info.type == "album":
            album = self.apple_music_api.get_album(url_info.id)
            download_queue.extend(
                DownloadQueueItem(track)
                for track in album["relationships"]["tracks"]["data"]
            )
        elif url_info.type == "playlist":
            download_queue.extend(
                DownloadQueueItem(track)
                for track in self.apple_music_api.get_playlist(url_info.id)[
                    "relationships"
                ]["tracks"]["data"]
            )
        elif url_info.type == "music-video":
            download_queue.append(
                DownloadQueueItem(self.apple_music_api.get_music_video(url_info.id))
            )
        elif url_info.type == "post":
            download_queue.append(
                DownloadQueueItem(self.apple_music_api.get_post(url_info.id))
            )
        else:
            raise Exception(f"Invalid url type: {url_info.type}")
        return download_queue

    def sanitize_date(self, date: str):
        datetime_obj = ciso8601.parse_datetime(date)
        return datetime_obj.strftime(self.template_date)

    def get_decryption_key(self, pssh: str, track_id: str) -> str:
        pssh_obj = PSSH(pssh.split(",")[-1])
        cdm_session = self.cdm.open()
        challenge = base64.b64encode(
            self.cdm.get_license_challenge(cdm_session, pssh_obj)
        ).decode()
        license = self.apple_music_api.get_widevine_license(
            track_id,
            pssh,
            challenge,
        )
        self.cdm.parse_license(cdm_session, license)
        decryption_key = next(
            i for i in self.cdm.get_keys(cdm_session) if i.type == "CONTENT"
        ).key.hex()
        self.cdm.close(cdm_session)
        return decryption_key

    def download(self, path: Path, stream_url: str):
        if self.download_mode == DownloadMode.YTDLP:
            self.download_ytdlp(path, stream_url)
        elif self.download_mode == DownloadMode.NM3U8DLRE:
            self.download_nm3u8dlre(path, stream_url)

    def download_ytdlp(self, path: Path, stream_url: str):
        with YoutubeDL(
            {
                "quiet": True,
                "no_warnings": True,
                "outtmpl": str(path),
                "allow_unplayable_formats": True,
                "fixup": "never",
                "allowed_extractors": ["generic"],
                "noprogress": self.no_progress,
            }
        ) as ydl:
            ydl.download(stream_url)

    def download_nm3u8dlre(self, path: Path, stream_url: str):
        if self.no_progress:
            subprocess_additional_args = {
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
        else:
            subprocess_additional_args = {}
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                self.nm3u8dlre_path_full,
                stream_url,
                "--binary-merge",
                "--no-log",
                "--log-level",
                "off",
                "--ffmpeg-binary-path",
                self.ffmpeg_path_full,
                "--save-name",
                path.stem,
                "--save-dir",
                path.parent,
                "--tmp-dir",
                path.parent,
            ],
            check=True,
            **subprocess_additional_args,
        )

    def get_sanitized_string(self, dirty_string: str, is_folder: bool) -> str:
        dirty_string = re.sub(self.ILLEGAL_CHARACTERS_REGEX, "_", dirty_string)
        if is_folder:
            dirty_string = dirty_string[: self.truncate]
            if dirty_string.endswith("."):
                dirty_string = dirty_string[:-1] + "_"
        else:
            if self.truncate is not None:
                dirty_string = dirty_string[: self.truncate - 4]
        return dirty_string.strip()

    def get_final_path(self, tags: dict, file_extension: str) -> Path:
        if tags.get("album"):
            final_path_folder = (
                self.template_folder_compilation.split("/")
                if tags.get("compilation")
                else self.template_folder_album.split("/")
            )
            final_path_file = (
                self.template_file_multi_disc.split("/")
                if tags["disc_total"] > 1
                else self.template_file_single_disc.split("/")
            )
        else:
            final_path_folder = self.template_folder_no_album.split("/")
            final_path_file = self.template_file_no_album.split("/")
        final_path_folder = [
            self.get_sanitized_string(i.format(**tags), True) for i in final_path_folder
        ]
        final_path_file = [
            self.get_sanitized_string(i.format(**tags), True)
            for i in final_path_file[:-1]
        ] + [
            self.get_sanitized_string(final_path_file[-1].format(**tags), False)
            + file_extension
        ]
        return self.output_path.joinpath(*final_path_folder).joinpath(*final_path_file)

    def get_cover_url(self, metadata: dict) -> str:
        return self._get_cover_url(metadata["attributes"]["artwork"]["url"])

    def _get_cover_url(self, cover_url_template: str) -> str:
        return re.sub(
            r"\{w\}x\{h\}([a-z]{2})\.jpg",
            f"{self.cover_size}x{self.cover_size}bb.{self.cover_format.value}",
            cover_url_template,
        )

    @staticmethod
    @functools.lru_cache()
    def get_url_response_bytes(url: str) -> bytes:
        return requests.get(url).content

    def apply_tags(
        self,
        path: Path,
        tags: dict,
        cover_url: str,
    ):
        to_apply_tags = [
            tag_name
            for tag_name in tags.keys()
            if tag_name not in self.exclude_tags_list
        ]
        mp4_tags = {}
        for tag_name in to_apply_tags:
            if tag_name in ("disc", "disc_total"):
                if mp4_tags.get("disk") is None:
                    mp4_tags["disk"] = [[0, 0]]
                if tag_name == "disc":
                    mp4_tags["disk"][0][0] = tags[tag_name]
                elif tag_name == "disc_total":
                    mp4_tags["disk"][0][1] = tags[tag_name]
            elif tag_name in ("track", "track_total"):
                if mp4_tags.get("trkn") is None:
                    mp4_tags["trkn"] = [[0, 0]]
                if tag_name == "track":
                    mp4_tags["trkn"][0][0] = tags[tag_name]
                elif tag_name == "track_total":
                    mp4_tags["trkn"][0][1] = tags[tag_name]
            elif tag_name == "compilation":
                mp4_tags["cpil"] = tags["compilation"]
            elif tag_name == "gapless":
                mp4_tags["pgap"] = tags["gapless"]
            elif (
                MP4_TAGS_MAP.get(tag_name) is not None
                and tags.get(tag_name) is not None
            ):
                mp4_tags[MP4_TAGS_MAP[tag_name]] = [tags[tag_name]]
        if "cover" not in self.exclude_tags_list:
            mp4_tags["covr"] = [
                MP4Cover(
                    self.get_url_response_bytes(cover_url),
                    imageformat=(
                        MP4Cover.FORMAT_JPEG
                        if self.cover_format == CoverFormat.JPG
                        else MP4Cover.FORMAT_PNG
                    ),
                )
            ]
        mp4 = MP4(path)
        mp4.clear()
        mp4.update(mp4_tags)
        mp4.save()

    def move_to_output_path(
        self,
        remuxed_path: Path,
        final_path: Path,
    ):
        final_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(remuxed_path, final_path)

    @functools.lru_cache()
    def save_cover(self, cover_path: Path, cover_url: str):
        cover_path.write_bytes(self.get_url_response_bytes(cover_url))

    def cleanup_temp_path(self):
        shutil.rmtree(self.temp_path)
