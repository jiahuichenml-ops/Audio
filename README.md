# 语音约碰面地点

同一座城市内，按住说话，为两个人找中间附近的碰面地点。

当前进度：后端 `GET /health`、`POST /upload`、`POST /asr`、`POST /extract`、`POST /search` + 前端本地录音。播报尚未实现；前端仍不调用业务接口。

## 环境依赖

- Python 3.11
- Node.js 22.12 及以上的 22.x
- **上传接口需要 `ffprobe`**（FFmpeg 自带）。它只探测真实容器、编码和时长，**不会转码**。本机当前若未安装，真实上传会返回 502。macOS 安装（由你执行，不要省略）：

```bash
brew install ffmpeg
ffprobe -version
```

密钥或账号权限未确认，不阻塞健康检查和上传骨架；没有 `ffprobe` 时无法完成真实上传校验。

## 配置

1. 复制密钥模板（不要把填好的 `.env` 提交到 Git）：

```bash
cd backend
cp .env.example .env
```

2. `.env.example` 只保留空密钥。真实的 `BAILIAN_API_KEY`、`DEEPSEEK_API_KEY`、`AMAP_API_KEY` 由你填入本地 `.env`。高德使用 Web 服务类型 Key。
3. 百炼使用北京地域。ASR、TTS、DeepSeek 的模型名和请求地址分开配置。
4. 即使不填写任何密钥，`GET /health` 和 `POST /upload` 仍可工作（上传依赖 `ffprobe`）。`POST /asr` 默认需要 `BAILIAN_API_KEY`。`POST /extract` 默认需要 `DEEPSEEK_API_KEY`。`POST /search` 默认需要 `AMAP_API_KEY`（Web 服务类型）。本地联调可把 `ASR_MOCK`、`EXTRACT_MOCK`、`SEARCH_MOCK` 设为 `true`，**不等于真实识别、提取或搜店**。

## 启动

```bash
cd backend
source .venv/bin/activate
uvicorn main:app --host 127.0.0.1 --port 8003 --reload
```

```bash
cd frontend
npm run dev
```

## 如何用 /docs 上传刚下载的录音

1. 前端按住录音并下载，例如 `~/Downloads/meetup-recording.webm`。
2. 确认已安装 `ffprobe`，后端已启动。
3. 打开 [http://127.0.0.1:8003/docs](http://127.0.0.1:8003/docs)
4. 找到 `POST /upload` → Try it out → 在 `file` 选择下载的录音 → Execute。字段名必须是 `file`。

### 正常上传

- 状态码：`200`
- 响应示例（`request_id`、`audio_id` 每次不同）：

```json
{
  "request_id": "3f1c0b8e-4a2d-4c1e-9f0a-7b6d2e1c9a10",
  "data": {
    "audio_id": "b6c1f2a0-4d3e-4c8a-9f11-2a7c0e8d91aa"
  }
}
```

`audio_id` 是临时编号，不是服务器路径。文件保存在 `backend/storage/audio/<audio_id>/recording.webm`（或 `.ogg`），同目录 `meta.json` 记录创建时间，供 24 小时有效期校验。接口响应里不会出现这些路径。

缺少 Duration 元数据的浏览器录音：先读 stream/format 时长；没有则用音频包时间戳计算，不把「没有 Duration」直接判为非法。

### 异常用例

| 做法 | 状态码 | 响应示例 |
| --- | --- | --- |
| 上传 `.txt` 或把扩展名改成 `.webm` 的非 Opus 文件 | 415 | 见下 |
| 上传大于 5MB 的文件 | 413 | 见下 |
| 用极短录音（探测时长 &lt; 1 秒）或人为构造超 60 秒 | 422 | 见下 |
| 未安装 ffprobe | 502 | `PROBE_UNAVAILABLE` |

格式不支持（415）：

```json
{
  "request_id": "3f1c0b8e-4a2d-4c1e-9f0a-7b6d2e1c9a10",
  "error": {
    "code": "UNSUPPORTED_MEDIA_TYPE",
    "message": "不支持的录音格式，请使用浏览器录制的 WebM/Opus 或 Ogg/Opus。",
    "stage": "upload"
  }
}
```

文件过大（413）：

```json
{
  "request_id": "3f1c0b8e-4a2d-4c1e-9f0a-7b6d2e1c9a10",
  "error": {
    "code": "FILE_TOO_LARGE",
    "message": "录音文件过大，最大允许 5MB。",
    "stage": "upload"
  }
}
```

时长过短（422）：

```json
{
  "request_id": "3f1c0b8e-4a2d-4c1e-9f0a-7b6d2e1c9a10",
  "error": {
    "code": "DURATION_TOO_SHORT",
    "message": "录音时长过短，请按住至少 1 秒后重试。",
    "stage": "upload"
  }
}
```

时长过长（422）的 `code` 为 `DURATION_TOO_LONG`，文案为「录音时长超过 60 秒，请缩短后重试。」

缺少 `file` 字段（422）：

```json
{
  "request_id": "3f1c0b8e-4a2d-4c1e-9f0a-7b6d2e1c9a10",
  "error": {
    "code": "INVALID_REQUEST",
    "message": "请求缺少必要字段或字段类型不正确，请检查后重试。",
    "stage": "request"
  }
}
```

## 如何测试 POST /asr

先 `POST /upload` 拿到真实 `audio_id`，再调用识别。不要把服务器文件路径当作编号。

1. 在 `/docs` 上传录音，复制返回的 `data.audio_id`
2. 打开 `POST /asr` → Try it out，请求体：

```json
{
  "audio_id": "粘贴上一步的编号"
}
```

### 超时预算

- 读取编号、校验 24 小时有效期、用 ffprobe 复查格式：约 10 秒
- 百炼 ASR：`ASR_TIMEOUT_S=40`
- 本接口总预算约 50 秒。前端以后接入时超时应略长于 50 秒。本轮前端不调用此接口。

### 本地 Mock（不调用百炼、不产生费用）

在 `backend/.env` 设置后**重启后端**（改 Python 文件时 `--reload` 也会生效）：

```
ASR_MOCK=true
ASR_MOCK_TEXT=我在杭州东站，朋友在西湖龙翔桥地铁站，帮我们找个中间的咖啡店。
```

仍须先 `POST /upload` 拿到未过期的 `audio_id`，接口会复查格式，但**不会**请求百炼。响应字段与真实识别相同，只有 `text` 来自配置，不是录音内容。关掉 Mock 或填了密钥后请把 `ASR_MOCK` 改回 `false`，否则会继续跳过付费接口。

### 正常识别（需要真实密钥，会产生费用）

`ASR_MOCK=false`，并在 `backend/.env` 填写 `BAILIAN_API_KEY` 后**重启后端**。状态码 `200`：

```json
{
  "request_id": "3f1c0b8e-4a2d-4c1e-9f0a-7b6d2e1c9a10",
  "data": {
    "text": "我在杭州东站，朋友在西湖龙翔桥地铁站，帮我们找个中间的咖啡店。"
  }
}
```

`text` 来自百炼真实识别结果，不是固定占位文案。日志只记录阶段、耗时和字数，不会打印密钥或音频 Base64。

### 异常

| 做法 | 状态码 | code | 是否付费 |
| --- | --- | --- | --- |
| 随机/过期 `audio_id` | 404 | `AUDIO_NOT_FOUND` | Mock / 本地即可 |
| 请求体缺少 `audio_id` | 422 | `INVALID_REQUEST` | Mock |
| 未填写 `BAILIAN_API_KEY` 且 `ASR_MOCK=false` | 502 | `ASR_NOT_CONFIGURED` | 本地即可 |
| 识别结果为空 | 422 | `ASR_EMPTY` | 真实调用或 Mock |
| 百炼超时 | 504 | `ASR_TIMEOUT` | Mock 或真实慢网 |
| 百炼失败/密钥无效 | 502 | `ASR_UPSTREAM` / `ASR_UNAUTHORIZED` | 真实密钥错误会失败，不循环重试 |

## 可选 Mock 测试

`ASR_MOCK=true` 时，`POST /asr` 本身就是本地固定文案，不是真实 ASR。

不调用外部付费接口的 pytest：

```bash
cd backend
source .venv/bin/activate
pytest -q
```

Mock 通过不能证明真实 ASR、DeepSeek 或高德已跑通。真实调用请你确认并执行，我不会自动调用付费接口。

## 如何测试 POST /extract

在 `/docs` 调用。请求体：

```json
{
  "text": "我在杭州东站，朋友在西湖龙翔桥地铁站，帮我们找个中间的咖啡店。",
  "city": "杭州"
}
```

`city` 是页面选定城市；口述里没说城市时，用这个值。完整成功时 `data` **只有**五个字段，不含 `party_count`。

### 本地 Mock

`EXTRACT_MOCK=true` 时不调用 DeepSeek，固定返回杭州东站 / 龙翔桥 / 咖啡店。输入文本会被忽略。

### 正常提取（需要 DEEPSEEK_API_KEY，会产生费用）

`EXTRACT_MOCK=false`。DeepSeek 使用 `deepseek-v4-flash`，关闭思考，JSON 模式。提示词在 `backend/prompts/extract.txt`。接口总预算约 25 秒（其中模型约 20 秒）。

状态码 `200`：

```json
{
  "request_id": "3f1c0b8e-4a2d-4c1e-9f0a-7b6d2e1c9a10",
  "data": {
    "city_a": "杭州",
    "address_a": "杭州东站",
    "city_b": "杭州",
    "address_b": "西湖龙翔桥地铁站",
    "category": "咖啡店"
  }
}
```

可直接在 `/docs` 试的异常输入：

| 请求 text | 预期 |
| --- | --- |
| 我在杭州东站，朋友在西湖龙翔桥地铁站，帮我们找个中间的咖啡店。 | 200，五个字段 |
| 我在杭州，朋友也在杭州，找个咖啡店。 | 422 `ADDRESS_MISSING` |
| 我在我家，朋友在公司，找个咖啡店。 | 422 `ADDRESS_MISSING` |
| 我们三个人分别在杭州东站、龙翔桥和河坊街，找个咖啡店。 | 422 `PARTY_COUNT` |
| 我在杭州东站，朋友在上海虹桥站，找个咖啡店。 | 422 `CROSS_CITY` |

模型返回非法 JSON 或缺少约定字段是 502 `EXTRACT_INVALID_RESPONSE`，不要理解成「用户没说清楚」。未填密钥且未开 Mock 是 502 `EXTRACT_NOT_CONFIGURED`。

## 如何测试 POST /search

把 `/extract` 返回的五个字段原样作为请求体：

```json
{
  "city_a": "杭州",
  "address_a": "杭州东站",
  "city_b": "杭州",
  "address_b": "西湖龙翔桥地铁站",
  "category": "咖啡店"
}
```

### 本地 Mock

`SEARCH_MOCK=true` 时不调用高德，返回演示中点和最多 3 家模拟店。店名带「模拟店」，不是真实 POI。

### 正常搜店（需要 AMAP_API_KEY，会计入高德配额）

`SEARCH_MOCK=false`。流程：

1. 用 [地理编码](https://lbs.amap.com/api/webservice/guide/api/georegeo) 按城市查双方坐标，经度在前、纬度在后，保持高德坐标系。
2. 结合城市、匹配级别、地名/地址筛选；国家/省/市/区县等过粗级别不用。多个不同候选即使相距不到 300 米也不会自动当成同一地点；无法区分则 422 `LOCATION_AMBIGUOUS`。
3. 对经度、纬度分别求平均，得到地理中点。这只表示位置大致居中，**不能**理解成两人出行时间相同。
4. 用 [周边搜索](https://lbs.amap.com/api/webservice/guide/api-advanced/search) 以类别为 `keywords`，先 2000 米，无有效店再 5000 米。
5. 后端自己按「距离中点」升序排序，最多保留 3 家。优先用高德返回的有效距离；缺失时用候选坐标与中点计算，不把缺失填成 0。
6. 保存结果 24 小时，返回 `search_id`（不是文件路径），供以后 `/finalize` 使用。

单次高德超时 `AMAP_TIMEOUT_S=8`。本接口含两次定位和最多两次周边搜索，总预算约 45 秒。

状态码 `200`：

```json
{
  "request_id": "3f1c0b8e-4a2d-4c1e-9f0a-7b6d2e1c9a10",
  "data": {
    "search_id": "7c2e1b90-5d4a-4c8a-9f11-2a7c0e8d91aa",
    "midpoint": {
      "longitude": 120.1885,
      "latitude": 30.2755
    },
    "pois": [
      {
        "name": "示例咖啡店",
        "address": "杭州市上城区示例路1号",
        "distance_to_midpoint_m": 180
      }
    ]
  }
}
```

`distance_to_midpoint_m` 单位是米，表示距离中点，不是步行或驾车时间。

| 情况 | 状态码 | code |
| --- | --- | --- |
| 地点含糊或多种匹配无法区分 | 422 | `LOCATION_AMBIGUOUS` |
| 2000 米和 5000 米都没有有效店 | 422 | `NO_CANDIDATES` |
| 未填 `AMAP_API_KEY` 且 `SEARCH_MOCK=false` | 502 | `SEARCH_NOT_CONFIGURED` |
| 高德超时 | 504 | `SEARCH_TIMEOUT` |

## 尚未实现

- 前端把录音 POST 到 `/upload` 再调用 `/asr`、`/extract`、`/search`
- `POST /finalize`
- `GET /audio/{audio_id}` 播放接口
- 推荐语 DeepSeek 提示词
