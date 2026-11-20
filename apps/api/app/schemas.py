from pydantic import BaseModel,EmailStr,Field,ConfigDict
from uuid import UUID
class RegisterRequest(BaseModel):
 email:EmailStr
 password:str=Field(min_length=10,max_length=128)
 display_name:str=Field(min_length=1,max_length=120)
 workspace_name:str=Field(min_length=1,max_length=120)
class LoginRequest(BaseModel):
 email:EmailStr
 password:str
class UserView(BaseModel):
 model_config=ConfigDict(from_attributes=True)
 id:UUID
 email:EmailStr
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
