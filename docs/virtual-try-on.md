# AI 虚拟模特试穿

该服务不接收用户照片。用户输入身高、体重、三围等身体参数，系统生成匿名成年虚拟模特，再把目录商品渲染到该模特上。生成结果只用于视觉参考，不代表真实尺码或合身度。

## API 契约

`POST /api/try-on/jobs` 需要登录态、`Idempotency-Key` 和 JSON：

```json
{
  "product_id": "0000000001",
  "body_profile": {
    "height_cm": 168,
    "weight_kg": 58,
    "chest_cm": 88,
    "waist_cm": 70,
    "hip_cm": 94,
    "shoulder_cm": 40,
    "inseam_cm": 76,
    "presentation": "NEUTRAL",
    "body_shape": "BALANCED",
    "skin_tone": "MEDIUM",
    "fit_preference": "REGULAR"
  }
}
```

响应为 `202`。客户端通过 `GET /api/try-on/jobs/{id}` 轮询 `QUEUED`、`PROCESSING`、`SUCCEEDED` 或 `FAILED`。成功结果使用 15 分钟签名 URL，默认保留 24 小时；主动保存后保留 7 天。

消费闭环接口：

- `GET /api/try-on/jobs`：最近试穿。
- `POST /api/try-on/jobs/{id}/save`：保存或取消保存。
- `POST /api/try-on/jobs/{id}/share`：创建短时分享地址。
- `POST /api/try-on/jobs/{id}/feedback`：记录质量评分与问题类型。
- `DELETE /api/try-on/jobs/{id}`：立即删除任务及结果。

## 推理提供方

`VTO_PROVIDER_URL` 接收 multipart：

- 文本字段：`product_id`、`category`、`request_id`、`body_profile`、`prompt`。
- 文件字段：`garment_image`。
- 返回 `image/*`，或 JSON 中的 `image_base64` / `b64_json` / `data[0].b64_json`。

提示词明确要求生成非真实、不可识别的成年合成模特，不允许复刻真人身份。

## 生产架构

设置 `VTO_REDIS_URL` 后，API 使用 Redis 共享任务状态和可靠队列，`tryon-worker` 独立消费任务；处理中的消息在 Worker 重启时会重新入队，任务 claim 保证重复消息不会重复推理。

设置 `VTO_S3_BUCKET` 后，结果存入私有 S3 兼容对象存储。`docker-compose.yml` 默认提供 Redis、独立 Worker 和 MinIO；外部仍只暴露前端端口。

OpenTelemetry 指标包括：

- `vto.jobs.submitted`
- `vto.jobs.completed`
- `vto.provider.duration`
- `vto.queue.duration`

生产环境必须配置 HTTPS 推理地址、随机结果签名密钥、Redis 密码和私有对象存储凭据。
