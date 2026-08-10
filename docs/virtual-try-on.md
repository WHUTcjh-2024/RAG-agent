# AI 虚拟试穿

商品详情页会上传一张用户全身照，提交异步任务并轮询结果。设计重点参考 Google Shopping Try On：商品级入口、全身照片指导、异步生成、结果回看与明确的“视觉参考而非尺码保证”提示。

## 服务契约

`POST /api/try-on/jobs` 需要已登录用户、`Idempotency-Key` 和 multipart 字段：

- `product_id`：目录中的商品 ID。
- `person_image`：JPG、PNG 或 WebP，最大 12 MB。
- `consent=true`：确认有照片中人物的处理授权。

响应为 `202`，包含任务状态。客户端用带 Bearer Token 的 `GET /api/try-on/jobs/{id}` 轮询 `QUEUED`、`PROCESSING`、`SUCCEEDED` 或 `FAILED`。成功时返回一个 15 分钟有效、仅用于图片加载的签名结果 URL；原始上传照在生成成功或失败后删除，结果默认保留 24 小时。

Python 服务只接受 Java 网关验证 JWT 后注入的可信用户上下文。它会去除上传照片的 EXIF、限制尺寸与像素数、按用户限流、持久化幂等任务，并在推理暂时失败时最多重试两次。不要直接暴露 Python 容器端口。

## 推理提供商

设置 `VTO_PROVIDER_URL` 后即可接入任何满足下列契约的服装虚拟试穿模型服务：

- `POST` multipart，字段为 `person_image`、`garment_image`、`product_id`、`category`、`request_id` 与 `prompt`。
- 成功响应为 `image/*`，或 JSON 的 `image_base64` / `b64_json` / `data[0].b64_json`。
- 可选 `VTO_PROVIDER_API_KEY` 会作为 Bearer Token 转发；生产环境必须使用 HTTPS。

该边界让 GPU/第三方推理服务可独立伸缩，并避免使用简单图片叠加伪装成生成式试穿。
