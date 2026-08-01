from __future__ import annotations

import urllib.robotparser
from urllib.parse import urljoin, urlparse

import httpx

from app.services.material_harvester import MaterialHarvester, MaterialHarvesterError


class SafeMaterialHarvester(MaterialHarvester):
    """Material harvester with explicit robots redirect validation.

    httpx must not follow a robots.txt redirect before the destination has gone
    through the same public-address checks as article pages.
    """

    def _check_robots(self, url: str) -> None:
        parsed = urlparse(url)
        current = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        parser = urllib.robotparser.RobotFileParser()
        for _ in range(4):
            current = self.validate_public_url(current)
            try:
                response = httpx.get(
                    current,
                    headers=self.headers,
                    timeout=min(max(self.settings.request_timeout_seconds, 10.0), 30.0),
                    follow_redirects=False,
                )
            except httpx.HTTPError:
                parser.parse([])
                break
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    parser.parse([])
                    break
                current = urljoin(current, location)
                continue
            if response.status_code == 200:
                parser.set_url(current)
                parser.parse(response.text.splitlines())
            elif response.status_code in {401, 403}:
                raise MaterialHarvesterError("站点 robots.txt 禁止自动访问")
            else:
                parser.parse([])
            break
        else:
            raise MaterialHarvesterError("robots.txt 重定向次数过多")
        if not parser.can_fetch(self.settings.material_user_agent, url):
            raise MaterialHarvesterError("站点 robots.txt 不允许采集该页面")
