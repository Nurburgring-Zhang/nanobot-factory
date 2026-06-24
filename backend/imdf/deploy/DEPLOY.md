# IMDF 生产部署指南

## 系统要求
- Ubuntu 22.04+ / Debian 12+
- Python 3.12+
- ffmpeg 6.0+
- 4GB RAM / 20GB 磁盘
- (可选) nginx + Let's Encrypt

## 快速部署(3步)

### 1. 安装依赖
```bash
cd /mnt/d/Hermes/infinite-multimodal-data-foundry
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 填入真实API Key和密钥
vim .env
```

### 2. 安装系统服务
```bash
sudo cp deploy/imdf.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now imdf
```

### 3. 配置nginx(HTTPS)
```bash
sudo apt install nginx certbot python3-certbot-nginx
sudo cp deploy/nginx-imdf.conf /etc/nginx/sites-available/imdf
sudo sed -i 's/your-domain.com/你的域名/g' /etc/nginx/sites-available/imdf
sudo ln -s /etc/nginx/sites-available/imdf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d 你的域名
```

## 验证
```bash
curl http://localhost:8765/api/v1/health
# {"status":"ok","service":"imdf","version":"2.0.0"}

sudo systemctl status imdf
# Active: active (running)
```

## 规模
- 79个Python模块 / 18个JS页面
- 24,000行Python + 18,000行前端
- 21个导航页面 / 20+条API路由
- 48种画布节点 / 44个管线算子
- 728个文件 / 26MB

## 多用户部署

### 创建第一个管理员账号

部署完成后，第一个管理员需要通过命令行创建：

```bash
# 方法一: 命令行直接创建
python scripts/create_admin.py --username admin --password YOUR_SECURE_PASSWORD

# 方法二: 通过环境变量创建
export IMDF_ADMIN_USERNAME=admin
export IMDF_ADMIN_PASSWORD=YOUR_SECURE_PASSWORD
python scripts/create_admin.py

# 重置已有管理员密码
python scripts/create_admin.py --username admin --password NEW_PASSWORD --force
```

管理员拥有最高权限，可访问所有管理页面和API。

### 用户注册

注册功能由 `.env` 中的 `IMDF_REGISTRATION_ENABLED` 控制:

- **允许注册 (默认):** 设置 `IMDF_REGISTRATION_ENABLED=true`
  用户访问 `/auth/register` 或前端注册页面自行注册，默认角色为 `viewer`。

- **禁止注册 (生产推荐):** 设置 `IMDF_REGISTRATION_ENABLED=false`
  只有管理员可以通过 `scripts/create_admin.py` 创建用户。新用户创建:
  ```bash
  python scripts/create_admin.py --username newuser --password TheirPass123 --role viewer
  ```

### 角色权限说明

| 角色 | 权限 |
|------|------|
| `admin` | 全部权限：用户管理、系统配置、数据管理、API Key管理 |
| `manager` | 项目管理：创建/管理项目、审核标注结果、查看统计 |
| `viewer` | 只读：浏览数据、查看看板，不可修改 |

### 认证接口

```bash
# 登录获取token
curl -X POST http://localhost:8765/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"YOUR_PASSWORD"}'

# 返回: {"access_token":"eyJ...", "token_type":"bearer"}

# 使用token访问API
curl http://localhost:8765/auth/me \
  -H "Authorization: Bearer eyJ..."

# 修改密码
curl -X PUT http://localhost:8765/auth/password \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{"old_password":"OLD","new_password":"NEW"}'
```

## 安全注意事项

### 部署前安全检查

- [ ] **修改 JWT_SECRET_KEY** — 必须修改，不能用默认值:
  ```bash
  openssl rand -hex 32  # 生成64字符随机密钥
  ```
  将生成的值填入 `.env` 的 `JWT_SECRET_KEY`。

- [ ] **禁用公开注册** — 生产环境设置 `IMDF_REGISTRATION_ENABLED=false`

- [ ] **配置 nginx HTTPS + 防火墙**:
  ```bash
  sudo ufw allow 80/tcp
  sudo ufw allow 443/tcp
  sudo ufw deny 8765  # 阻止直接访问应用端口
  sudo ufw enable
  ```

- [ ] **CORS origins 改为实际域名** — 修改 `api/canvas_web.py` 中 `allow_origins`:
  ```python
  allow_origins=["https://your-domain.com"],
  ```

- [ ] **配置 .env 中的 API Key** — 填入各AI服务商的API密钥

- [ ] **设置文件权限** — `.env` 文件应仅应用用户可读:
  ```bash
  chmod 600 .env
  chmod 600 data/imdf.db
  ```

- [ ] **定期备份数据库**:
  ```bash
  # 手动备份
  cp data/imdf.db data/backups/imdf_$(date +%Y%m%d_%H%M%S).db

  # 或使用API自动备份
  curl -X POST http://localhost:8765/api/v1/backup
  ```

### 运行中安全建议

- 定期轮换 `JWT_SECRET_KEY`（注意：轮换会使所有现有token失效）
- 监控 `/auth/login` 端点的失败尝试（审计日志中查看）
- 使用 `systemd` 的 `ProtectSystem=strict` 限制服务进程文件访问
- 定期审查 `data/audit.db` 中的审计记录
- 管理员密码使用强密码（12+字符，含大小写字母、数字、符号）

## 安全清单
- [ ] 修改JWT_SECRET_KEY(openssl rand -hex 32)
- [ ] 配置nginx HTTPS + 防火墙
- [ ] CORS origins改为实际域名
- [ ] 配置.env中的API Key
- [ ] 创建管理员账号 (scripts/create_admin.py)
- [ ] 禁用公开注册 (生产环境)
- [ ] 设置 .env 文件权限 (chmod 600)
- [ ] 定期备份 data/imdf.db
