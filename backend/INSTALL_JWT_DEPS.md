# 安装 JWT 依赖

## 问题
后端服务报错：`module 'jwt' has no attribute 'encode'`

这是因为缺少 `PyJWT` 包。

## 解决方法

### 方法 1: 在 WSL 中安装（推荐）

```bash
# 1. 更新 pip
sudo apt update
sudo apt install python3-pip

# 2. 安装依赖
cd /mnt/d/Study/Agents/MA/data3/zb/MyAgent/backend
pip3 install PyJWT bcrypt

# 或者使用 python3 -m pip
python3 -m pip install PyJWT bcrypt
```

### 方法 2: 在 Windows 中安装（如果使用 Windows Python）

```powershell
# 在 Windows PowerShell 中执行
cd D:\Study\Agents\MA\data3\zb\MyAgent\backend
pip install PyJWT bcrypt
```

### 方法 3: 使用虚拟环境

```bash
# 1. 创建虚拟环境
cd /mnt/d/Study/Agents/MA/data3/zb/MyAgent/backend
python3 -m venv venv

# 2. 激活虚拟环境
source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt
```

## 验证安装

安装完成后，运行以下命令验证：

```bash
python3 -c "import jwt; print(jwt.__version__)"
```

应该输出版本号，如 `2.8.0`。

## 重启后端服务

安装完成后，重启后端服务：

```bash
cd /mnt/d/Study/Agents/MA/data3/zb/MyAgent/backend
python3 -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## requirements.txt

项目已创建 `backend/requirements.txt`，包含所有必要的依赖：

```
PyJWT>=2.8.0
bcrypt>=4.1.0
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
pymysql>=1.1.0
sqlalchemy>=2.0.0
pymilvus>=2.3.0
dashscope>=1.14.0
langchain>=0.1.0
langgraph>=0.0.20
...
```

可以使用以下命令一键安装所有依赖：

```bash
pip install -r requirements.txt
```
