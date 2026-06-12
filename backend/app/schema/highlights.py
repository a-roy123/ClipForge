from pydantic import BaseModel

class DownloadResponse(BaseModel):
    download_url: str
    expires_in: int