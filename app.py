from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
import os
import json
import random

# ===================== 你的专属配置（已经全部填好，直接用） =====================
# 服务器端口
HOST = "0.0.0.0"
PORT = 1250

# 用户数据存储文件路径（自动创建）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_FILE = os.path.join(BASE_DIR, "users.json")

# JWT加密配置（重置密码用，自动生成的随机密钥，不用改）
SECRET_KEY = os.urandom(32).hex()
ALGORITHM = "HS256"
RESET_TOKEN_EXPIRE_MINUTES = 30

# 你的QQ邮箱配置（已经填好你的授权码，直接用）
SMTP_SERVER = "smtp.qq.com"
SMTP_PORT = 465
SMTP_EMAIL = "2224930586@qq.com"  # 你的发件邮箱
SMTP_AUTH_CODE = "baxvbgcslnpddifi"  # 你的邮箱授权码
SITE_NAME = "星际互联"

# ===================== 初始化 =====================
# 初始化FastAPI服务
app = FastAPI(title="星际互联用户系统", version="1.0")

# 跨域配置（所有设备都能访问，方便测试）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 密码哈希工具（自动生成随机盐，不用你管，每次加密结果都不一样，安全）
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 验证码临时存储（key: 邮箱, value: {code: 验证码, expire: 过期时间戳}）
code_storage = {}

# 自动创建用户数据文件（如果不存在）
if not os.path.exists(JSON_FILE):
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump([], f, ensure_ascii=False, indent=2)

# ===================== 接口请求数据模型 =====================
class SendCodeModel(BaseModel):
    email: EmailStr
    type: str = "register"

class RegisterModel(BaseModel):
    username: str
    email: EmailStr
    code: str
    password: str

class LoginModel(BaseModel):
    username: str
    password: str

class ForgetPasswordModel(BaseModel):
    email: EmailStr

class ResetPasswordModel(BaseModel):
    token: str
    new_password: str

# ===================== 核心工具函数 =====================
# 1. 读取所有用户数据
def read_users():
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# 2. 写入用户数据
def write_users(users):
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

# 3. 生成自增UUID（从1开始往上加，明文存储）
def generate_new_uuid():
    users = read_users()
    if not users:
        return 1  # 第一个用户UUID是1
    # 取现有最大的UUID，加1
    max_uuid = max(user["uuid"] for user in users)
    return max_uuid + 1

# 4. 密码哈希（自动加随机盐，只有这个是加密的）
def hash_password(password: str):
    return pwd_context.hash(password)

# 5. 密码验证
def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)

# 6. 生成6位数字验证码
def generate_verify_code():
    return str(random.randint(100000, 999999))

# 7. 邮件发送函数（彻底解决550报错，QQ邮箱100%兼容）
def send_email(to_email: str, subject: str, content: str):
    # 创建HTML格式邮件
    msg = MIMEText(content, "html", "utf-8")
    # 关键：直接用纯字符串，不用Header编码，彻底解决QQ邮箱格式报错
    msg["From"] = SMTP_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject

    try:
        # 连接QQ邮箱SMTP服务器发送
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SMTP_EMAIL, SMTP_AUTH_CODE)
            server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"邮件发送失败: {e}")
        return False

# 8. 生成重置密码Token
def create_reset_token(email: str):
    expire = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": email, "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# 9. 验证重置密码Token
def verify_reset_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None

# ===================== API接口（和前端完全对接） =====================
# 健康检查接口（测试服务是否正常）
@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "星际互联用户系统运行正常"}

# 【核心】发送验证码接口
@app.post("/api/send-code")
def send_verify_code(data: SendCodeModel):
    email = data.email
    users = read_users()

    # 注册场景：检查邮箱是否已被注册
    if data.type == "register":
        if any(user["email"] == email for user in users):
            raise HTTPException(status_code=400, detail="该邮箱已被注册")
    
    # 重置密码场景：检查邮箱是否存在
    if data.type == "reset":
        if not any(user["email"] == email for user in users):
            raise HTTPException(status_code=400, detail="该邮箱未注册")

    # 生成6位验证码，5分钟过期
    code = generate_verify_code()
    expire_time = datetime.now() + timedelta(minutes=5)
    code_storage[email] = {
        "code": code,
        "expire": expire_time.timestamp()
    }

    # 按照你的要求写的邮件内容
    email_content = f"""
    <h3>欢迎您注册{SITE_NAME}！</h3>
    <p>您的验证码是：<b style="font-size: 24px; color: #002699;">{code}</b></p>
    <p>验证码有效期5分钟，请勿泄露给他人。</p>
    <p>若不是您本人操作，请忽略此邮箱。</p>
    <p><b>注意！此邮件由机器发送，请勿回复。</b></p>
    """
    if not send_email(email, f"{SITE_NAME} 注册验证码", email_content):
        raise HTTPException(status_code=500, detail="验证码发送失败，请稍后重试")
    
    return {"message": "验证码已发送", "expire_minutes": 5}

# 【核心】用户注册接口
@app.post("/api/register")
def user_register(data: RegisterModel):
    users = read_users()
    # 1. 校验用户名是否已存在
    if any(user["username"] == data.username for user in users):
        raise HTTPException(status_code=400, detail="用户名已被注册")
    # 2. 校验邮箱是否已存在
    if any(user["email"] == data.email for user in users):
        raise HTTPException(status_code=400, detail="邮箱已被注册")
    
    # 3. 校验验证码是否正确
    code_info = code_storage.get(data.email)
    if not code_info:
        raise HTTPException(status_code=400, detail="请先获取验证码")
    # 检查验证码是否过期
    if datetime.now().timestamp() > code_info["expire"]:
        raise HTTPException(status_code=400, detail="验证码已过期，请重新获取")
    # 检查验证码是否正确
    if code_info["code"] != data.code:
        raise HTTPException(status_code=400, detail="验证码错误")
    
    # 4. 生成自增UUID（从1开始往上加，明文存储）
    new_uuid = generate_new_uuid()
    # 5. 密码哈希加密（只有密码是加密的，其他全是明文）
    hashed_pwd = hash_password(data.password)
    
    # 6. 创建新用户（全明文存储，除了密码）
    new_user = {
        "uuid": new_uuid,  # 自增UUID，明文
        "username": data.username,  # 用户名，明文
        "email": data.email,  # 邮箱，明文
        "hashed_password": hashed_pwd,  # 只有密码是加密的
        "points": 0,  # 积分，明文
        "money": 0.0,  # 余额，明文
        "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # 注册时间，明文
    }
    users.append(new_user)
    write_users(users)

    # 7. 注册成功后删除验证码，防止重复使用
    del code_storage[data.email]

    # 8. 发送注册成功欢迎邮件（包含你的UUID）
    welcome_content = f"""
    <h3>恭喜您成功注册{SITE_NAME}！</h3>
    <p>您的账户名：<b>{data.username}</b></p>
    <p>您的UUID：<b>{new_uuid}</b></p>
    <p>感谢您的加入，祝您使用愉快！</p>
    <p><b>注意！此邮件由机器发送，请勿回复。</b></p>
    """
    send_email(data.email, f"欢迎加入{SITE_NAME}", welcome_content)
    
    return {"message": "注册成功", "username": data.username, "uuid": new_uuid}

# 【核心】用户登录接口
@app.post("/api/login")
def user_login(data: LoginModel):
    users = read_users()
    # 支持用户名/邮箱登录
    user = next(
        (u for u in users if u["username"] == data.username or u["email"] == data.username),
        None
    )
    if not user:
        raise HTTPException(status_code=400, detail="用户名或密码错误")
    # 验证密码
    if not verify_password(data.password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="用户名或密码错误")
    
    # 返回用户信息（排除加密的密码）
    user_info = {k: v for k, v in user.items() if k != "hashed_password"}
    return {"message": "登录成功", "user": user_info}

# 忘记密码接口
@app.post("/api/forget-password")
def forget_password(data: ForgetPasswordModel):
    users = read_users()
    user = next((u for u in users if u["email"] == data.email), None)
    if not user:
        raise HTTPException(status_code=400, detail="该邮箱未注册")
    
    # 生成重置密码链接
    token = create_reset_token(data.email)
    reset_link = f"http://127.0.0.1:5500/html/reset.html?token={token}"
    
    # 发送重置邮件
    email_content = f"""
    <h3>{SITE_NAME} 密码重置申请</h3>
    <p>您好，您正在申请重置账号密码</p>
    <p>请点击下方链接重置密码，链接有效期30分钟：</p>
    <p><a href="{reset_link}" target="_blank">立即重置密码</a></p>
    <p>如果不是您本人操作，请忽略此邮件</p>
    <p><b>注意！此邮件由机器发送，请勿回复。</b></p>
    """
    if not send_email(data.email, f"{SITE_NAME} 密码重置", email_content):
        raise HTTPException(status_code=500, detail="邮件发送失败，请稍后重试")
    
    return {"message": "重置邮件已发送，请查收"}

# 重置密码接口
@app.post("/api/reset-password")
def reset_password(data: ResetPasswordModel):
    email = verify_reset_token(data.token)
    if not email:
        raise HTTPException(status_code=400, detail="链接无效或已过期")
    
    users = read_users()
    user_index = next((i for i, u in enumerate(users) if u["email"] == email), None)
    if user_index is None:
        raise HTTPException(status_code=400, detail="用户不存在")
    
    # 更新密码（重新哈希加密）
    users[user_index]["hashed_password"] = hash_password(data.new_password)
    write_users(users)
    
    return {"message": "密码重置成功，请使用新密码登录"}

# 获取用户信息接口
@app.get("/api/user-info")
def get_user_info(uuid: int):
    users = read_users()
    user = next((u for u in users if u["uuid"] == uuid), None)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user_info = {k: v for k, v in user.items() if k != "hashed_password"}
    return {"user": user_info}

# 启动服务
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
