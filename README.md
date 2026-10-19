# izchu

izchu 是一个私人骑行数据服务。当前 MVP 只读取数据，不会修改 Strava 或 Garmin 中的活动。

它现在可以：

- 通过 Strava OAuth 读取运动员、活动详情和逐点流数据，并自动轮换短期 token。
- 通过 Garmin Connect 读取码表活动、训练效果、圈数、天气、心率区间和功率区间。
- 下载 Garmin 原始活动文件并用 Garmin 官方 FIT SDK 解码功率、心率、踏频、左右平衡等实际记录字段。
- 将 Garmin 原始响应、FIT 文件和完整解码结果保存在本地数据卷中，方便后续生成 Strava 描述。

## 在群晖上启动

在 Container Manager 能访问的目录中放置本仓库，然后进入该目录：

```bash
cp .env.example .env
```

编辑 `.env`：

```dotenv
IZCHU_STRAVA_CLIENT_ID=286135
IZCHU_STRAVA_CLIENT_SECRET=你的_Strava_Client_Secret
IZCHU_STRAVA_REDIRECT_URI=http://你的群晖地址:8080/api/strava/callback
IZCHU_DATA_DIR=/data
```

为容器创建私有数据目录（容器内运行用户 UID 为 `10001`）：

```bash
mkdir -p data
sudo chown 10001:10001 data
chmod 700 data
chmod 600 .env
```

Strava API 设置页的 `Authorization Callback Domain` 必须与回调地址中的主机一致。若在同一台电脑本地运行，可保留 `localhost`。

构建并启动：

```bash
docker compose up -d --build
```

打开 `http://你的群晖地址:8080/docs` 可看到交互式接口页面。

## 连接 Strava

浏览器打开：

```text
http://你的群晖地址:8080/api/strava/connect
```

完成授权后，izchu 会把 token 保存到 `data/strava-token.json`，文件权限为 `0600`。应用会在 token 临近过期时自动刷新，并保存 Strava 返回的新 refresh token。

验证：

```text
GET /api/strava/athlete
GET /api/strava/activities
GET /api/strava/activities/{activity_id}
GET /api/strava/activities/{activity_id}/streams
```

如果之前保存了有效的 `strava-token.json`，可在停掉容器后把它放进 `data/`，无需再次授权。不要把 token 提交到 Git。

## 连接 Garmin Connect

首次登录用一次性容器完成，密码不会写进数据卷：

```bash
docker compose run --rm izchu izchu garmin-login
```

按提示输入 Garmin 邮箱、密码和可能出现的 MFA 验证码。成功后，可续期的登录 token 会保存在 `data/garmin-tokens/`；以后服务只使用 token。

验证：

```text
GET  /api/garmin/activities?activity_type=cycling
GET  /api/garmin/activities/{activity_id}
POST /api/garmin/activities/{activity_id}/fit
```

第三个接口会下载并解析原始 FIT。完整逐秒记录默认只写入：

```text
data/activities/garmin-{activity_id}/fit-decoded.json
```

若确实需要在响应中返回全部逐秒记录，增加 `?include_records=true`。

也可以直接检查从码表导出的本地文件：

```bash
docker compose run --rm -v /你的目录:/imports:ro izchu \
  izchu inspect-fit /imports/activity.fit
```

## 数据与安全边界

- `.env`、OAuth token、Garmin token、活动 JSON 和 FIT 文件都被 Git 忽略。
- 当前 API 没有写活动接口，接入验证阶段不会覆盖 Strava 描述。
- Garmin Connect 接入使用社区维护的非官方接口，可能因 Garmin 登录或字段变化需要升级依赖。
- `data/` 包含位置、健康和训练数据；群晖目录不要开放匿名共享，外网访问前需要增加 HTTPS 和登录保护。

## 本地开发

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check .
```

