import requests
import json
import uuid
import os
import glob
import sys
import re
from datetime import datetime
from typing import List, Dict, Any

class BaseProvider:
    def __init__(self, name):
        self.name = name
    def get_user_agent(self):
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    def get_timeout(self):
        return 30

class PlutoProvider(BaseProvider):
    """Provider for Pluto TV with HD Resolution, Categories, and Regional EPGs"""

    def __init__(self):
        super().__init__("pluto")
        self.device_id = str(uuid.uuid1())
        self.session_token = None
        self.stitcher_params = ""
        self.session_expires_at = 0
        
        # Configuration from environment (e.g., 'us', 'gb', 'ca')
        self.region = os.getenv('PLUTO_REGION', 'us').lower()
        
        # Optimized IPs from official source to fix freezing/commercial issues
        self.x_forward = {
            "us": "185.236.200.172", "gb": "84.17.50.173", "ca": "192.206.151.131", 
            "fr": "176.31.84.249", "de": "217.94.184.66", "es": "88.26.241.248", 
            "it": "131.114.130.239", "br": "177.192.255.38", "mx": "200.68.128.83", 
            "ar": "168.226.232.228", "cl": "181.200.138.240", "no": "78.26.38.103", 
            "se": "185.6.8.2", "dk": "192.36.27.7",
        }
        
        self.headers = {
            'authority': 'boot.pluto.tv',
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'origin': 'https://pluto.tv',
            'referer': 'https://pluto.tv/',
            'user-agent': self.get_user_agent(),
        }
        
        if self.region in self.x_forward:
            self.headers["X-Forwarded-For"] = self.x_forward[self.region]

    def _get_session_token(self) -> str:
        if self.session_token and datetime.now().timestamp() < self.session_expires_at:
            return self.session_token
        try:
            url = 'https://boot.pluto.tv/v4/start'
            params = {
                'appName': 'web', 'appVersion': '8.1.0', 'deviceVersion': '133.0.0',
                'deviceModel': 'web', 'deviceMake': 'chrome', 'deviceType': 'web',
                'clientID': self.device_id, 'clientModelNumber': '1.0.0', 'serverSideAds': 'false',
                'architecture': 'x86_64', 'buildVersion': '1.0.0', 'drmCapabilities': 'widevine:L3'
            }
            response = requests.get(url, headers=self.headers, params=params, timeout=self.get_timeout())
            data = response.json()
            self.session_token = data.get('sessionToken', '')
            self.stitcher_params = data.get('stitcherParams', '')
            self.session_expires_at = datetime.now().timestamp() + (4 * 3600)
            return self.session_token
        except Exception: return ""

    def get_channels(self) -> List[Dict[str, Any]]:
        try:
            token = self._get_session_token()
            if not token: return []
            
            url = "https://service-channels.clusters.pluto.tv/v2/guide/channels"
            headers = self.headers.copy()
            headers['authorization'] = f'Bearer {token}'
            
            response = requests.get(url, params={'limit': '1000'}, headers=headers, timeout=self.get_timeout())
            channel_data = response.json().get("data", [])
            
            processed_channels = []
            for channel in channel_data:
                channel_id, name = channel.get('id'), channel.get('name')
                if not channel_id or not name: continue
                
                logo = next((img.get('url') for img in channel.get('images', []) if img.get('type') == 'colorLogoPNG'), "")
                
                # Forced category name for all channels
                group = "Fast Pluto"
                
                sid = str(uuid.uuid4())
                quality_suffix = (f"&quality=720p&deviceMake=chrome&deviceType=web&deviceModel=web"
                                  f"&deviceVersion=133.0.0&architecture=x86_64&buildVersion=1.0.0"
                                  f"&includeExtendedEvents=true&masterJWTPassthrough=true")

                stream_url = (f"https://ipv4.pluto.tv/api/tn/video/playout/v2/stitch/hls/channel/{channel_id}/master.m3u8"
                              f"?{self.stitcher_params}&jwt={token}{quality_suffix}")
                
                processed_channels.append({'id': str(channel_id), 'name': name, 'stream_url': stream_url, 'logo': logo, 'group': group})
            return processed_channels
        except Exception: return []

    def generate_m3u(self, channels):
        # Uses the specific regional EPG URL in the header as requested
        m3u = f'#EXTM3U url-tvg="https://github.com/matthuisman/i.mjh.nz/raw/master/PlutoTV/{self.region}.xml.gz"\n'
        for ch in channels:
            
