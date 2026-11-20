from pydantic import BaseModel,EmailStr,Field,ConfigDict
from uuid import UUID
class RegisterRequest(BaseModel):
 email:EmailStr
 password:str=Field(min_length=10,max_length=128)
 display_name:str=Field(min_length=1,max_length=120)
 workspace_name:str=Field(min_length=1,max_length=120)
 username:str|None=Field(default=None,min_length=3,max_length=24,pattern=r"^[a-z0-9_]+$")
class LoginRequest(BaseModel):
 identifier:str|None=Field(default=None,min_length=3,max_length=320)
 email:str|None=Field(default=None,max_length=320)
 password:str=Field(min_length=1,max_length=128)
 @property
 def login_name(self)->str:return (self.identifier or self.email or "").strip().lower()
class GoogleLoginRequest(BaseModel):
 credential:str=Field(min_length=20,max_length=8192)
 workspace_name:str|None=Field(default=None,max_length=120)
class UsernameRequest(BaseModel):
 username:str=Field(min_length=3,max_length=24,pattern=r"^[a-z0-9_]+$")
class UserView(BaseModel):
 model_config=ConfigDict(from_attributes=True)
 id:UUID
 email:EmailStr
 username:str|None=None
 display_name:str
 email_verified:bool
class WorkspaceView(BaseModel):
 id:UUID
 name:str
 slug:str
 role:str
class AuthResponse(BaseModel):
 access_token:str
 token_type:str="bearer"
 expires_in:int
 user:UserView
 workspace:WorkspaceView
