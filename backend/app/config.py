from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # WordPress.com OAuth2
    wordpress_site: str = ""           # e.g. marziblogs1.wordpress.com
    wordpress_client_id: str = ""      # OAuth app Client ID
    wordpress_client_secret: str = ""  # OAuth app Client Secret
    wordpress_access_token: str = ""   # OAuth2 bearer token (obtained via auth flow)

    # Gemini
    gemini_api_key: str = "AIzaSyBP61Ii7krxZogUo71cbP94vvjXC2MBRB8"

    # Site
    site_url: str = "https://marziblogs.web.app"
    site_name: str = "Marzi Life Blog"
    organization_name: str = "Marzi"
    default_author: str = "Marzi Life"

    # Generation
    num_variations: int = 3
    dedup_similarity_threshold: float = 0.85

    # CORS
    cors_origins: list[str] = ["http://localhost:5173"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
