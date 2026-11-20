from pydantic_settings import BaseSettings,SettingsConfigDict
class Settings(BaseSettings):
 model_config=SettingsConfigDict(env_file=".env",env_file_encoding="utf-8",extra="ignore")
 app_name:str="Creator Intelligence API"
 app_env:str="development"
 web_base_url:str="http://localhost:3000"
 database_url:str="postgresql+asyncpg://creator:creator_dev_password@localhost:5432/creator_intelligence"
 redis_url:str="redis://localhost:6379/0"
 cors_origins:str="http://localhost:3000"
 jwt_secret:str="dev-only-change-me-to-a-32-byte-random-secret"
 jwt_issuer:str="creator-intelligence"
 jwt_access_minutes:int=15
 jwt_refresh_days:int=30
 cookie_secure:bool=False
 google_client_id:str=""
 google_client_secret:str=""
 google_youtube_redirect_uri:str=""
 youtube_token_encryption_key:str=""
 youtube_daily_quota_limit:int=10000
 youtube_api_key:str=""
 meta_client_id:str=""
 meta_client_secret:str=""
 meta_oauth_redirect_uri:str=""
 meta_graph_version:str="v23.0"
 social_token_encryption_key:str=""
 ai_api_key:str=""
 ai_base_url:str=""
 ai_model:str=""
 @property
 def allowed_origins(self)->list[str]:
  return [x.strip() for x in self.cors_origins.split(",") if x.strip()]
settings=Settings()
