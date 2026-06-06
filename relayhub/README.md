# RelayHub

ISP IP 中转开通服务 —— 把 decode SOCKS5 线路一键配置进 Marzban/Xray 并出订阅。
CLI 与 Web 共用同一套开通编排（`ProvisioningService`），出站安全护栏不可旁路。

关联文档：[../需求文档.md](../需求文档.md) · [../技术设计与研发方案.md](../技术设计与研发方案.md) · [../项目计划.md](../项目计划.md)

## 结构

```
app/  config 配置 | parsing 线路解析 | guard 出站护栏(SEC-5)
      marzban API客户端 | provisioning 编排 | models 模型 | api FastAPI
web/index.html   管理面板(接 API, 离线回退演示)
scripts/add_line.py   CLI 薄封装
tests/   parsing / guard / provisioning / marzban
```

## 开发

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest        # 23 用例
```

## 运行

```bash
cp .env.example .env            # 填面板地址/凭据/local_ip, 权限 600
chmod 600 .env

# Web 面板 (仅监听本地, SEC-3)
.venv/bin/uvicorn app.api:app --host 127.0.0.1 --port 8080
# 运维经 SSH 隧道访问:  ssh -L 8080:127.0.0.1:8080 user@vps -p 2222

# CLI 开通
.venv/bin/python -m scripts.add_line zhang 1.2.3.4:8080:user:pass --days 30
```

## 部署

见 systemd/relayhub.service 与技术文档 C1。

## 安全不变量

每次开通都重建出站护栏并置顶（私网 / 本机IP / 25端口），由 `tests/test_provisioning.py::test_security_regression_guard_stays_on_top_with_preexisting_rules` 锁定，防止 SEC-5 回归。
