# Java 后端统一入口

这个服务是第一阶段 Java 网关，用来接收前端请求，并把 `/api/**` 和 `/media/**` 转发到现有 Python FastAPI 服务。

## 端口

```text
Java 后端：127.0.0.1:8080
Python 后端：127.0.0.1:18000
```

## 启动

先启动 Python 后端：

```powershell
cd D:\727push\backend
.\.venv\Scripts\activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 18000 --log-level debug
```

再启动 Java 后端：

```powershell
cd D:\727push\java-backend
mvn spring-boot:run
```

检查 Java 后端：

```text
http://127.0.0.1:8080/health
```

检查 Java 到 Python 的代理：

```text
http://127.0.0.1:8080/api/products?page=1&page_size=12&sort=popular
```

## 用户系统接口

注册：

```text
POST http://127.0.0.1:8080/api/auth/register
```

登录：

```text
POST http://127.0.0.1:8080/api/auth/login
```

当前用户：

```text
GET http://127.0.0.1:8080/api/auth/me
Authorization: Bearer <token>
```

第一阶段只支持本地邮箱密码账号。微信、支付宝、GitHub 登录暂不接入，只在数据模型中预留扩展字段。
