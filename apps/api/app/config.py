from pydantic_settings import BaseSettings,SettingsConfigDict
class Settings(BaseSettings):
 model_config=SettingsConfigDict(env_file=".env",env_file_encoding="utf-8",extra="ignore")
 app_name:str="Creator Intelligence API";app_env:str="development";web_base_url:str="http://localhost:3000"
 database_url:str="postgresql+asyncpg://creator:creator_dev_password@localhost:5432/creator_intelligence";redis_url:str="redis://localhost:6379/0";cors_origins:str="http://localhost:3000"
 jwt_secret:str="dev-only-change-me-to-a-32-byte-random-secret";jwt_issuer:str="creator-intelligence";jwt_access_minutes:int=15;jwt_refresh_days:int=30;cookie_secure:bool=False
 google_client_id:str="";google_client_secret:str="";google_youtube_redirect_uri:str="";youtube_token_encryption_key:str="";youtube_daily_quota_limit:int=10000;youtube_api_key:str=""
 meta_client_id:str="";meta_client_secret:str="";meta_oauth_redirect_uri:str="";meta_graph_version:str="v23.0";social_token_encryption_key:str=""
 ai_api_key:str="";ai_base_url:str="";ai_model:str="";admin_emails:str="";publishing_worker_enabled:bool=False;publishing_worker_poll_seconds:int=3;youtube_publishing_worker_enabled:bool=False;youtube_upload_root:str=''
 google_client_ids:str="";trust_proxy:bool=False
 dodo_api_key:str="";dodo_webhook_secret:str="";dodo_env:str="test";dodo_return_url:str=""
 dodo_product_creator_monthly:str="";dodo_product_creator_yearly:str="";dodo_product_pro_monthly:str="";dodo_product_pro_yearly:str=""
 @property
 def is_production(self)->bool:return self.app_env.lower() in ("production","prod")
 @property
 def google_audiences(self)->list[str]:
  raw=self.google_client_ids or self.google_client_id
  return [x.strip() for x in raw.split(",") if x.strip()]
 @property
 def allowed_origins(self):return [x.strip() for x in self.cors_origins.split(",") if x.strip()]
def production_problems(s:"Settings")->list[str]:
 """Everything that must be true before the API may serve real users."""
 if not s.is_production:return []
 p=[]
 if len(s.jwt_secret)<32 or s.jwt_secret.startswith("dev-only") or "replace-with" in s.jwt_secret:p.append("JWT_SECRET (32+ random characters)")
 if not s.cookie_secure:p.append("COOKIE_SECURE=true")
 if "creator_dev_password" in s.database_url:p.append("DATABASE_URL must not use the development password")
 if any(o.startswith("http://") for o in s.allowed_origins) or not s.allowed_origins:p.append("CORS_ORIGINS must list only https origins")
 if not s.web_base_url.startswith("https://"):p.append("WEB_BASE_URL (https)")
 if s.google_client_id and len(s.youtube_token_encryption_key)<32:p.append("YOUTUBE_TOKEN_ENCRYPTION_KEY")
 if s.meta_client_id and len(s.social_token_encryption_key)<32:p.append("SOCIAL_TOKEN_ENCRYPTION_KEY")
 if s.dodo_api_key and not s.dodo_webhook_secret:p.append("DODO_WEBHOOK_SECRET (required with DODO_API_KEY)")
 if not s.admin_emails.strip():p.append("ADMIN_EMAILS")
 return p
settings=Settings()
