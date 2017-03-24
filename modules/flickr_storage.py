import os
import re
import __main__
import webbrowser
import time
import datetime
import urllib2
from storage import Storage
import flickr_api
from flickr_api.api import flickr
from file_info import FileInfo
from folder_info import FolderInfo

MAX_PAGES = 100
TOKEN_FILENAME = '.flickrToken'

class FlickrStorage(Storage):

    def __init__(self, config):
        self._is_authenticated = False
        self._user = None
        self._api_key = config.flickr['api_key']
        self._api_secret = config.flickr['api_secret']
        self._retry = int(config.network['retry'])
        self._throttling = float(config.network['throttling'])
        self._include = config.files['flickr_include']
        self._include_dir = config.files['flickr_include_dir']
        self._exclude = config.files['flickr_exclude']
        self._exclude_dir = config.files['flickr_exclude_dir']

    def list_folders(self):
        self._authenticate()
        all_photosets = []
        page = 1
        total_pages = 0
        for i in range(0, MAX_PAGES):
            paged_photosets = self._call_remote(self._user.getPhotosets, page=page)
            all_photosets += paged_photosets
            total_pages = paged_photosets.info.pages
            page = paged_photosets.info.page
            if page >= total_pages:
                break

        self._photosets = {x.id: x for x in all_photosets}
        folders = [FolderInfo(id=x.id, name=x.title) for x in all_photosets]
        return [x for x in folders 
            if (not self._include_dir or re.search(self._include_dir, x.name, flags=re.IGNORECASE)) and
                (not self._exclude_dir or not re.search(self._exclude_dir, x.name, flags=re.IGNORECASE))]

    def list_files(self, folder):
        self._authenticate()
        all_photos = []
        page = 1
        total_pages = 0
        photoset = self._photosets[folder.id]
        for i in range(0, MAX_PAGES):
            paged_photos = self._call_remote(photoset.getPhotos, extras='original_format,tags')
            all_photos += paged_photos
            total_pages = paged_photos.info.pages
            page = paged_photos.info.page
            if page >= total_pages:
                break

        files = [self._get_file_info(x) for x in all_photos]
        return [x for x in files 
            if (not self._include or re.search(self._include, x.name, flags=re.IGNORECASE)) and
                (not self._exclude or not re.search(self._exclude, x.name, flags=re.IGNORECASE))]

    def _get_file_info(self, photo):
        name = photo.title if photo.title else photo.id
        checksum = None
        if photo.originalformat:
            name += "." + photo.originalformat
        if photo.tags:
            tags = photo.tags.split()
            checksum = next((parts[1] for parts in (tag.split('=') for tag in tags) if parts[0] == "checksum:md5"), None)
        return FileInfo(id=photo.id, name=name, checksum=checksum)

    def _authenticate(self):
        if self._is_authenticated:
            return

        flickr_api.set_keys(api_key = self._api_key, api_secret = self._api_secret)

        token_path = os.path.join(os.path.split(os.path.abspath(__main__.__file__))[0], TOKEN_FILENAME)
        if os.path.isfile(token_path):
           auth_handler = flickr_api.auth.AuthHandler.load(token_path) 

        else:
            auth_handler = flickr_api.auth.AuthHandler()
            permissions_requested = "read"
            url = auth_handler.get_authorization_url(permissions_requested)
            webbrowser.open(url)
            print "Please enter the OAuth verifier tag once logged in:"
            verifier_code = raw_input("> ")
            auth_handler.set_verifier(verifier_code)
            auth_handler.save(token_path)

        flickr_api.set_auth_handler(auth_handler)
        self._user = flickr_api.test.login()
        self._is_authenticated = True

    def _call_remote(self, fn, **kwargs):
        backoff = [0, 1, 3, 5, 10, 30, 60]
        if self._throttling > 0:
            time.sleep(self._throttling)
        for i in range(self._retry):
            if i > 0:
                time.sleep(backoff[i] if i < len(backoff) else backoff[-1])
            try:
                return fn(**kwargs)
            except urllib2.URLError:
                pass
        return fn(**kwargs)