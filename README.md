# RAG-agent

这个项目正在开发中。

这是一个 React + Java + Python 的本地智能穿搭顾问项目。

## 服务划分

```text
frontend       React/Vite 前端，运行在 127.0.0.1:5173
java-backend   Java Spring Boot 统一入口，运行在 127.0.0.1:8080
backend        Python FastAPI RAG 服务，运行在 127.0.0.1:18000
```

## 本地启动顺序

### 1. 启动 Python 后端

```powershell
cd D:\727push\backend
.\.venv\Scripts\activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 18000 --log-level debug
```

检查：

```text
http://127.0.0.1:18000/health
```

### 2. 启动 Java 后端

```powershell
cd D:\727push\java-backend
mvn spring-boot:run
```

检查：

```text
http://127.0.0.1:8080/health
http://127.0.0.1:8080/api/products?page=1&page_size=12&sort=popular
```

### 3. 启动前端

```powershell
cd D:\727push\frontend
npm run dev
```

打开：

```text
http://127.0.0.1:5173/
```

## 当前阶段

第一阶段中，Java 后端作为统一入口，先代理请求到 Python。后续可以逐步把用户、商品、购物车、订单等主业务迁移到 Java，Python 保留 RAG、模型调用和向量检索能力。

## 用户系统阶段

Java 后端现在开始承接主业务能力。第一阶段支持：

```text
POST /api/auth/register
POST /api/auth/login
GET  /api/auth/me
```

用户系统使用邮箱密码账号和 JWT。密码使用 BCrypt 加密保存。除 Java 自己处理的认证接口外，其他 `/api/**` 和 `/media/**` 请求仍然由 Java 转发到 Python。
