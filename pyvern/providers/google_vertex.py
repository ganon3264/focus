import json
import google.auth
import google.auth.transport.requests
from google.oauth2 import service_account
from .openai_compat import OpenAICompatProvider

class GoogleVertexProvider(OpenAICompatProvider):
    def __init__(self, api_key: str, model: str, params: dict):
        self.credentials = None
        self.project_id = ""
        
        # Try to parse the api_key as Service Account JSON
        try:
            sa_info = json.loads(api_key)
            self.credentials = service_account.Credentials.from_service_account_info(
                sa_info,
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            self.project_id = sa_info.get("project_id", "")
        except Exception:
            pass
        
        region = params.get("vertex_region", "")
        if not self.project_id or not region:
            raise ValueError("Vertex AI requires valid Service Account JSON in API Key and a Region in params")

        base_url = f"https://{region}-aiplatform.googleapis.com/v1beta1/projects/{self.project_id}/locations/{region}/endpoints/openapi/"
        super().__init__(base_url, "", model, params)

    def _extra_headers(self) -> dict:
        headers = super()._extra_headers()
        if self.credentials:
            request = google.auth.transport.requests.Request()
            self.credentials.refresh(request)
            headers["Authorization"] = f"Bearer {self.credentials.token}"
        return headers
